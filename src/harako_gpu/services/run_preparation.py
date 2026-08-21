"""Fail-closed materialization of immutable local execution runs."""

from __future__ import annotations

import json
import os
import re
import shutil
import gzip
import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from harako_gpu.adapters.docker import DockerImageContract, canonical_image_identity, inspect_image_contract
from harako_gpu.adapters.execution import CommandSpec, write_command_spec
from harako_gpu.adapters.execution_context import ExecutionContext, NATIVE_LINUX, parse_execution_context, require_native_linux_host
from harako_gpu.adapters.filesystem import (
    ensure_within, make_tree_read_only, require_safe_linux_runtime_path, sha256_path, tree_inventory, write_new_text,
)
from harako_gpu.adapters.nfcore_patch import load_patch_manifest, verify_patch_state
from harako_gpu.adapters.process import ProcessRunner
from harako_gpu.core.canonical import sha256_payload
from harako_gpu.core.capabilities import ExecutionRoute
from harako_gpu.core.run_lifecycle import RunIdentity, RunState, RunStatus, StageId, TaskRecord
from harako_gpu.services.backend_profile import validate_nf_params
from harako_gpu.services.alignment_profiles import fixed_parabricks_extra_args, get_alignment_profile
from harako_gpu.services.planning import validate_plan_file
from harako_gpu.services.preflight import collect_preflight
from harako_gpu.services.quantification_profiles import AnalysisMode, ModeSelection, ProfileIndex, get_profile, salmon_argv
from harako_gpu.services.run_state import RunStateStore, utc_now
from harako_gpu.services.salmon_reproducibility import parse_transcript_gene_map
from harako_gpu.services.star_gene_counts import PARABRICKS_IMAGE_DIGEST
from harako_gpu.services.host_profiles import (
    FULL_HUMAN_TASK_IMAGES, PLUGIN_CLOSURE_ID, TASK_IMAGE_CLOSURE_ID,
    PARABRICKS_CONFIG_IMAGE_ID, PARABRICKS_SOURCE_REFERENCE,
    UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
    HostQualificationReceipt, OfflinePlatformImageProvenance, PluginClosureReceipt,
    featurecounts_contract, runtime_quantification_image_contract, select_resource_contract,
    validate_task_image_closure,
)
from harako_gpu.services.runtime_validation_images import bam_validator_freeze_payload
from harako_gpu.services.workflow_backends import (
    HARAKO_NATIVE_V1,
    NFCORE_REFERENCE,
    selected_image_roles,
    workflow_backend_for_plan,
)


PIPELINE_COMMIT = "e7ca46272c8f9d5ceee3f71759f4ba551d3217a4"
NEXTFLOW_VERSION = "25.04.3"
GENECOUNTS_CONTRACT = "parabricks-star-genecounts-explicit-library-v2"
FASTP_IMAGE_REFERENCE = "community.wave.seqera.io/library/fastp:1.0.1--c8b87fe62dcc103c"
FASTP_IMAGE_IDENTITY = "sha256:d228dace961ab50d04471e02e7fd2c8f2b8cd5b1b37be2d4039e2db64fcfae45"
IMAGE_CONTRACTS = {
    # Historical evidence does not distinguish a registry digest for Parabricks;
    # retain the pre-existing exact Docker .Id validation semantics.
    "parabricks": DockerImageContract(
        "nvcr.io/nvidia/clara/clara-parabricks:4.6.0-1",
        PARABRICKS_IMAGE_DIGEST,
        "image_id",
    ),
    "fastp": DockerImageContract(
        FASTP_IMAGE_REFERENCE,
        FASTP_IMAGE_IDENTITY,
        "repo_digest",
    ),
    "salmon_1_10_3_compatibility": DockerImageContract(
        "quay.io/biocontainers/salmon:1.10.3--h6dccd9a_2",
        "sha256:f83ebb158845ee8138d793347f83b92c75e83c58dd8f4600c6fea2a2453ef08e",
        "repo_digest",
    ),
    "salmon_2_5_1_deterministic": DockerImageContract(
        "harako-gpu/salmon:2.5.1-qualification",
        "sha256:e6e64f39a479458ef6f007757498321ee5a3ef8a2227ff2af414fbe3c36e6f7f",
        "image_id",
    ),
}


def _qualified_task_contract(process_role: str) -> DockerImageContract:
    matches = [item.contract for item in FULL_HUMAN_TASK_IMAGES if item.process_role == process_role]
    if len(matches) != 1:
        raise ValueError(f"Expected one fixed task image for {process_role}")
    return matches[0]


def _runtime_image_contract(requirements: "RuntimeRequirements", role: str) -> DockerImageContract:
    return runtime_quantification_image_contract(requirements.host_profile_id, role) or IMAGE_CONTRACTS[role]


def _native_runtime_image_contract(
    requirements: "RuntimeRequirements", role: str,
) -> DockerImageContract:
    if role == "parabricks":
        return DockerImageContract(
            PARABRICKS_SOURCE_REFERENCE, PARABRICKS_CONFIG_IMAGE_ID, "image_id",
        )
    return _runtime_image_contract(requirements, role)


IMAGE_CONTRACTS.update({
    "samtools": _qualified_task_contract("SAMTOOLS"),
    "subread_featurecounts": _qualified_task_contract("SUBREAD_FEATURECOUNTS"),
    "multiqc": _qualified_task_contract("MULTIQC"),
})
DEFAULT_IMAGE_ROLES = (
    "parabricks", "fastp", "salmon_1_10_3_compatibility", "salmon_2_5_1_deterministic",
)
EXPECTED_IMAGES = {role: IMAGE_CONTRACTS[role].identity for role in DEFAULT_IMAGE_ROLES}
ALL_IMAGE_IDENTITIES = {role: contract.identity for role, contract in IMAGE_CONTRACTS.items()}
IMAGE_REFERENCES = {role: contract.reference for role, contract in IMAGE_CONTRACTS.items()}


@dataclass(frozen=True)
class RuntimeRequirements:
    """Concrete fixed runtime prerequisites for one validated Harako-GPU plan."""

    execution_route: str
    required_image_roles: tuple[str, ...]
    requires_gpu: bool
    requires_java: bool
    requires_nextflow: bool
    requires_nfcore_pipeline: bool
    requires_star_index: bool
    requires_bam_validation: bool
    host_profile_id: str
    requires_offline_closure: bool
    workflow_backend: str = NFCORE_REFERENCE
    requires_nf_schema: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def runtime_requirements_for_plan(plan: Mapping[str, Any]) -> RuntimeRequirements:
    """Derive the small fixed prerequisite set after plan validation."""
    route = str(plan.get("execution_route") or ExecutionRoute.GPU_BAM_ALIGNMENT.value)
    host_profile_id = str(dict(dict(plan.get("capability_snapshot") or {}).get("result") or {}).get(
        "host_profile_id") or "windows_wsl2_rtx3090_ram64_v1"
    )
    selection = ModeSelection.create(
        AnalysisMode(str(dict(plan.get("quantification") or {})["mode"])),
        str(dict(plan.get("quantification") or {})["primary_profile_id"]),
    )
    selected_profiles = {
        profile_id for profile_id in (
            selection.primary_profile_id,
            selection.secondary_profile_id,
        ) if profile_id is not None
    }
    workflow = workflow_backend_for_plan(plan)
    roles = selected_image_roles(
        workflow.workflow_backend,
        quantification_only=route == ExecutionRoute.FASTQ_QUANTIFICATION_ONLY.value,
        quantification_profiles=tuple(
            role for role in IMAGE_REFERENCES if role in selected_profiles
        ),
    )
    if route == ExecutionRoute.FASTQ_QUANTIFICATION_ONLY.value:
        return RuntimeRequirements(
            route, roles, False, False, False, False, False, False,
            host_profile_id, False, workflow.workflow_backend, False,
        )
    if route != ExecutionRoute.GPU_BAM_ALIGNMENT.value:
        raise ValueError(f"Unsupported execution route: {route}")
    return RuntimeRequirements(
        route, roles, True, True, True,
        workflow.workflow_backend == NFCORE_REFERENCE,
        True, True, host_profile_id,
        host_profile_id == UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
        workflow.workflow_backend,
        workflow.requires_nf_schema,
    )


def runtime_requirements_for_plan_file(path: Path) -> RuntimeRequirements:
    source = path.expanduser().resolve()
    validate_plan_file(source)
    return runtime_requirements_for_plan(json.loads(source.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class PreparationContext:
    execution: ExecutionContext
    pipeline_source_linux: str
    nextflow_executable: str
    observed_image_ids: Mapping[str, str]
    hardware_report: Mapping[str, Any]
    repository_root: Path
    runner: ProcessRunner
    read_only_snapshot: bool = True
    host_receipt: HostQualificationReceipt | None = None
    plugin_receipt: PluginClosureReceipt | None = None
    task_image_inspections: Mapping[str, Mapping[str, Any]] | None = None
    parabricks_provenance: OfflinePlatformImageProvenance | None = None
    parabricks_image_inspection: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class PreparedRun:
    run_id: str
    run_dir_linux: str
    run_dir: Path
    approval_hash: str
    primary_profile_id: str
    secondary_profile_id: str | None


def _inspect_images(
    process: ProcessRunner,
    prefix: tuple[str, ...],
    roles: tuple[str, ...],
    contracts: Mapping[str, DockerImageContract] | None = None,
) -> dict[str, str]:
    observed = {}
    for role in roles:
        try:
            observed[role] = inspect_image_contract(
                process,
                (contracts or IMAGE_CONTRACTS)[role],
                prefix=prefix,
            )
        except ValueError as exc:
            raise ValueError(f"Required image identity validation failed for {role}: {exc}") from exc
    return observed


def _inspect_raw_image(process: ProcessRunner, reference: str) -> Mapping[str, Any]:
    result = process.run(("docker", "image", "inspect", reference), timeout=15)
    if not result.ok:
        raise ValueError(f"Required local image unavailable: {reference}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("Docker image inspect returned malformed JSON") from exc
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise ValueError("Docker image inspect must return one object")
    return payload[0]


def _load_receipt(path: Path, kind: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read installed {kind} receipt: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Installed {kind} receipt must be an object")
    return value


def build_wsl_preparation_context(*, runtime_root: str, distribution: str = "Ubuntu",
                                  runner: ProcessRunner | None = None,
                                  requirements: RuntimeRequirements | None = None) -> PreparationContext:
    process = runner or ProcessRunner()
    runtime_root = require_safe_linux_runtime_path(runtime_root)
    execution = parse_execution_context("wsl2", distribution=distribution)
    prefix = ("wsl.exe", "--distribution", distribution, "--exec")
    roles = DEFAULT_IMAGE_ROLES if requirements is None else requirements.required_image_roles
    observed = _inspect_images(process, prefix, roles)
    requires_nextflow = requirements is None or requirements.requires_nextflow
    nextflow = "NOT_APPLICABLE"
    if requires_nextflow:
        uid = process.run(("wsl.exe", "--distribution", distribution, "--exec", "/usr/bin/id", "-u"), timeout=5)
        if not uid.ok or not uid.stdout.strip().isdigit():
            raise ValueError("Cannot resolve WSL user identity")
        passwd = process.run(("wsl.exe", "--distribution", distribution, "--exec", "/usr/bin/getent", "passwd", uid.stdout.strip()), timeout=5)
        if not passwd.ok or len(passwd.stdout.strip().split(":")) < 6:
            raise ValueError("Cannot resolve WSL home directory")
        home = passwd.stdout.strip().split(":")[5]
        nextflow = f"{home}/.local/bin/nextflow"
        version = process.run(("wsl.exe", "--distribution", distribution, "--exec", "/usr/bin/env",
                               "NXF_VER=25.04.3", nextflow, "-version"), timeout=30)
        if not version.ok or "25.04.3" not in (version.stdout + version.stderr):
            raise ValueError("Pinned Nextflow 25.04.3 is unavailable")
    report = collect_preflight(runner=process, wsl_work_root=runtime_root).as_dict()
    return PreparationContext(
        execution=execution,
        pipeline_source_linux=f"{runtime_root}/metrics-compatibility/pipeline-qualified",
        nextflow_executable=nextflow, observed_image_ids=observed, hardware_report=report,
        repository_root=Path(__file__).resolve().parents[3], runner=process,
    )


def build_native_linux_preparation_context(
    *,
    runtime_root: str,
    nextflow_executable: str | None = None,
    runner: ProcessRunner | None = None,
    host_system: str | None = None,
    kernel_release: str | None = None,
    hardware_report: Mapping[str, Any] | None = None,
    requirements: RuntimeRequirements | None = None,
) -> PreparationContext:
    """Resolve the fixed native toolchain without downloads, pulls, or fallback."""
    require_native_linux_host(host_system=host_system, kernel_release=kernel_release)
    execution = parse_execution_context(NATIVE_LINUX)
    process = runner or ProcessRunner()
    runtime_root = require_safe_linux_runtime_path(runtime_root)
    requires_nextflow = requirements is None or requirements.requires_nextflow
    resolved_value = "NOT_APPLICABLE"
    if requires_nextflow:
        resolved = nextflow_executable or shutil.which("nextflow")
        if resolved is None:
            raise ValueError("Pinned Nextflow 25.04.3 is unavailable")
        resolved_path = Path(resolved)
        if not resolved_path.is_absolute():
            located = shutil.which(resolved)
            if located is None:
                raise ValueError("Pinned Nextflow 25.04.3 is unavailable")
            resolved_path = Path(located)
        if not resolved_path.is_file():
            raise ValueError("Pinned Nextflow executable is missing")
        version = process.run(
            (str(resolved_path), "-version"), timeout=30, env={"NXF_VER": NEXTFLOW_VERSION},
        )
        if not version.ok or re.search(r"\b25\.04\.3\b", version.stdout + version.stderr) is None:
            raise ValueError("Pinned Nextflow 25.04.3 is unavailable")
        resolved_value = str(resolved_path)
    high_memory = requirements is not None and requirements.requires_offline_closure
    host_receipt = None
    plugin_receipt = None
    task_inspections = None
    provenance = None
    parabricks_inspection = None
    if high_memory:
        receipt_root = Path(runtime_root) / "host-profiles"
        host_receipt = HostQualificationReceipt.load(
            receipt_root / f"{UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID}.json"
        )
        host_receipt.validate(
            report_root=Path(__file__).resolve().parents[3] / "docs/qualification"
        )
        if requirements.requires_nf_schema:
            plugin_receipt = PluginClosureReceipt(**dict(_load_receipt(
                receipt_root / f"{PLUGIN_CLOSURE_ID}.json", "plugin closure",
            )))
            plugin_receipt.validate()
            task_inspections = {
                item.contract.reference: _inspect_raw_image(process, item.contract.execution_reference)
                for item in FULL_HUMAN_TASK_IMAGES
            }
            validate_task_image_closure(task_inspections)
        else:
            task_inspections = {
                _runtime_image_contract(requirements, role).reference: _inspect_raw_image(
                    process, _runtime_image_contract(requirements, role).execution_reference,
                )
                for role in requirements.required_image_roles
                if role != "parabricks"
            }
            for role in requirements.required_image_roles:
                if role == "parabricks":
                    continue
                contract = _runtime_image_contract(requirements, role)
                canonical_image_identity(
                    contract, task_inspections[contract.reference],
                )
        provenance = OfflinePlatformImageProvenance.from_mapping(_load_receipt(
            receipt_root / "parabricks-offline-linux-amd64-v1.json", "Parabricks provenance",
        ))
        parabricks_inspection = _inspect_raw_image(process, provenance.source_reference)
        provenance.validate(
            observed_image=parabricks_inspection,
            expected_receipt_sha256=host_receipt.parabricks_provenance_receipt_sha256,
            expected_archive_sha256=host_receipt.parabricks_archive_sha256,
        )
        observed = {
            role: (
                provenance.config_image_id if role == "parabricks"
                else _runtime_image_contract(requirements, role).identity
            )
            for role in requirements.required_image_roles
        }
    else:
        roles = DEFAULT_IMAGE_ROLES if requirements is None else requirements.required_image_roles
        contracts = {
            role: (
                runtime_quantification_image_contract(requirements.host_profile_id, role)
                if requirements is not None
                else None
            ) or IMAGE_CONTRACTS[role]
            for role in roles
        }
        observed = _inspect_images(process, (), roles, contracts)
    report = dict(
        hardware_report if hardware_report is not None else
        collect_preflight(runner=process, cwd=Path(runtime_root),
                          wsl_work_root=runtime_root).as_dict()
    )
    return PreparationContext(
        execution=execution,
        pipeline_source_linux=f"{runtime_root}/metrics-compatibility/pipeline-qualified",
        nextflow_executable=resolved_value,
        observed_image_ids=observed,
        hardware_report=report,
        repository_root=Path(__file__).resolve().parents[3],
        runner=process, host_receipt=host_receipt, plugin_receipt=plugin_receipt,
        task_image_inspections=task_inspections, parabricks_provenance=provenance,
        parabricks_image_inspection=parabricks_inspection,
    )


def _linux_path(path: str, context: PreparationContext) -> Path:
    require_safe_linux_runtime_path(path)
    return context.execution.host_path(path)


def _run_id(plan_id: str, now: datetime | None = None) -> str:
    instant = (now or datetime.now(UTC)).astimezone(UTC)
    return instant.strftime("%Y%m%dT%H%M%SZ") + "-" + plan_id[:8]


def _copy_pipeline(source_linux: str, destination_linux: str, context: PreparationContext) -> None:
    source = _linux_path(source_linux, context)
    destination = _linux_path(destination_linux, context)
    if not source.is_dir() or destination.exists():
        raise ValueError("Pipeline source must exist and run snapshot must be new")
    if context.execution.is_wsl2:
        result = context.runner.run((
            "wsl.exe", "--distribution", str(context.execution.distribution), "--exec",
            "/usr/bin/cp", "-a", "--", source_linux, destination_linux,
        ), timeout=180)
        if not result.ok:
            raise ValueError(f"Cannot materialize pipeline snapshot: {result.stderr or result.exception}")
    else:
        shutil.copytree(source, destination, symlinks=True)


def _git_head(path_linux: str, context: PreparationContext) -> str:
    if context.execution.is_wsl2:
        result = context.runner.run((
            "wsl.exe", "--distribution", str(context.execution.distribution), "--exec",
            "/usr/bin/git", "-C", path_linux, "rev-parse", "HEAD",
        ), timeout=30)
    else:
        result = context.runner.run(("git", "-C", path_linux, "rev-parse", "HEAD"), timeout=30)
    if not result.ok:
        raise ValueError("Cannot resolve pipeline commit")
    return result.stdout.strip()


def _freeze_pipeline(path_linux: str, context: PreparationContext) -> None:
    if not context.read_only_snapshot:
        return
    if context.execution.is_wsl2:
        result = context.runner.run((
            "wsl.exe", "--distribution", str(context.execution.distribution), "--exec",
            "/usr/bin/chmod", "-R", "a-w", "--", path_linux,
        ), timeout=120)
        if not result.ok:
            raise ValueError("Cannot make pipeline snapshot read-only")
    else:
        make_tree_read_only(_linux_path(path_linux, context))


def _index_contracts(plan: Mapping[str, Any], selection: ModeSelection, context: PreparationContext) -> tuple[ProfileIndex, ...]:
    quantification = dict(plan.get("quantification") or {})
    if quantification.get("execution_indices_ready") is not True:
        raise ValueError("Plan lacks complete fixed profile index manifests")
    profiles = dict(quantification.get("profiles") or {})
    indices = []
    for profile_id in (selection.primary_profile_id, selection.secondary_profile_id):
        if not profile_id:
            continue
        try:
            index = ProfileIndex(**dict(profiles[profile_id]["index"]))
        except (KeyError, TypeError) as exc:
            raise ValueError("Plan profile index contract is missing") from exc
        index.validate()
        if not _linux_path(index.path, context).is_dir():
            raise ValueError(f"Pinned profile index is missing: {profile_id}")
        indices.append(index)
    return tuple(indices)


def _alignment_params(plan: Mapping[str, Any], original: Mapping[str, Any], *, run_dir: str, work_dir: str) -> dict[str, Any]:
    reference = dict(plan["reference"])
    backend = dict(plan["backend_profile"])
    quantification = dict(plan.get("quantification") or {})
    alignment_profile = get_alignment_profile(str(plan["alignment_profile_id"]))
    overhang = quantification.get("parabricks_star_sjdb_overhang")
    is_full_human = (
        reference.get("assembly") == "GRCh38.p14"
        and reference.get("annotation_provider") == "GENCODE"
        and str(reference.get("annotation_release")) == "49"
    )
    expected_overhang = 74 if is_full_human else 100
    if overhang != expected_overhang:
        raise ValueError(f"Execution requires fixed STAR index sjdbOverhang={expected_overhang}")
    star_arguments = fixed_parabricks_extra_args(
        alignment_profile.profile_id,
        sjdb_overhang=expected_overhang,
        qualification_debug_x3=backend.get("qualification_debug_mode") == "x3",
    )
    workflow = workflow_backend_for_plan(plan)
    if workflow.workflow_backend == HARAKO_NATIVE_V1:
        requirements = runtime_requirements_for_plan(plan)
        star_index = quantification.get("parabricks_star_index") or original.get("star_index")
        if not star_index:
            raise ValueError("Harako-native requires the frozen STAR index")
        feature_type, group_type = featurecounts_contract(
            "human_grch38p14_gencode49_harako_gpu_v1" if is_full_human
            else str(reference["reference_pack_id"]),
            feature_type="exon", group_type="gene_type" if is_full_human else "gene_id",
        )
        return {
            "input": f"{run_dir}/frozen/nf-samplesheet.csv",
            "outdir": f"{run_dir}/results",
            "fasta": reference["fasta_path"],
            "gtf": reference["gtf_path"],
            "star_index": star_index,
            "library_type": quantification["explicit_library_type"],
            "featurecounts_feature_type": feature_type,
            "featurecounts_group_type": group_type,
            "parabricks_two_pass_mode": "Basic" if alignment_profile.two_pass else "None",
            "parabricks_extra_args": star_arguments,
            "images": {
                role: _native_runtime_image_contract(requirements, role).execution_reference
                for role in (
                    "fastp", "parabricks", "samtools", "subread_featurecounts", "multiqc",
                )
            },
        }
    params: dict[str, Any] = {
        "aligner": "star_salmon", "input": f"{run_dir}/frozen/nf-samplesheet.csv",
        "outdir": f"{run_dir}/results/nfcore", "fasta": reference["fasta_path"], "gtf": reference["gtf_path"],
        "use_parabricks_star": True, "save_align_intermeds": True, "save_reference": False,
        "skip_markduplicates": True, "skip_pseudo_alignment": True,
        "trimmer": "fastp", "save_trimmed": True,
        "extra_star_align_args": star_arguments,
    }
    if reference.get("transcript_fasta_path"):
        params["transcript_fasta"] = reference["transcript_fasta_path"]
    star_index = quantification.get("parabricks_star_index") or original.get("star_index")
    if star_index:
        params["star_index"] = star_index
    if is_full_human:
        feature_type, group_type = featurecounts_contract(
            "human_grch38p14_gencode49_harako_gpu_v1",
            feature_type="exon", group_type="gene_type",
        )
        params["featurecounts_feature_type"] = feature_type
        params["featurecounts_group_type"] = group_type
    validate_nf_params(params)
    return params


def _execution_config(plan: Mapping[str, Any]) -> str:
    gpu = str(dict(plan["backend_profile"])["gpu_selection"])
    gpu_options = "--gpus all" if gpu == "all" else f'--gpus "device={gpu}"'
    backend = dict(plan["backend_profile"])
    workflow = workflow_backend_for_plan(plan)
    resource_limits = ""
    resource_contract_id = dict(plan.get("quantification") or {}).get("qualification_resource_contract")
    if resource_contract_id == "full_human_47gib_probe_v1":
        resource_limits = (
            "  withName: 'NFCORE_RNASEQ:RNASEQ:ALIGN_STAR:PARABRICKS_RNA_FQ2BAM' {\n"
            "    cpus = 12\n"
            "    memory = 42.GB\n"
            "    time = 12.h\n"
            "  }\n"
        )
    elif resource_contract_id in {
        "ubuntu_native_rtx3090_ram128_one_pass_42gb_v1",
        "ubuntu_native_rtx3090_ram128_two_pass_96gb_v1",
    }:
        result = dict(dict(plan.get("capability_snapshot") or {}).get("result") or {})
        contract = select_resource_contract(
            str(result.get("host_profile_id")), str(result.get("reference_pack_id")),
            str(plan.get("alignment_profile_id")),
        )
        if contract is None or contract.contract_id != resource_contract_id:
            raise ValueError("Frozen high-memory resource contract does not match host/reference/profile")
        resource_limits = (
            f"  withName: '{contract.process_selector}' {{\n"
            f"    cpus = {contract.cpus}\n"
            f"    memory = {contract.memory_gb}.GB\n"
            "    time = 12.h\n"
            "  }\n"
        )
    if backend.get("qualification_debug_mode") == "x3":
        if resource_contract_id in {
            "ubuntu_native_rtx3090_ram128_one_pass_42gb_v1",
            "ubuntu_native_rtx3090_ram128_two_pass_96gb_v1",
        }:
            raise ValueError("High-memory resource contracts cannot be replaced by the debug envelope")
        resource_limits = (
            "  withName: 'NFCORE_RNASEQ:PREPARE_GENOME:PARABRICKS_STARGENOMEGENERATE' {\n"
            "    cpus = 8\n"
            "    memory = 30.GB\n"
            "    time = 2.h\n"
            "  }\n"
            "  withName: 'NFCORE_RNASEQ:RNASEQ:ALIGN_STAR:PARABRICKS_RNA_FQ2BAM' {\n"
            "    cpus = 8\n"
            "    memory = 30.GB\n"
            "    time = 2.h\n"
            "  }\n"
        )
    if workflow.workflow_backend == HARAKO_NATIVE_V1:
        result = dict(dict(plan.get("capability_snapshot") or {}).get("result") or {})
        contract = select_resource_contract(
            str(result.get("host_profile_id")), str(result.get("reference_pack_id")),
            str(plan.get("alignment_profile_id")),
        )
        if contract is None or contract.contract_id != resource_contract_id:
            raise ValueError("Harako-native resource contract identity mismatch")
        return (
            "// Harako-native v1 fixed, offline execution configuration.\n"
            "docker.enabled = true\n"
            "docker.pullPolicy = 'never'\n"
            f"process.containerOptions = '{gpu_options}'\n"
            "process {\n"
            "  withName: 'PARABRICKS_RNA_FQ2BAM' {\n"
            f"    cpus = {contract.cpus}\n"
            f"    memory = {contract.memory_gb}.GB\n"
            "    time = 12.h\n"
            "  }\n"
            "}\n"
        )
    return (
        "// Harako-GPU execution adapter v1: fixed alignment-only stage.\n"
        f"params.gpu_container_options = '{gpu_options}'\n"
        "docker.enabled = true\n"
        "process {\n"
        "  withName: 'NFCORE_RNASEQ:RNASEQ:QUANTIFY_BAM_SALMON:SALMON_QUANT' { ext.when = false }\n"
        "  withName: 'NFCORE_RNASEQ:RNASEQ:QUANTIFY_PSEUDO_ALIGNMENT:SALMON_QUANT' { ext.when = false }\n"
        f"{resource_limits}"
        "}\n"
    )


def _nextflow_argv(
    *, executable: str, pipeline: str, run_dir: str, work_dir: str,
    run_id: str, resume: bool = False, profile: str | None = "docker",
) -> tuple[str, ...]:
    argv = [executable, "run", pipeline]
    if profile is not None:
        argv.extend(("-profile", profile))
    argv.extend([
        "-params-file", f"{run_dir}/frozen/params.json", "-c", f"{run_dir}/frozen/nextflow.config",
        "-work-dir", work_dir, "-with-report", f"{run_dir}/execution/current-report.html",
        "-with-timeline", f"{run_dir}/execution/current-timeline.html",
        "-with-trace", f"{run_dir}/execution/current-trace.tsv",
        "-with-dag", f"{run_dir}/execution/current-dag.html", "-name", f"h-{run_id.lower()}",
    ])
    if resume:
        argv.append("-resume")
    return tuple(argv)


def _tasks(plan: Mapping[str, Any], selection: ModeSelection, command_identity: str,
           expected_images: Mapping[str, str]) -> tuple[TaskRecord, ...]:
    samples = [str(item["sample"]) for item in plan["samples"]]
    base = sha256_payload({"kind": "run-task-input-v1", "plan_id": plan["plan_id"]})
    quant_only = plan.get("execution_route") == "fastq_quantification_only"
    tasks = [TaskRecord("preflight", StageId.PREFLIGHT.value, None, None, base, command_identity, None)]
    if not quant_only:
        task_id = (
            "harako-native-alignment" if workflow_backend_for_plan(plan).workflow_backend == HARAKO_NATIVE_V1
            else "nfcore-alignment"
        )
        tasks.append(TaskRecord(task_id, StageId.NFCORE.value, None, None, base, command_identity, expected_images["parabricks"]))
    for sample in samples:
        if quant_only:
            tasks.append(TaskRecord(f"input-validation:{sample}", StageId.PREFLIGHT.value, sample, None, base, command_identity, None))
            tasks.append(TaskRecord(f"fastp:{sample}", StageId.NFCORE.value, sample, None, base, command_identity, FASTP_IMAGE_IDENTITY))
            tasks.append(TaskRecord(f"processed-fastq-validation:{sample}", StageId.ALIGNMENT_VALIDATION.value, sample, None, base, command_identity, None))
        else:
            tasks.append(TaskRecord(f"alignment-validation:{sample}", StageId.ALIGNMENT_VALIDATION.value, sample, None, base, command_identity, None))
        tasks.append(TaskRecord(f"salmon-primary:{sample}", StageId.SALMON_PRIMARY.value, sample,
                                selection.primary_profile_id, base, command_identity,
                                expected_images[selection.primary_profile_id]))
        if selection.secondary_profile_id:
            tasks.append(TaskRecord(f"salmon-secondary:{sample}", StageId.SALMON_SECONDARY.value, sample,
                                    selection.secondary_profile_id, base, command_identity,
                                    expected_images[selection.secondary_profile_id]))
        if not quant_only:
            tasks.append(TaskRecord(f"star-counts:{sample}", StageId.STAR_COUNTS.value, sample, None, base, command_identity, None))
    for profile_id in (selection.primary_profile_id, selection.secondary_profile_id):
        if profile_id:
            tasks.append(TaskRecord(f"matrices:{profile_id}", StageId.MATRICES.value, None, profile_id, base, command_identity, None))
    if selection.secondary_profile_id:
        tasks.append(TaskRecord("concordance", StageId.CONCORDANCE.value, None, None, base, command_identity, None))
    tasks.extend((TaskRecord("report", StageId.REPORT.value, None, None, base, command_identity, None),
                  TaskRecord("artifacts", StageId.ARTIFACTS.value, None, None, base, command_identity, None),
                  TaskRecord("terminal", StageId.TERMINAL.value, None, None, base, command_identity, None)))
    return tuple(tasks)


def _prerequisite_applies(code: str, requirements: RuntimeRequirements) -> bool:
    if not requirements.requires_gpu and code in {
        "GPU_UNAVAILABLE",
        "WSL_GPU_UNAVAILABLE",
        "DOCKER_GPU_ACCESS_UNAVAILABLE",
        "GPU_CONTAINER_TEST_NOT_RUN",
        "PARABRICKS_HOST_MEMORY_BELOW_RECOMMENDED",
        "NVIDIA_SMI_PATH_NOT_EXPORTED",
    }:
        return False
    if "parabricks" not in requirements.required_image_roles and code == "PARABRICKS_IMAGE_UNAVAILABLE":
        return False
    if not requirements.requires_java and code.startswith("JAVA_"):
        return False
    if not requirements.requires_nextflow and code.startswith("NEXTFLOW_"):
        return False
    if not requirements.requires_nfcore_pipeline and code == "NF_CORE_CLI_UNAVAILABLE":
        return False
    return True


def validate_offline_runtime_closure(
    requirements: RuntimeRequirements, context: PreparationContext,
) -> dict[str, str]:
    """Validate installed high-memory receipts before any run-directory mutation."""
    expected_images = dict(ALL_IMAGE_IDENTITIES)
    for role in requirements.required_image_roles:
        overlay = runtime_quantification_image_contract(requirements.host_profile_id, role)
        if overlay is not None:
            expected_images[role] = overlay.identity
    if not requirements.requires_offline_closure:
        return expected_images
    if not all((context.host_receipt, context.task_image_inspections,
                context.parabricks_provenance, context.parabricks_image_inspection)):
        raise ValueError("Ubuntu high-memory prepare requires installed host/image provenance receipts")
    context.host_receipt.validate(report_root=context.repository_root / "docs/qualification")
    if requirements.requires_nf_schema:
        if context.plugin_receipt is None:
            raise ValueError("Ubuntu high-memory prepare requires installed host/plugin/image provenance receipts")
        context.plugin_receipt.validate()
        validate_task_image_closure(context.task_image_inspections)
    else:
        for role in requirements.required_image_roles:
            if role == "parabricks":
                continue
            contract = _native_runtime_image_contract(requirements, role)
            try:
                inspection = context.task_image_inspections[contract.reference]
            except KeyError as exc:
                raise ValueError(f"Harako-native image closure is missing {role}") from exc
            canonical_image_identity(contract, inspection)
    context.parabricks_provenance.validate(
        observed_image=context.parabricks_image_inspection,
        expected_receipt_sha256=context.host_receipt.parabricks_provenance_receipt_sha256,
        expected_archive_sha256=context.host_receipt.parabricks_archive_sha256,
    )
    expected_images.update({
        role: (
            context.parabricks_provenance.config_image_id
            if role == "parabricks" else _native_runtime_image_contract(requirements, role).identity
        )
        for role in requirements.required_image_roles
    })
    return expected_images


def prepare_run(*, plan_path: Path, runtime_root: str, context: PreparationContext,
                now: datetime | None = None) -> PreparedRun:
    plan_source = plan_path.expanduser().resolve()
    validate_plan_file(plan_source)
    plan = json.loads(plan_source.read_text(encoding="utf-8"))
    requirements = runtime_requirements_for_plan(plan)
    quant_only = plan.get("execution_route") == "fastq_quantification_only"
    runtime_root = require_safe_linux_runtime_path(runtime_root)
    output_root = require_safe_linux_runtime_path(str(plan["output_root"]))
    work_root = require_safe_linux_runtime_path(str(plan["work_root"]))
    if not output_root.startswith(runtime_root + "/") or not work_root.startswith(runtime_root + "/"):
        raise ValueError("Plan output/work roots must remain inside the declared runtime root")
    runtime_boundary = _linux_path(runtime_root, context)
    ensure_within(_linux_path(output_root, context), runtime_boundary)
    ensure_within(_linux_path(work_root, context), runtime_boundary)
    expected_images = validate_offline_runtime_closure(requirements, context)
    missing_roles = [
        role for role in requirements.required_image_roles
        if role not in context.observed_image_ids
    ]
    if missing_roles:
        raise ValueError("Required runtime image unavailable: " + ", ".join(missing_roles))
    mismatched_roles = [
        role for role in requirements.required_image_roles
        if context.observed_image_ids[role] != expected_images[role]
    ]
    if mismatched_roles:
        raise ValueError("Required runtime image identity mismatch: " + ", ".join(mismatched_roles))
    raw_bytes = 0
    for sample in plan.get("samples", []):
        for role in ("fastq_1", "fastq_2"):
            path = sample.get(role)
            if path:
                candidate = _linux_path(str(path), context)
                if not candidate.is_file():
                    raise ValueError(f"Raw FASTQ is missing: {sample.get('sample')}/{role}")
                raw_bytes += candidate.stat().st_size
    expected_disk_bytes = max(5 * 1024**3, raw_bytes * (6 if quant_only else 100))
    wsl_resources = dict(context.hardware_report.get("support_details", {}).get("wsl_resources") or {})
    available_work_bytes = int(wsl_resources.get("work_root_free_bytes") or context.hardware_report.get("disk", {}).get("free_bytes") or 0)
    if available_work_bytes < expected_disk_bytes:
        raise ValueError(f"Insufficient work disk: need {expected_disk_bytes}, observed {available_work_bytes}")
    blockers = [item for item in context.hardware_report.get("prerequisites", [])
                if item.get("active") and item.get("severity") == "hard_blocker"
                and item.get("code") != "WSL_WORK_ROOT_SCRATCH_INSUFFICIENT"
                and _prerequisite_applies(str(item.get("code")), requirements)]
    if blockers:
        raise ValueError("Runtime doctor has hard blockers: " + ", ".join(str(item.get("code")) for item in blockers))
    selection = ModeSelection.create(AnalysisMode(str(plan["quantification"]["mode"])),
                                     str(plan["quantification"]["primary_profile_id"]))
    indices = _index_contracts(plan, selection, context)
    reference = dict(plan["reference"])
    for role in ("fasta_path", "gtf_path", "transcript_fasta_path"):
        value = reference.get(role)
        if value and not _linux_path(str(value), context).is_file():
            raise ValueError(f"Reference input is missing: {role}")
    if sha256_path(_linux_path(reference["fasta_path"], context)) != reference["fasta_sha256"]:
        raise ValueError("Reference FASTA identity mismatch")
    if sha256_path(_linux_path(reference["gtf_path"], context)) != reference["gtf_sha256"]:
        raise ValueError("Reference GTF identity mismatch")
    gtf_path = _linux_path(reference["gtf_path"], context)
    if gtf_path.suffix == ".gz":
        with gzip.open(gtf_path, "rt", encoding="utf-8") as handle:
            gtf_text = handle.read()
    else:
        gtf_text = gtf_path.read_text(encoding="utf-8")
    transcript_to_gene = parse_transcript_gene_map(gtf_text)
    tx2gene_text = "transcript_id\tgene_id\n" + "".join(
        f"{transcript}\t{gene}\n" for transcript, gene in sorted(transcript_to_gene.items())
    )
    tx2gene_sha = hashlib.sha256(tx2gene_text.encode("utf-8")).hexdigest()
    run_id = _run_id(str(plan["plan_id"]), now)
    run_dir_linux = f"{output_root}/{plan['project_slug']}/{run_id}"
    work_dir_linux = f"{work_root}/{run_id}"
    run_dir = _linux_path(run_dir_linux, context)
    if run_dir.exists():
        raise ValueError("Run directory already exists")
    run_dir.mkdir(parents=True)
    work_dir = _linux_path(work_dir_linux, context)
    if work_dir.exists():
        raise ValueError("Run-specific work directory already exists")
    work_dir.mkdir(parents=True)
    for relative in (
        "frozen", "execution/attempts", "tasks", "results/quantification", "results/preprocessing/fastp",
        "results/matrices", "results/concordance", "results/reports", "artifacts", "support",
    ):
        (run_dir / relative).mkdir(parents=True)
    workflow = workflow_backend_for_plan(plan)
    pipeline_name = (
        "harako-native-v1" if workflow.workflow_backend == HARAKO_NATIVE_V1
        else "nf-core-rnaseq-3.26.0"
    )
    pipeline_linux = f"{run_dir_linux}/pipeline/{pipeline_name}"
    (run_dir / "pipeline").mkdir()
    if not quant_only:
        if workflow.workflow_backend == HARAKO_NATIVE_V1:
            if not context.execution.is_native_linux:
                raise ValueError("Harako-native launch remains guarded to native Linux product verification")
            native_source = (context.repository_root / "pipelines/harako-native-v1").resolve()
            _copy_pipeline(str(native_source), pipeline_linux, context)
        else:
            _copy_pipeline(context.pipeline_source_linux, pipeline_linux, context)
            if _git_head(pipeline_linux, context) != PIPELINE_COMMIT:
                raise ValueError("Resolved pipeline commit mismatch")
    patch_manifest_path = context.repository_root / "patches/nf-core-rnaseq-3.26.0/manifest.json"
    patch_path = context.repository_root / "patches/nf-core-rnaseq-3.26.0/parabricks-logfile-separation.patch"
    reference_pipeline = workflow.workflow_backend == NFCORE_REFERENCE
    patch_manifest = ({"schema_version": 1, "applicability": "NOT_APPLICABLE"} if quant_only or not reference_pipeline
                      else load_patch_manifest(patch_manifest_path))
    patch_state = ("NOT_APPLICABLE" if quant_only or not reference_pipeline else verify_patch_state(
        _linux_path(pipeline_linux, context), patch_manifest,
        resolved_commit=PIPELINE_COMMIT, patch_path=patch_path))
    if not quant_only and reference_pipeline and patch_state != "PATCHED":
        raise ValueError("Pipeline snapshot does not contain the qualified compatibility patch")
    index_patch_manifest_path = context.repository_root / "patches/nf-core-rnaseq-3.26.0/prebuilt-star-index-manifest.json"
    index_patch_path = context.repository_root / "patches/nf-core-rnaseq-3.26.0/parabricks-prebuilt-star-index.patch"
    index_patch_manifest = ({"schema_version": 1, "applicability": "NOT_APPLICABLE"} if quant_only or not reference_pipeline
                            else load_patch_manifest(index_patch_manifest_path))
    index_patch_state = ("NOT_APPLICABLE" if quant_only or not reference_pipeline else verify_patch_state(
        _linux_path(pipeline_linux, context), index_patch_manifest,
        resolved_commit=PIPELINE_COMMIT, patch_path=index_patch_path))
    if not quant_only and reference_pipeline and index_patch_state != "PATCHED":
        raise ValueError("Pipeline snapshot does not contain the qualified prebuilt-index patch")
    inventory, inventory_sha = (([], sha256_payload({"pipeline": "NOT_APPLICABLE"})) if quant_only
                                else tree_inventory(_linux_path(pipeline_linux, context)))
    if not quant_only:
        _freeze_pipeline(pipeline_linux, context)
    original_params = json.loads((plan_source.parent / "nf-params.json").read_text(encoding="utf-8"))
    if quant_only:
        params = {"execution_route": "fastq_quantification_only"}
        nextflow_argv = ("harako-fixed-route", "fastq_quantification_only")
        command_spec = CommandSpec(nextflow_argv, run_dir_linux, {}, f"{run_dir_linux}/execution/linux.pid")
    else:
        params = _alignment_params(plan, original_params, run_dir=run_dir_linux, work_dir=work_dir_linux)
        nextflow_argv = _nextflow_argv(
            executable=context.nextflow_executable, pipeline=pipeline_linux,
            run_dir=run_dir_linux, work_dir=work_dir_linux, run_id=run_id,
            profile=None if workflow.workflow_backend == HARAKO_NATIVE_V1 else "docker",
        )
        command_env = {
            "NXF_VER": NEXTFLOW_VERSION, "NXF_HOME": f"{run_dir_linux}/.nextflow",
            "NXF_ANSI_LOG": "false",
        }
        if requirements.requires_offline_closure:
            command_env["NXF_OFFLINE"] = "true"
            if requirements.requires_nf_schema:
                command_env["NXF_PLUGINS_DIR"] = str(Path.home() / ".nextflow/plugins")
        if context.execution.is_native_linux:
            command_env["PATH"] = os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")
        command_spec = CommandSpec(nextflow_argv, run_dir_linux, command_env,
                                   f"{run_dir_linux}/execution/linux.pid")
    indices_by_id = {index.profile_id: index for index in indices}
    tx2gene_linux = f"{run_dir_linux}/frozen/tx2gene.tsv"
    commands = {
        profile_id: salmon_argv(profile_id, index=indices_by_id[profile_id].path,
                                gene_map=tx2gene_linux, r1="<PROCESSED_R1>", r2="<PROCESSED_R2>",
                                output=f"{run_dir_linux}/results/quantification/{profile_id}/<SAMPLE>",
                                library_type=str(plan["quantification"]["explicit_library_type"]))
        for profile_id in indices_by_id
    }
    preprocessing_contract = str(plan.get("processed_fastq_contract") or (
        "harako-fastp-1.0.1-fixed-v1" if quant_only
        else "nfcore-rnaseq-3.26.0-fastp-fixed-v1"
    ))
    series_payload = {
        "schema_version": 1, "project_id": plan["project_slug"], "selection": asdict(selection),
        "reference_pack_id": reference["reference_pack_id"], "fasta_sha256": reference["fasta_sha256"],
        "gtf_sha256": reference["gtf_sha256"], "tx2gene_sha256": tx2gene_sha,
        "preprocessing_contract_id": preprocessing_contract,
        "raw_samples": plan["samples"], "processed_fastq_state": "CAPTURE_PER_TASK_AFTER_PREPROCESSING",
        "indices": [asdict(item) for item in indices], "commands": {key: list(value) for key, value in commands.items()},
        "created_at": (now or datetime.now(UTC)).isoformat(), "series_status": "immutable",
        "alignment_profile_id": plan["alignment_profile_id"],
        "alignment_profile": plan["alignment_profile"],
        "workflow_backend": workflow.workflow_backend,
        "alignment_backend": plan.get("alignment_backend", "none" if quant_only else "parabricks_star"),
        "execution_route": plan["execution_route"], "bam_output_mode": plan["bam_output_mode"],
    }
    analysis_series_id = sha256_payload({"kind": "harako-analysis-series-execution-v1", "payload": series_payload})
    plan_sha = sha256_path(plan_source)
    samplesheet_source = plan_source.parent / "nf-samplesheet.csv"
    samplesheet_sha = sha256_path(samplesheet_source)
    identity = RunIdentity(
        run_id, plan["project_slug"], plan["plan_id"], plan["approval_hash"], analysis_series_id,
        selection.primary_profile_id, selection.secondary_profile_id, selection.mode.value,
        reference["reference_pack_id"], reference["fasta_sha256"], reference["gtf_sha256"],
        tx2gene_sha, samplesheet_sha, preprocessing_contract,
        ("harako-native-v1" if workflow.workflow_backend == HARAKO_NATIVE_V1 else "3.26.0"),
        (inventory_sha if workflow.workflow_backend == HARAKO_NATIVE_V1 else PIPELINE_COMMIT),
        NEXTFLOW_VERSION, expected_images["parabricks"] if not quant_only else "NOT_APPLICABLE",
        sha256_payload({"compatibility": {"manifest": patch_manifest, "state": patch_state},
                        "prebuilt_star_index": {"manifest": index_patch_manifest, "state": index_patch_state}}),
        {
            profile_id: (
                runtime_quantification_image_contract(requirements.host_profile_id, profile_id).identity
                if runtime_quantification_image_contract(requirements.host_profile_id, profile_id)
                else get_profile(profile_id).image_identity
            )
            for profile_id in indices_by_id
        },
        {item.profile_id: item.index_id for item in indices},
        "NOT_APPLICABLE" if quant_only else GENECOUNTS_CONTRACT,
        utc_now(), context.execution.identity, output_root, work_dir_linux, run_dir_linux,
        alignment_profile_id=str(plan["alignment_profile_id"]),
        two_pass=bool(plan["alignment_profile"].get("two_pass", False)),
        annotation_backed=bool(plan["alignment_profile"].get("annotation_backed", False)),
        alignment_profile_limitations=tuple(plan["alignment_profile"].get("limitations", ())),
        execution_route=str(plan["execution_route"]), bam_output_mode=str(plan["bam_output_mode"]),
        gpu_used=not quant_only,
        workflow_backend=workflow.workflow_backend,
        alignment_backend=str(plan.get("alignment_backend") or ("none" if quant_only else "parabricks_star")),
        output_artifact_contract=str(plan.get("output_artifact_contract") or "harako-backend-output-manifest-v1"),
    )
    frozen: dict[str, str] = {
        "plan.json": plan_source.read_text(encoding="utf-8"),
        "approval-contract.json": json.dumps({"schema_version": 1, "approval_hash": plan["approval_hash"],
                                                "plan_id": plan["plan_id"], "plan_sha256": plan_sha,
                                                "expected_disk_bytes": expected_disk_bytes,
                                                "available_work_bytes": available_work_bytes}, indent=2, sort_keys=True) + "\n",
        "nf-samplesheet.csv": samplesheet_source.read_text(encoding="utf-8"),
        "normalized-samplesheet.csv": samplesheet_source.read_text(encoding="utf-8"),
        "reference-manifest.json": json.dumps(reference, indent=2, sort_keys=True) + "\n",
        "backend-profile.json": json.dumps(plan["backend_profile"], indent=2, sort_keys=True) + "\n",
        "workflow-backend.json": json.dumps({
            "schema_version": 1,
            "workflow_backend": workflow.workflow_backend,
            "alignment_backend": plan.get("alignment_backend"),
            "processed_fastq_contract": preprocessing_contract,
            "output_artifact_contract": plan.get("output_artifact_contract"),
            "runtime_image_closure": plan.get("runtime_image_closure"),
            "resource_contract_id": plan.get("resource_contract_id"),
        }, indent=2, sort_keys=True) + "\n",
        "alignment-profile.json": json.dumps(plan["alignment_profile"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        "quantification-profiles.json": json.dumps(plan["quantification"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        "analysis-series.json": json.dumps({**series_payload, "analysis_series_id": analysis_series_id}, indent=2, sort_keys=True) + "\n",
        "tx2gene.tsv": tx2gene_text,
        "params.json": json.dumps(params, indent=2, sort_keys=True) + "\n",
        "nextflow.config": "// NOT_APPLICABLE: fixed FASTQ quantification-only route\n" if quant_only else _execution_config(plan),
        "command-preview.txt": " ".join(nextflow_argv) + "\n",
        "environment.json": json.dumps(command_spec.env, indent=2, sort_keys=True) + "\n",
        "hardware-report.json": json.dumps(context.hardware_report, indent=2, sort_keys=True) + "\n",
        "runtime-requirements.json": json.dumps({
            "schema_version": 1,
            **requirements.as_dict(),
            "observed_image_ids": {
                role: context.observed_image_ids[role] for role in requirements.required_image_roles
            },
            "image_contracts": {
                role: {
                    "role": role,
                    "image_reference": (
                        context.parabricks_provenance.source_reference
                        if requirements.requires_offline_closure and role == "parabricks"
                        else _runtime_image_contract(requirements, role).reference
                    ),
                    "identity_kind": _runtime_image_contract(requirements, role).identity_kind,
                    "expected_identity": expected_images[role],
                    "observed_canonical_identity": context.observed_image_ids[role],
                }
                for role in requirements.required_image_roles
            },
            "not_applicable_findings": [
                str(item.get("code")) for item in context.hardware_report.get("prerequisites", [])
                if item.get("active") and not _prerequisite_applies(str(item.get("code")), requirements)
            ],
        }, indent=2, sort_keys=True) + "\n",
        "pipeline-manifest.json": json.dumps({"schema_version": 1,
                                                "workflow_backend": workflow.workflow_backend,
                                                "commit": "NOT_APPLICABLE" if quant_only else (
                                                    inventory_sha if workflow.workflow_backend == HARAKO_NATIVE_V1 else PIPELINE_COMMIT
                                                ),
                                                "inventory_sha256": inventory_sha, "inventory": inventory}, indent=2, sort_keys=True) + "\n",
        "patch-manifest.json": json.dumps({**patch_manifest, "observed_state": patch_state}, indent=2, sort_keys=True) + "\n",
        "prebuilt-star-index-patch-manifest.json": json.dumps(
            {**index_patch_manifest, "observed_state": index_patch_state}, indent=2, sort_keys=True
        ) + "\n",
        "versions.tsv": (
            "component\tversion_or_identity\nNextflow\tNOT_APPLICABLE\nworkflow_backend\tNOT_APPLICABLE\nParabricks\tNOT_APPLICABLE\nfastp\t1.0.1\n"
            if quant_only else
            f"component\tversion_or_identity\nNextflow\t25.04.3\nworkflow_backend\t{workflow.workflow_backend}\nParabricks\t4.6.0-1\n"
        ),
        "paths.tsv": (
            f"role\tlinux_path\nRUN_DIR\t{run_dir_linux}\nWORK_DIR\t{work_dir_linux}\n"
            + ("" if quant_only else f"PIPELINE\t{pipeline_linux}\n")
        ),
    }
    if requirements.requires_bam_validation:
        frozen["runtime-validation-images.json"] = json.dumps(
            bam_validator_freeze_payload(requirements.host_profile_id),
            indent=2,
            sort_keys=True,
        ) + "\n"
    for name, content in frozen.items():
        write_new_text(run_dir / "frozen" / name, content)
    if context.execution.is_wsl2:
        shutil.copy2(context.repository_root / "scripts/wsl_exec_runner.py", run_dir / "frozen/wsl_exec_runner.py")
    write_command_spec(run_dir / "frozen/command.json", command_spec)
    frozen_inventory, frozen_sha = tree_inventory(run_dir / "frozen", exclude_names=frozenset({"manifest.json"}))
    write_new_text(
        run_dir / "frozen/manifest.json",
        json.dumps({"schema_version": 1, "inventory_sha256": frozen_sha,
                    "inventory": frozen_inventory}, indent=2, sort_keys=True) + "\n",
    )
    write_new_text(run_dir / "run.json", json.dumps({"schema_version": 1, "identity": identity.as_dict()}, indent=2, sort_keys=True) + "\n")
    store = RunStateStore(run_dir)
    store.write_status(RunStatus(run_id, RunState.PREPARED, None, None, None, utc_now(),
                                 resumable=False, warnings=tuple(plan.get("warnings") or ()),
                                 next_actions=("run start",)))
    store.write_tasks(_tasks(plan, selection, command_spec.argv_sha256, expected_images))
    return PreparedRun(run_id, run_dir_linux, run_dir, plan["approval_hash"],
                       selection.primary_profile_id, selection.secondary_profile_id)
