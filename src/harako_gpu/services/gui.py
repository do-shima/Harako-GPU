"""Application-service façade for the local reference-aware GUI.

This module contains no Streamlit or subprocess dependency. It delegates every
scientific decision to the existing capability, planning, run, and artifact
services.
"""

from __future__ import annotations

import csv
import json
import platform
import shutil
import time
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from harako_gpu.adapters.execution_context import NATIVE_LINUX, require_native_linux_host
from harako_gpu.adapters.filesystem import (
    ensure_within, require_safe_linux_runtime_path, sha256_path, write_new_text,
)
from harako_gpu.adapters.gui_launcher import LaunchedController, controller_argv, launch_controller
from harako_gpu.adapters.host_paths import host_path_from_linux
from harako_gpu.core.capabilities import CAPABILITY_MATRIX_VERSION, BamOutputMode, CapabilityResult
from harako_gpu.core.contracts import BamRetention, MemoryMode, QualificationDebugMode
from harako_gpu.core.samples import validate_samples
from harako_gpu.services.artifacts import list_artifacts, verify_artifacts
from harako_gpu.services.capabilities import (
    CURRENT_HOST_PROFILE_ID, FULL_HUMAN_REFERENCE_PACK_ID, FULL_HUMAN_SHA,
    SMALL_REFERENCE_PACK_ID, SMALL_REFERENCE_SHA, evaluate_capability, write_handoff,
)
from harako_gpu.services.host_profiles import (
    TERMINAL_RESULTS_ARCHIVE_POLICY,
    UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
    WINDOWS_HOST_PROFILE_ID,
    HostQualificationReceipt,
    OfflinePlatformImageProvenance,
    get_host_profile,
    installed_host_receipt_path,
    select_resource_contract,
)
from harako_gpu.services.input_inspection import inspect_input
from harako_gpu.services.planning import PROJECT_RE, create_plan, validate_plan_file
from harako_gpu.services.preflight import collect_preflight
from harako_gpu.services.quantification_profiles import (
    AnalysisMode, SALMON_1103_ID, SALMON_251_ID, ModeSelection, visible_profiles,
)
from harako_gpu.services.run_execution import verify_frozen
from harako_gpu.services.run_preparation import (
    PreparationContext,
    build_native_linux_preparation_context,
    build_wsl_preparation_context,
    prepare_run,
    runtime_requirements_for_plan,
    runtime_requirements_for_plan_file,
    validate_offline_runtime_closure,
)
from harako_gpu.services.run_state import RunStateStore
from harako_gpu.services.run_status import inspect_run, status_payload
from harako_gpu.services.support_bundle import create_support_bundle
from harako_gpu.services.workflow_backends import (
    HARAKO_NATIVE_V1,
    NFCORE_REFERENCE,
    harako_native_parity_evidence_valid,
    parse_workflow_backend,
)


GUI_CONTRACT_VERSION = "reference-aware-gui-v1"
POLL_ATTEMPTS = 6
POLL_BACKOFF_SECONDS = 0.05
PRODUCT_CLI_QUALIFICATION_EVIDENCE = (
    (
        "ubuntu-high-memory-product-cli-smoke.md",
        "f28c62d126448c6a67b137b4cd52f41f300c4323f608da553532ab6122b83bc1",
    ),
    (
        "ubuntu-high-memory-product-cli-smoke.json",
        "a91b80256223499de61090ad68b60b42e0dd0038cfdc7d35697ab79b9b3798e7",
    ),
)
PRODUCT_CLI_QUALIFIED_RECEIPT_SHA256 = (
    "edef6fdba77cb62b0aac3debf9e624acea97d3c75be48932653f9cb0051d5c47"
)


def product_cli_qualification_evidence_valid(
    *, receipt_path: Path, qualification_report_root: Path | None = None,
) -> bool:
    """Validate immutable CLI qualification evidence without rewriting its host receipt."""
    root = qualification_report_root or (
        Path(__file__).resolve().parents[3] / "docs/qualification"
    )
    try:
        for name, expected in PRODUCT_CLI_QUALIFICATION_EVIDENCE:
            if sha256_path(root / name) != expected:
                return False
        if sha256_path(receipt_path) != PRODUCT_CLI_QUALIFIED_RECEIPT_SHA256:
            return False
        report = json.loads(
            (root / "ubuntu-high-memory-product-cli-smoke.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(report, dict):
        return False
    p1 = report.get("p1") or {}
    p2 = report.get("p2") or {}
    reference = report.get("reference") or {}
    return (
        report.get("classification") == "PUBLIC_PRODUCT_CLI_ONE_PASS_TWO_PASS_QUALIFIED"
        and report.get("host_profile_id") == UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID
        and report.get("host_receipt_sha256") == PRODUCT_CLI_QUALIFIED_RECEIPT_SHA256
        and report.get("manual_scientific_override") is False
        and reference.get("pack_id") == FULL_HUMAN_REFERENCE_PACK_ID
        and reference.get("star_index_id") == "star-2.7.2a-c15a9d6fe6df9716"
        and reference.get("salmon_2_5_1_index_id") == "salmon-2.5.1-1c037278d376f40f"
        and p1.get("state") == "COMPLETED"
        and p1.get("alignment_profile_id") == "parabricks_star_one_pass_workstation"
        and (p1.get("resource_contract") or {}).get("id")
        == "ubuntu_native_rtx3090_ram128_one_pass_42gb_v1"
        and p1.get("artifact_deep_verification") == "PASS"
        and (p1.get("support_bundle") or {}).get("status") == "PASS"
        and p2.get("state") == "COMPLETED"
        and p2.get("alignment_profile_id") == "parabricks_star_two_pass_high_memory"
        and (p2.get("resource_contract") or {}).get("id")
        == "ubuntu_native_rtx3090_ram128_two_pass_96gb_v1"
        and p2.get("artifact_deep_verification") == "PASS"
        and (p2.get("support_bundle") or {}).get("status") == "PASS"
    )


@dataclass(frozen=True)
class ReferenceOption:
    reference_pack_id: str
    display_name: str
    species: str
    assembly: str
    annotation_provider: str
    annotation_release: str
    resource_class: str
    transcript_count: int | None
    gene_count: int | None
    source: str
    qualification_status: str
    cached_assets: bool
    reference_assets_cached: bool
    star_index_cached: bool
    salmon_251_index_cached: bool
    salmon_1103_index_cached: bool
    fasta_linux: str
    gtf_linux: str
    transcript_fasta_linux: str
    legacy_index_manifest_linux: str
    salmon_251_manifest_linux: str
    salmon_1103_manifest_linux: str
    star_index_linux: str | None
    star_sjdb_overhang: int | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GuiDraft:
    project_slug: str
    samples: tuple[Mapping[str, str], ...]
    reference_pack_id: str
    bam_output_mode: str
    alignment_profile_id: str
    quantification_mode: str
    primary_profile_id: str
    explicit_library_type: str
    runtime_root: str
    output_root: str
    work_root: str
    distribution: str = "Ubuntu"
    execution_context: str = "wsl2:Ubuntu"
    host_profile_id: str = WINDOWS_HOST_PROFILE_ID
    workflow_backend: str = NFCORE_REFERENCE
    nextflow_executable: str | None = None


@dataclass(frozen=True)
class GuiPreparedRun:
    plan_id: str
    approval_hash: str
    run_id: str
    run_directory: str
    analysis_series_id: str
    capability: Mapping[str, Any]
    plan_path: str


@dataclass(frozen=True)
class GuiScientificLaunchEligibility:
    allowed: bool
    execution_context: str
    detected_host_profile_id: str
    host_receipt_status: str
    capability_status: str
    workflow_backend: str
    alignment_profile_id: str
    resource_contract_id: str | None
    asset_readiness: Mapping[str, Any]
    storage_readiness: Mapping[str, Any]
    blocker_code: str | None
    blocker_explanation: str
    limitations: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def matches(self, draft: GuiDraft) -> bool:
        assets = self.asset_readiness
        return (
            self.execution_context == draft.execution_context
            and self.detected_host_profile_id == draft.host_profile_id
            and self.workflow_backend == draft.workflow_backend
            and self.alignment_profile_id == draft.alignment_profile_id
            and assets.get("reference_pack_id") == draft.reference_pack_id
            and assets.get("quantification_mode") == draft.quantification_mode
            and assets.get("primary_profile_id") == draft.primary_profile_id
        )


def _genuine_native_linux(*, host_system: str | None = None,
                          kernel_release: str | None = None) -> bool:
    system = host_system or platform.system()
    release = kernel_release or platform.release()
    return system == "Linux" and "microsoft" not in release.casefold()


def gui_environment_defaults(*, host_system: str | None = None,
                             kernel_release: str | None = None) -> dict[str, str]:
    if _genuine_native_linux(host_system=host_system, kernel_release=kernel_release):
        return {
            "execution_context": NATIVE_LINUX,
            "host_profile_id": UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
            "workflow_backend": HARAKO_NATIVE_V1,
        }
    return {
        "execution_context": "wsl2:Ubuntu",
        "host_profile_id": WINDOWS_HOST_PROFILE_ID,
        "workflow_backend": NFCORE_REFERENCE,
    }


def _host(linux_path: str, distribution: str,
          execution_context: str | None = None) -> Path:
    if execution_context == NATIVE_LINUX or (
        execution_context is None and _genuine_native_linux()
    ):
        return Path(require_safe_linux_runtime_path(linux_path))
    return host_path_from_linux(linux_path, distribution=distribution)


def reference_catalog(*, runtime_root: str, distribution: str = "Ubuntu",
                      execution_context: str | None = None) -> tuple[ReferenceOption, ...]:
    root = require_safe_linux_runtime_path(runtime_root)
    human_assets = f"{root}/capacity/references/human_grch38p14_gencode49_harako_gpu_v1/assets"
    small_assets = f"{root}/references/nf-core-test-datasets-626c8fab/reference"
    human = ReferenceOption(
        FULL_HUMAN_REFERENCE_PACK_ID, "GRCh38.p14 / GENCODE 49", "Homo sapiens", "GRCh38.p14",
        "GENCODE", "49", "FULL_MAMMALIAN_HIGH_MEMORY", 533740, 78899, "GENCODE",
        "quantification-qualified; GPU BAM unsupported on current host", True, True, True, True, True,
        f"{human_assets}/GRCh38.primary_assembly.genome.fa",
        f"{human_assets}/gencode.v49.primary_assembly.annotation.gtf",
        f"{human_assets}/gencode.v49.transcript_targets.fa",
        f"{root}/capacity/plans/C1_1M/legacy-salmon-index-manifest.json",
        f"{root}/capacity/plans/C1_1M/salmon_2_5_1_deterministic-index.json",
        f"{root}/capacity/plans/C1_1M/salmon_1_10_3_compatibility-index.json",
        f"{root}/capacity/indices/star-2.7.2a", 74,
    )
    small = ReferenceOption(
        SMALL_REFERENCE_PACK_ID, "WT_REP1 exact small reference", "Homo sapiens", "test-mini",
        "nf-core-test-datasets", "626c8fab", "SMALL_REFERENCE_QUALIFIED", None, None,
        "nf-core test datasets", "GPU BAM qualified", True, True, True, True, True,
        f"{small_assets}/genome.fasta", f"{small_assets}/genes_with_empty_tid.gtf.gz",
        f"{small_assets}/transcriptome.fasta",
        f"{root}/independent-fastq-salmon/manifests/candidate-a-v2/salmon-index-manifest.json",
        f"{root}/plans/execution-adapter-qualification/compare-both/salmon_2_5_1_deterministic-index.json",
        f"{root}/plans/execution-adapter-qualification/compare-both/salmon_1_10_3_compatibility-index.json",
        f"{root}/metrics-compatibility/results/corrected/genome/index/star", 100,
    )
    checked = []
    for item in (human, small):
        paths = (item.fasta_linux, item.gtf_linux, item.transcript_fasta_linux)
        cached = all(_host(path, distribution, execution_context).is_file() for path in paths)
        star_cached = item.star_index_linux is None or _host(
            item.star_index_linux, distribution, execution_context,
        ).is_dir()
        salmon_251_cached = _host(
            item.salmon_251_manifest_linux, distribution, execution_context,
        ).is_file()
        salmon_1103_cached = _host(
            item.salmon_1103_manifest_linux, distribution, execution_context,
        ).is_file()
        checked.append(ReferenceOption(**{
            **item.as_dict(), "cached_assets": cached and star_cached,
            "reference_assets_cached": cached, "star_index_cached": star_cached,
            "salmon_251_index_cached": salmon_251_cached,
            "salmon_1103_index_cached": salmon_1103_cached,
        }))
    return tuple(checked)


def get_reference(reference_pack_id: str, *, runtime_root: str,
                  distribution: str = "Ubuntu", quantification_mode: str | None = None,
                  primary_profile_id: str | None = None,
                  execution_context: str | None = None) -> ReferenceOption:
    matches = [item for item in reference_catalog(
        runtime_root=runtime_root, distribution=distribution,
        execution_context=execution_context,
    )
               if item.reference_pack_id == reference_pack_id]
    if len(matches) != 1:
        raise ValueError("Reference pack is not in the fixed GUI catalog")
    reference = matches[0]
    if not reference.cached_assets:
        raise ValueError("Fixed reference assets are not completely cached")
    if quantification_mode is not None:
        selection = ModeSelection.create(AnalysisMode(quantification_mode), primary_profile_id)
        required = {selection.primary_profile_id} | ({selection.secondary_profile_id} if selection.secondary_profile_id else set())
        if SALMON_251_ID in required and not reference.salmon_251_index_cached:
            raise ValueError("Selected Salmon 2.5.1 profile index is not cached")
        if SALMON_1103_ID in required and not reference.salmon_1103_index_cached:
            raise ValueError("Selected Salmon 1.10.3 profile index is not cached")
    return reference


def capability_for(*, reference_pack_id: str, bam_output_mode: str,
                   alignment_profile_id: str | None, quantification_mode: str,
                   primary_profile_id: str, runtime_root: str,
                   distribution: str = "Ubuntu",
                   host_profile_id: str = CURRENT_HOST_PROFILE_ID,
                   execution_context: str = "wsl2:Ubuntu",
                   host_receipt: HostQualificationReceipt | None = None,
                   parabricks_provenance: OfflinePlatformImageProvenance | None = None,
                   observed_parabricks_image: Mapping[str, Any] | None = None) -> CapabilityResult:
    reference = get_reference(
        reference_pack_id, runtime_root=runtime_root, distribution=distribution,
        execution_context=execution_context,
    )
    identity = ({**FULL_HUMAN_SHA, "reference_pack_id": reference_pack_id}
                if reference_pack_id == FULL_HUMAN_REFERENCE_PACK_ID
                else {**SMALL_REFERENCE_SHA, "reference_pack_id": reference_pack_id})
    mode = AnalysisMode(quantification_mode)
    selection = ModeSelection.create(mode, primary_profile_id)
    return evaluate_capability(
        reference=identity, bam_output_mode=BamOutputMode(bam_output_mode),
        alignment_profile_id=None if bam_output_mode == "none" else alignment_profile_id,
        quantification_mode=mode.value, primary_profile_id=selection.primary_profile_id,
        secondary_profile_id=selection.secondary_profile_id,
        host_profile_id=host_profile_id, execution_context=execution_context,
        host_receipt=host_receipt, parabricks_provenance=parabricks_provenance,
        observed_parabricks_image=observed_parabricks_image,
    )


def host_summary(*, runtime_root: str, execution_context: str = "wsl2:Ubuntu") -> dict[str, Any]:
    root = require_safe_linux_runtime_path(runtime_root)
    report = (
        collect_preflight(cwd=Path(root), wsl_work_root=root).as_dict()
        if execution_context == NATIVE_LINUX else
        collect_preflight(wsl_work_root=root).as_dict()
    )
    gpus = list(report.get("nvidia_gpus") or [])
    return {
        "host_profile_id": (
            UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID
            if execution_context == NATIVE_LINUX else CURRENT_HOST_PROFILE_ID
        ),
        "physical_ram_bytes": report.get("host_ram_bytes"),
        "wsl_ram_bytes": dict(report.get("support_details", {}).get("wsl_resources") or {}).get("total_memory_bytes"),
        "gpu": gpus[0] if gpus else None,
        "docker": report.get("docker", {}), "java": report.get("java", {}),
        "nextflow": report.get("nextflow", {}), "qualification_status": report.get("qualification_status"),
    }


def scan_fastqs(directory: str, *, layout: str, library_type: str,
                distribution: str = "Ubuntu") -> dict[str, Any]:
    if layout not in {"paired", "single"}:
        raise ValueError("Read layout must be paired or single")
    if library_type not in {"U", "ISF", "ISR"}:
        raise ValueError("Explicit library type U, ISF, or ISR is required")
    host_root = _host(directory, distribution) if directory.startswith("/") else Path(directory).resolve(strict=True)
    report = inspect_input(host_root)
    items = list(report["fastq_files"])
    by_sample: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_sample.setdefault(str(item["sample_suggestion"]), []).append(item)
    rows: list[dict[str, str]] = []
    errors = list(report.get("unresolved") or [])
    strandedness = {"U": "unstranded", "ISF": "forward", "ISR": "reverse"}[library_type]
    for sample, group in sorted(by_sample.items()):
        r1 = [item for item in group if item["read_side"] == "1"]
        r2 = [item for item in group if item["read_side"] == "2"]
        unknown = [item for item in group if item["read_side"] == "single"]
        if layout == "paired":
            if len(r1) != 1 or len(r2) != 1 or unknown:
                errors.append(f"Ambiguous or orphan paired FASTQ assignment for {sample}")
                continue
            first, second = r1[0], r2[0]
        else:
            candidates = unknown or r1
            if len(candidates) != 1 or r2:
                errors.append(f"Ambiguous single-end FASTQ assignment for {sample}")
                continue
            first, second = candidates[0], None
        def absolute(item: Mapping[str, Any]) -> str:
            path = ensure_within(host_root / str(item["path"]), host_root, require_exists=True)
            return str(path)
        rows.append({"sample": sample, "condition": sample, "fastq_1": absolute(first),
                     "fastq_2": absolute(second) if second else "", "strandedness": strandedness,
                     "library_protocol": "explicit_gui_selection"})
    validation = validate_samples(rows)
    errors.extend(validation.errors)
    if layout == "single":
        errors.append("Single-end discovery is available, but the current execution route is paired-end only")
    return {"schema_version": 1, "input_root": str(host_root), "rows": rows,
            "valid": not errors, "errors": sorted(set(errors)), "file_count": len(items)}


def validate_gui_samples(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    result = validate_samples(rows)
    return {"valid": not result.errors, "errors": list(result.errors)}


def project_slug_valid(value: str) -> bool:
    return PROJECT_RE.fullmatch(value) is not None


def discover_projects(output_root: str, *, distribution: str = "Ubuntu") -> dict[str, Any]:
    root = _host(output_root, distribution) if output_root.startswith("/") else Path(output_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Project output root does not exist")
    projects: dict[str, list[dict[str, Any]]] = {}
    for project_dir in sorted(path for path in root.iterdir() if path.is_dir() and not path.is_symlink()):
        for run_dir in sorted(path for path in project_dir.iterdir() if path.is_dir() and not path.is_symlink()):
            manifest = run_dir / "run.json"
            status = run_dir / "status.json"
            if not manifest.is_file() or not status.is_file():
                continue
            try:
                identity = json.loads(manifest.read_text(encoding="utf-8"))["identity"]
                state = json.loads(status.read_text(encoding="utf-8"))["state"]
            except (OSError, json.JSONDecodeError, KeyError):
                continue
            projects.setdefault(str(identity["project_slug"]), []).append({
                "run_id": identity["run_id"], "state": state,
                "reference_pack_id": identity["reference_pack_id"],
                "execution_route": identity.get("execution_route"), "run_directory": str(run_dir),
            })
    return {"schema_version": 1, "projects": [
        {"project_slug": key, "run_count": len(value), "last_run": value[-1], "runs": value}
        for key, value in sorted(projects.items())
    ]}


def _sample_csv(rows: Sequence[Mapping[str, str]]) -> str:
    columns = ("sample", "condition", "fastq_1", "fastq_2", "strandedness", "library_protocol")
    output = [",".join(columns)]
    for row in rows:
        values = [str(row.get(key) or "") for key in columns]
        if any(any(character in value for character in ',\n\r"') for value in values):
            raise ValueError("GUI sample values requiring CSV quoting are not supported")
        output.append(",".join(values))
    return "\n".join(output) + "\n"


def fixed_gui_debug_mode(reference_pack_id: str, bam_output_mode: str) -> QualificationDebugMode:
    """Reuse the exact small-reference BAM qualification mode; never apply it to human data."""
    if reference_pack_id == SMALL_REFERENCE_PACK_ID and bam_output_mode != BamOutputMode.NONE.value:
        return QualificationDebugMode.X3
    return QualificationDebugMode.DISABLED


def _requirements_for_draft(draft: GuiDraft) -> Any:
    route = "fastq_quantification_only" if draft.bam_output_mode == "none" else "gpu_bam_alignment"
    workflow = parse_workflow_backend(draft.workflow_backend)
    return runtime_requirements_for_plan({
        "execution_route": route,
        "workflow_backend": workflow.workflow_backend,
        "quantification": {
            "mode": draft.quantification_mode,
            "primary_profile_id": draft.primary_profile_id,
        },
        "capability_snapshot": {"result": {"host_profile_id": draft.host_profile_id}},
    })


def _mount_type(path: Path) -> str:
    resolved = path.resolve(strict=False)
    best: tuple[int, str] | None = None
    try:
        rows = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"Cannot inspect active-storage filesystem: {exc}") from exc
    for row in rows:
        fields = row.split(" - ", 1)
        if len(fields) != 2:
            continue
        left, right = fields
        columns = left.split()
        if len(columns) < 5 or not right.split():
            continue
        mount = Path(columns[4].replace("\\040", " ")).resolve(strict=False)
        if resolved == mount or mount in resolved.parents:
            candidate = (len(mount.parts), right.split()[0])
            if best is None or candidate[0] > best[0]:
                best = candidate
    if best is None:
        raise ValueError("Active-storage filesystem mount cannot be resolved")
    return best[1]


def _nearest_existing(path: Path) -> Path:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    if not candidate.exists():
        raise ValueError("Active-storage path has no existing parent")
    return candidate


def validate_native_storage_contract(
    *, runtime_root: str, output_root: str, work_root: str,
    filesystems: Sequence[str], free_bytes: int,
    estimated_required_bytes: int, operational_reserve_bytes: int,
) -> dict[str, Any]:
    """Validate the portable part of the native active-storage contract."""
    runtime = PurePosixPath(require_safe_linux_runtime_path(runtime_root))
    output = PurePosixPath(require_safe_linux_runtime_path(output_root))
    work = PurePosixPath(require_safe_linux_runtime_path(work_root))
    for path in (output, work):
        if runtime != path and runtime not in path.parents:
            raise ValueError("GUI output/work roots must stay under the declared runtime root")
        folded = str(path).casefold()
        if folded == "/mnt/wdgold" or folded.startswith("/mnt/wdgold/"):
            raise ValueError("WD Gold is terminal archive storage and cannot be active work storage")
        if folded in {"/mnt/c", "/mnt/d"} or folded.startswith(("/mnt/c/", "/mnt/d/")):
            raise ValueError("Windows drive mounts cannot be active native Linux work storage")
    observed_filesystems = tuple(sorted(set(filesystems)))
    unsupported = set(observed_filesystems) - {"ext4", "xfs", "btrfs"}
    if unsupported:
        raise ValueError("Unsupported active-storage filesystem: " + ", ".join(sorted(unsupported)))
    required = estimated_required_bytes + operational_reserve_bytes
    if free_bytes < required:
        raise ValueError(f"Insufficient active-storage disk: need {required}, observed {free_bytes}")
    return {
        "status": "READY", "filesystems": observed_filesystems,
        "free_bytes": free_bytes, "estimated_required_bytes": estimated_required_bytes,
        "operational_reserve_bytes": operational_reserve_bytes,
        "active_output_root": str(output), "active_work_root": str(work),
        "archive_policy": asdict(TERMINAL_RESULTS_ARCHIVE_POLICY),
    }


def _native_storage_readiness(draft: GuiDraft) -> dict[str, Any]:
    runtime = Path(require_safe_linux_runtime_path(draft.runtime_root)).resolve(strict=True)
    output = Path(require_safe_linux_runtime_path(draft.output_root)).resolve(strict=False)
    work = Path(require_safe_linux_runtime_path(draft.work_root)).resolve(strict=False)
    filesystems = {_mount_type(_nearest_existing(path)) for path in (output, work)}
    raw_bytes = 0
    for sample in draft.samples:
        for role in ("fastq_1", "fastq_2"):
            value = str(sample.get(role) or "")
            if value:
                candidate = Path(require_safe_linux_runtime_path(value)).resolve(strict=True)
                if not candidate.is_file():
                    raise ValueError(f"Selected FASTQ is missing: {role}")
                raw_bytes += candidate.stat().st_size
    estimated = max(5 * 1024**3, raw_bytes * (6 if draft.bam_output_mode == "none" else 100))
    reserve = 5 * 1024**3
    free = min(shutil.disk_usage(_nearest_existing(path)).free for path in (output, work))
    return validate_native_storage_contract(
        runtime_root=str(runtime), output_root=str(output), work_root=str(work),
        filesystems=tuple(filesystems), free_bytes=free,
        estimated_required_bytes=estimated, operational_reserve_bytes=reserve,
    )


def _has_conflicting_native_run(output_root: str) -> bool:
    """Rediscover a live native controller from bounded persistent run state."""
    root = Path(require_safe_linux_runtime_path(output_root)).resolve(strict=False)
    if not root.is_dir():
        return False
    for number, run_file in enumerate(root.rglob("run.json"), start=1):
        if number > 1000:
            raise ValueError("Active-run discovery exceeded the bounded 1000-run inventory")
        run_dir = run_file.parent.resolve(strict=True)
        if root != run_dir and root not in run_dir.parents:
            raise ValueError("Active-run discovery encountered a symlink escape")
        lock_state = RunStateStore(run_dir).inspect_lock(distribution=None)
        status_file = run_dir / "status.json"
        state = ""
        if status_file.is_file():
            try:
                state = str(json.loads(status_file.read_text(encoding="utf-8")).get("state") or "")
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"Cannot inspect persistent run status: {exc}") from exc
        if lock_state == "LIVE" or state in {"STARTING", "RUNNING", "RESUMING"}:
            return True
    return False


def _blocked_eligibility(
    draft: GuiDraft, *, code: str, explanation: str,
    receipt_status: str = "NOT_CHECKED", capability_status: str = "NOT_QUALIFIED",
    resource_contract_id: str | None = None,
    assets: Mapping[str, Any] | None = None,
    storage: Mapping[str, Any] | None = None,
) -> GuiScientificLaunchEligibility:
    return GuiScientificLaunchEligibility(
        False, draft.execution_context, draft.host_profile_id, receipt_status,
        capability_status, draft.workflow_backend, draft.alignment_profile_id,
        resource_contract_id, dict(assets or {}), dict(storage or {}), code,
        explanation, ("research use only", "non-diagnostic", "no manual bypass"),
    )


def _validate_observed_native_host(
    host_profile_id: str, hardware_report: Mapping[str, Any],
) -> None:
    profile = get_host_profile(host_profile_id)
    ram = int(hardware_report.get("host_ram_bytes") or 0)
    if ram < profile.minimum_physical_ram_bytes:
        raise ValueError(
            "Observed physical RAM does not meet the qualified Ubuntu host contract: "
            f"need {profile.minimum_physical_ram_bytes}, observed {ram}"
        )
    required_vram = profile.minimum_vram_mib * 1024**2
    gpus = tuple(hardware_report.get("nvidia_gpus") or ())
    matches = [gpu for gpu in gpus if (
        str(gpu.get("name") or "") == profile.gpu_model
        and int(gpu.get("total_vram_bytes") or 0) >= required_vram
    )]
    if not matches:
        raise ValueError(
            "Observed GPU/VRAM does not meet the qualified Ubuntu host contract: "
            f"need {profile.gpu_model} with at least {profile.minimum_vram_mib} MiB"
        )


def scientific_launch_eligibility(
    draft: GuiDraft, *, context: PreparationContext | None = None,
    storage_readiness: Mapping[str, Any] | None = None,
    active_lock: bool | None = None,
    host_system: str | None = None, kernel_release: str | None = None,
) -> GuiScientificLaunchEligibility:
    """Fail closed before native GUI preparation without creating run state."""
    if draft.execution_context != NATIVE_LINUX:
        return _blocked_eligibility(
            draft, code="NATIVE_EXECUTION_CONTEXT_REQUIRED",
            explanation="Native GUI scientific launch is unavailable on Windows/WSL.",
        )
    if draft.host_profile_id != UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID:
        return _blocked_eligibility(
            draft, code="HOST_PROFILE_UNQUALIFIED",
            explanation="The detected host profile is not the qualified Ubuntu high-memory profile.",
        )
    try:
        require_native_linux_host(host_system=host_system, kernel_release=kernel_release)
    except (OSError, ValueError) as exc:
        return _blocked_eligibility(draft, code="GENUINE_NATIVE_LINUX_REQUIRED", explanation=str(exc))
    try:
        workflow = parse_workflow_backend(draft.workflow_backend)
        if workflow.workflow_backend not in {HARAKO_NATIVE_V1, NFCORE_REFERENCE}:
            raise ValueError("Selected workflow backend is unavailable")
        receipt_path = installed_host_receipt_path(
            Path(draft.runtime_root), UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
        )
        receipt = HostQualificationReceipt.load(receipt_path)
        receipt.validate(report_root=Path(__file__).resolve().parents[3] / "docs/qualification")
        if (
            not receipt.product_cli_verified
            and not product_cli_qualification_evidence_valid(receipt_path=receipt_path)
        ):
            raise ValueError("Installed host receipt lacks Ubuntu public product-CLI verification")
    except (OSError, ValueError) as exc:
        return _blocked_eligibility(
            draft, code="HOST_RECEIPT_INVALID", explanation=str(exc), receipt_status="INVALID",
        )
    if not harako_native_parity_evidence_valid():
        return _blocked_eligibility(
            draft, code="PARITY_EVIDENCE_INVALID",
            explanation="Committed Harako-native C1 parity evidence is missing or changed.",
            receipt_status="VALID",
        )
    contract = (
        select_resource_contract(
            draft.host_profile_id, draft.reference_pack_id, draft.alignment_profile_id,
        ) if draft.bam_output_mode != "none" else None
    )
    if draft.bam_output_mode != "none" and contract is None:
        return _blocked_eligibility(
            draft, code="ALIGNMENT_PROFILE_UNQUALIFIED",
            explanation="No qualified host/reference/alignment resource contract exists.",
            receipt_status="VALID",
        )
    try:
        reference = get_reference(
            draft.reference_pack_id, runtime_root=draft.runtime_root,
            distribution=draft.distribution, quantification_mode=draft.quantification_mode,
            primary_profile_id=draft.primary_profile_id,
            execution_context=draft.execution_context,
        )
        requirements = _requirements_for_draft(draft)
        prepared_context = context or build_native_linux_preparation_context(
            runtime_root=draft.runtime_root,
            nextflow_executable=draft.nextflow_executable,
            requirements=requirements,
        )
        if prepared_context.execution.identity != NATIVE_LINUX:
            raise ValueError("Preparation context is not native Linux")
        _validate_observed_native_host(draft.host_profile_id, prepared_context.hardware_report)
        if prepared_context.host_receipt is None:
            prepared_context = replace(prepared_context, host_receipt=receipt)
        validate_offline_runtime_closure(requirements, prepared_context)
        capability = capability_for(
            reference_pack_id=draft.reference_pack_id,
            bam_output_mode=draft.bam_output_mode,
            alignment_profile_id=draft.alignment_profile_id,
            quantification_mode=draft.quantification_mode,
            primary_profile_id=draft.primary_profile_id,
            runtime_root=draft.runtime_root, distribution=draft.distribution,
            host_profile_id=draft.host_profile_id,
            execution_context=draft.execution_context,
            host_receipt=receipt,
            parabricks_provenance=prepared_context.parabricks_provenance,
            observed_parabricks_image=prepared_context.parabricks_image_inspection,
        )
        if capability.status.value not in {"AVAILABLE_QUALIFIED", "AVAILABLE_WITH_LIMITATION"}:
            raise ValueError(f"{capability.reason_code}: {capability.explanation}")
        storage = dict(storage_readiness or _native_storage_readiness(draft))
        if storage.get("status") != "READY":
            raise ValueError(str(storage.get("explanation") or "Active storage is not ready"))
        conflict = _has_conflicting_native_run(draft.output_root) if active_lock is None else active_lock
        if conflict:
            raise ValueError("A live controller lock already exists for the selected run")
    except (OSError, ValueError) as exc:
        text = str(exc)
        code = "ASSET_OR_RUNTIME_CLOSURE_UNAVAILABLE"
        if "storage" in text.casefold() or "filesystem" in text.casefold() or "disk" in text.casefold():
            code = "ACTIVE_STORAGE_UNAVAILABLE"
        elif "lock" in text.casefold():
            code = "ACTIVE_RUN_CONFLICT"
        elif "provenance" in text.casefold():
            code = "PROVENANCE_INVALID"
        elif "observed" in text.casefold() and "host contract" in text.casefold():
            code = "HOST_HARDWARE_MISMATCH"
        return _blocked_eligibility(
            draft, code=code, explanation=text, receipt_status="VALID",
            resource_contract_id=contract.contract_id if contract else None,
        )
    assets = {
        "status": "READY", "reference_pack_id": reference.reference_pack_id,
        "quantification_mode": draft.quantification_mode,
        "primary_profile_id": draft.primary_profile_id,
        "reference_assets": reference.reference_assets_cached,
        "star_index": reference.star_index_cached,
        "salmon_2_5_1_index": reference.salmon_251_index_cached,
        "salmon_1_10_3_index": reference.salmon_1103_index_cached,
        "runtime_image_roles": requirements.required_image_roles,
    }
    return GuiScientificLaunchEligibility(
        True, NATIVE_LINUX, draft.host_profile_id, "VALID", capability.status.value,
        workflow.workflow_backend, draft.alignment_profile_id,
        contract.contract_id if contract else None, assets, storage, None, "",
        tuple(workflow.limitations) + (
            "research use only", "non-diagnostic", "native GUI C1 launch qualification pending",
        ),
    )


def _validate_gui_capability_snapshot(
    snapshot: Mapping[str, Any], *, capability: CapabilityResult, workflow_backend: str,
) -> None:
    expected = {
        "capability_matrix_version": CAPABILITY_MATRIX_VERSION,
        "result": capability.as_dict(),
        "workflow_backend": parse_workflow_backend(workflow_backend).as_dict(),
        "evaluated_at": "plan_creation",
    }
    if dict(snapshot) != expected:
        raise ValueError("GUI plan capability snapshot differs from the application service result")


def create_gui_plan(draft: GuiDraft, *, plan_dir_linux: str | None = None,
                    preparation_context: PreparationContext | None = None) -> Path:
    if not PROJECT_RE.fullmatch(draft.project_slug):
        raise ValueError("Project slug must contain lowercase letters/digits separated by single hyphens")
    runtime = require_safe_linux_runtime_path(draft.runtime_root)
    for value in (draft.output_root, draft.work_root):
        checked = require_safe_linux_runtime_path(value)
        if not checked.startswith(runtime + "/"):
            raise ValueError("GUI output/work roots must stay under the declared runtime root")
    reference = get_reference(
        draft.reference_pack_id, runtime_root=runtime, distribution=draft.distribution,
        quantification_mode=draft.quantification_mode, primary_profile_id=draft.primary_profile_id,
        execution_context=draft.execution_context,
    )
    native = draft.execution_context == NATIVE_LINUX
    receipt = None
    context = preparation_context
    if native:
        receipt = HostQualificationReceipt.load(installed_host_receipt_path(
            Path(runtime), UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
        ))
        receipt.validate(report_root=Path(__file__).resolve().parents[3] / "docs/qualification")
        context = context or build_native_linux_preparation_context(
            runtime_root=runtime, nextflow_executable=draft.nextflow_executable,
            requirements=_requirements_for_draft(draft),
        )
    capability = capability_for(
        reference_pack_id=draft.reference_pack_id, bam_output_mode=draft.bam_output_mode,
        alignment_profile_id=draft.alignment_profile_id, quantification_mode=draft.quantification_mode,
        primary_profile_id=draft.primary_profile_id, runtime_root=runtime, distribution=draft.distribution,
        host_profile_id=draft.host_profile_id, execution_context=draft.execution_context,
        host_receipt=receipt,
        parabricks_provenance=context.parabricks_provenance if context else None,
        observed_parabricks_image=context.parabricks_image_inspection if context else None,
    )
    if capability.status.value not in {"AVAILABLE_QUALIFIED", "AVAILABLE_WITH_LIMITATION"}:
        raise ValueError(f"Capability unavailable: {capability.reason_code}: {capability.explanation}")
    instant = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    plan_linux = plan_dir_linux or f"{runtime}/gui-plans/{draft.project_slug}/{instant}"
    plan_linux = require_safe_linux_runtime_path(plan_linux)
    if not plan_linux.startswith(runtime + "/"):
        raise ValueError("GUI plan directory must stay under runtime root")
    plan_dir = _host(plan_linux, draft.distribution, draft.execution_context)
    sample_sheet = plan_dir / "samples.csv"
    rows = []
    for row in draft.samples:
        converted = dict(row)
        for role in ("fastq_1", "fastq_2"):
            value = str(converted.get(role) or "")
            if value.startswith("/") and not native:
                converted[role] = str(_host(value, draft.distribution, draft.execution_context))
        rows.append(converted)
    write_new_text(sample_sheet, _sample_csv(rows))
    bam = BamOutputMode(draft.bam_output_mode)
    quant_only = bam is BamOutputMode.NONE
    qualification_resource = (
        select_resource_contract(
            draft.host_profile_id, draft.reference_pack_id, draft.alignment_profile_id,
        ) if native and not quant_only else None
    )
    if native and not quant_only and qualification_resource is None:
        raise ValueError("No qualified host/reference/alignment resource contract exists")
    plan = create_plan(
        samplesheet=sample_sheet, plan_dir=plan_dir,
        output_root=_host(draft.output_root, draft.distribution, draft.execution_context),
        work_root=_host(draft.work_root, draft.distribution, draft.execution_context),
        fasta=_host(reference.fasta_linux, draft.distribution, draft.execution_context),
        gtf=_host(reference.gtf_linux, draft.distribution, draft.execution_context),
        transcript_fasta=_host(reference.transcript_fasta_linux, draft.distribution, draft.execution_context),
        salmon_2_5_1_index_manifest=(
            _host(reference.salmon_251_manifest_linux, draft.distribution, draft.execution_context)
            if reference.salmon_251_index_cached else None
        ),
        salmon_1_10_3_index_manifest=(
            _host(reference.salmon_1103_manifest_linux, draft.distribution, draft.execution_context)
            if reference.salmon_1103_index_cached else None
        ),
        star_index=None if quant_only else _host(
            str(reference.star_index_linux), draft.distribution, draft.execution_context,
        ),
        star_index_sjdb_overhang=None if quant_only else reference.star_sjdb_overhang,
        allow_small_fixture_star_index=(reference.reference_pack_id == SMALL_REFERENCE_PACK_ID),
        bam_retention=BamRetention(bam.value), bam_output_mode=bam,
        gpu_selection="none" if quant_only else "all",
        memory_mode=MemoryMode.STANDARD if quant_only else MemoryMode.LOW_MEMORY_CANDIDATE,
        qualification_debug_mode=fixed_gui_debug_mode(reference.reference_pack_id, bam.value),
        species=reference.species, assembly=reference.assembly,
        annotation_provider=reference.annotation_provider, annotation_release=reference.annotation_release,
        project_slug=draft.project_slug, target="linux" if native else "wsl",
        wsl_distribution=None if native else draft.distribution,
        quantification_mode=draft.quantification_mode,
        primary_quantification_profile=draft.primary_profile_id,
        explicit_library_type=draft.explicit_library_type,
        alignment_profile_id="none" if quant_only else draft.alignment_profile_id,
        workflow_backend=draft.workflow_backend,
        host_profile_id=draft.host_profile_id,
        host_qualification_receipt=receipt,
        qualification_report_root=Path(__file__).resolve().parents[3] / "docs/qualification",
        parabricks_provenance=context.parabricks_provenance if context else None,
        observed_parabricks_image=context.parabricks_image_inspection if context else None,
        qualification_resource_contract=(
            qualification_resource.contract_id if qualification_resource else None
        ),
    )
    _validate_gui_capability_snapshot(
        plan.capability_snapshot,
        capability=capability,
        workflow_backend=draft.workflow_backend,
    )
    return plan_dir / "plan.json"


def prepare_gui_run(
    draft: GuiDraft, *, plan_dir_linux: str | None = None,
    existing_plan_path: Path | None = None,
) -> GuiPreparedRun:
    context = None
    if existing_plan_path is not None:
        validate_plan_file(existing_plan_path)
    if draft.execution_context == NATIVE_LINUX:
        context = build_native_linux_preparation_context(
            runtime_root=draft.runtime_root, nextflow_executable=draft.nextflow_executable,
            requirements=(
                runtime_requirements_for_plan_file(existing_plan_path)
                if existing_plan_path is not None else _requirements_for_draft(draft)
            ),
        )
        eligibility = scientific_launch_eligibility(draft, context=context)
        if not eligibility.allowed:
            raise ValueError(
                f"Native GUI launch blocked: {eligibility.blocker_code}: "
                f"{eligibility.blocker_explanation}"
            )
    plan_path = existing_plan_path or create_gui_plan(
        draft, plan_dir_linux=plan_dir_linux, preparation_context=context,
    )
    validate_plan_file(plan_path)
    context = context or build_wsl_preparation_context(
        runtime_root=draft.runtime_root, distribution=draft.distribution,
        requirements=runtime_requirements_for_plan_file(plan_path),
    )
    prepared = prepare_run(plan_path=plan_path, runtime_root=draft.runtime_root, context=context)
    inspected = inspect_run(prepared.run_dir)
    identity = inspected["run"]["identity"]
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    return GuiPreparedRun(plan["plan_id"], prepared.approval_hash, prepared.run_id,
                          prepared.run_dir_linux, identity["analysis_series_id"],
                          dict(plan["capability_snapshot"]["result"]), str(plan_path))


def launch_gui_controller(*, action: str, run_directory: str, approval_hash: str,
                          distribution: str = "Ubuntu") -> LaunchedController:
    host = _host(run_directory, distribution) if run_directory.startswith("/") else Path(run_directory)
    inspected = inspect_run(host)
    identity = inspected["run"]["identity"]
    execution_context = str(identity.get("execution_context") or "")
    if execution_context == NATIVE_LINUX:
        plan_path = host / "frozen" / "plan.json"
        verify_frozen(host)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        capability = dict(dict(plan.get("capability_snapshot") or {}).get("result") or {})
        if capability.get("host_profile_id") != UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID:
            raise ValueError("Native GUI run is not frozen to the qualified Ubuntu host profile")
        if plan.get("workflow_backend") not in {HARAKO_NATIVE_V1, NFCORE_REFERENCE}:
            raise ValueError("Native GUI run has an unavailable frozen workflow backend")
    if identity["approval_hash"] != approval_hash:
        raise ValueError("Approval hash does not match immutable run identity")
    lock_state = RunStateStore(host).inspect_lock(
        distribution=None if execution_context == NATIVE_LINUX else distribution,
    )
    if lock_state == "LIVE":
        raise ValueError("A live controller lock already exists for this run")
    argv = controller_argv(action=action, run_dir=run_directory, approval_hash=approval_hash,
                           distribution=distribution,
                           execution_context="native-linux" if execution_context == NATIVE_LINUX else "wsl2")
    return launch_controller(argv=argv, run_dir_host=host)


def poll_run_status(run_directory: str, *, distribution: str = "Ubuntu",
                    last_valid: Mapping[str, Any] | None = None,
                    sleep: Any = time.sleep) -> dict[str, Any]:
    host = _host(run_directory, distribution) if run_directory.startswith("/") else Path(run_directory)
    error = ""
    for attempt in range(POLL_ATTEMPTS):
        try:
            payload = status_payload(host)
            if last_valid and str(payload["last_update"]) < str(last_valid.get("last_update", "")):
                return {"snapshot": dict(last_valid), "stale": True, "error": "older snapshot ignored"}
            return {"snapshot": payload, "stale": False, "error": "", "attempts": attempt + 1}
        except (OSError, ValueError) as exc:
            error = str(exc)
            if attempt + 1 < POLL_ATTEMPTS:
                sleep(POLL_BACKOFF_SECONDS * (attempt + 1))
    if last_valid:
        return {"snapshot": dict(last_valid), "stale": True, "error": error, "attempts": POLL_ATTEMPTS}
    raise ValueError(f"Run status unavailable after bounded retry: {error}")


def reconnect_run(run_directory: str, *, distribution: str = "Ubuntu") -> dict[str, Any]:
    host = _host(run_directory, distribution) if run_directory.startswith("/") else Path(run_directory)
    error = ""
    for attempt in range(POLL_ATTEMPTS):
        try:
            inspected = inspect_run(host)
            store = RunStateStore(host)
            return {**inspected, "lock_state": store.inspect_lock(distribution=distribution),
                    "attempts": [path.name for path in sorted((host / "execution/attempts").glob("[0-9][0-9][0-9][0-9]"))],
                    "artifacts": list_artifacts(host)}
        except (OSError, ValueError) as exc:
            error = str(exc)
            if attempt + 1 < POLL_ATTEMPTS:
                time.sleep(POLL_BACKOFF_SECONDS * (attempt + 1))
    raise ValueError(f"Run reconnection unavailable after bounded retry: {error}")


def verify_gui_artifacts(run_directory: str, *, deep: bool = False,
                         distribution: str = "Ubuntu") -> dict[str, Any]:
    host = _host(run_directory, distribution) if run_directory.startswith("/") else Path(run_directory)
    return verify_artifacts(host, deep=deep, distribution=distribution)


def create_gui_support_bundle(run_directory: str, *, distribution: str = "Ubuntu") -> str:
    host = _host(run_directory, distribution) if run_directory.startswith("/") else Path(run_directory)
    return str(create_support_bundle(host))


def export_gui_handoff(output_linux: str, *, distribution: str = "Ubuntu") -> str:
    destination = _host(output_linux, distribution)
    write_handoff(destination)
    return output_linux


def matrix_preview(run_directory: str, relative_path: str, *, distribution: str = "Ubuntu",
                   max_rows: int = 20, max_columns: int = 8, max_bytes: int = 5 * 1024**2) -> dict[str, Any]:
    host = _host(run_directory, distribution) if run_directory.startswith("/") else Path(run_directory)
    path = ensure_within(host / relative_path, host, require_exists=True)
    if path.stat().st_size > max_bytes:
        return {"columns": (), "rows": (), "truncated": True, "reason": "size gate"}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader)[:max_columns]
        rows = [row[:max_columns] for _, row in zip(range(max_rows), reader)]
    return {"columns": header, "rows": rows, "truncated": len(rows) == max_rows, "reason": "row/column gate"}


def visible_profile_cards() -> tuple[dict[str, Any], ...]:
    return tuple(profile.as_dict() for profile in visible_profiles())


def read_small_artifact(run_directory: str, relative_path: str, *, distribution: str = "Ubuntu",
                        max_bytes: int = 10 * 1024**2) -> dict[str, Any]:
    """Read only a registered, user-facing small text/report artifact."""
    host = _host(run_directory, distribution) if run_directory.startswith("/") else Path(run_directory)
    inventory = list_artifacts(host)
    matches = [item for item in inventory["artifacts"] if item["relative_path"] == relative_path]
    if len(matches) != 1:
        raise ValueError("Artifact is not uniquely registered for this run")
    artifact = matches[0]
    allowed_roles = {
        "self_contained_report", "concordance_html", "profile_comparison",
        "gene_method_sensitive", "transcript_method_sensitive", "hardware_report",
    }
    if artifact["role"] not in allowed_roles:
        raise ValueError("Artifact role is not eligible for in-browser display")
    path = ensure_within(host / relative_path, host, require_exists=True)
    if path.stat().st_size > max_bytes:
        raise ValueError("Artifact exceeds the GUI display size gate")
    return {"role": artifact["role"], "relative_path": relative_path,
            "media_type": artifact["media_type"], "size": path.stat().st_size,
            "content": path.read_text(encoding="utf-8")}
