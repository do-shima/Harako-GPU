"""Create and validate immutable, non-executing workflow plans."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Mapping

from harako_gpu.adapters.filesystem import sha256_path, write_new_text
from harako_gpu.adapters.nextflow import build_nextflow_argv, build_nextflow_environment, quote_argv, reject_mixed_path_context
from harako_gpu.adapters.wsl import unc_path_to_linux
from harako_gpu.core.analysis import analysis_plan_from_rows
from harako_gpu.core.canonical import sha256_payload
from harako_gpu.core.contracts import (
    BamRetention, IndexStatus, MemoryMode, NextflowVersionStatus, QualificationDebugMode, ReferenceContract,
    qualified_backend_profile,
)
from harako_gpu.core.capabilities import (
    CAPABILITY_MATRIX_VERSION, BamOutputMode, CapabilityStatus, ExecutionRoute,
)
from harako_gpu.services.capabilities import evaluate_capability, validate_capability_snapshot_version
from harako_gpu.core.provenance import approval_hash_for, plan_id_for
from harako_gpu.core.samples import Sample, rows_for_analysis, validate_samples
from harako_gpu.services.backend_profile import build_nf_params, config_fragment, retention_warnings, validate_nf_params
from harako_gpu.services.alignment_profiles import (
    ONE_PASS_PROFILE_ID, TWO_PASS_PROFILE_ID, fixed_parabricks_extra_args,
    get_alignment_profile, validate_alignment_profile_selection,
)
from harako_gpu.services.run_contract import RunPlan, execution_payload
from harako_gpu.services.independent_fastq_salmon import quantification_contract_from_dict
from harako_gpu.services.quantification_profiles import (
    AnalysisMode, PROFILE_CATALOG_VERSION, ModeSelection, ProfileIndex, get_profile,
    validate_versioned_quantification_contract, versioned_quantification_contract,
)
from harako_gpu.services.host_profiles import (
    HostQualificationReceipt, OfflinePlatformImageProvenance,
    WINDOWS_HOST_PROFILE_ID, featurecounts_contract, runtime_quantification_image_contract,
    select_resource_contract,
)
from harako_gpu.services.workflow_backends import (
    CANONICAL_OUTPUT_CONTRACT,
    HARAKO_NATIVE_V1,
    HISTORICAL_MISSING_WORKFLOW_BACKEND,
    HARAKO_PROCESSED_FASTQ_CONTRACT,
    NFCORE_PROCESSED_FASTQ_CONTRACT,
    alignment_backend_for_route,
    default_workflow_backend_for_new_plan,
    parse_workflow_backend,
    validate_backend_alignment,
)


SAMPLE_COLUMNS = ("sample", "condition", "fastq_1", "fastq_2", "strandedness", "library_protocol")
PROJECT_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _profile_index_from_manifest(path: Path, expected_profile_id: str) -> ProfileIndex:
    try:
        raw = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
        data = dict(raw.get("profile_index") or raw)
        index = ProfileIndex(**{key: data[key] for key in (
            "profile_id", "index_id", "path", "builder_version", "image_identity",
            "transcript_source_sha256", "genome_source_sha256", "gtf_sha256",
            "tx2gene_sha256", "manifest_sha256",
        )})
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"Cannot read fixed profile index manifest: {exc}") from exc
    if index.profile_id != expected_profile_id:
        raise ValueError("Profile index manifest belongs to a different fixed profile")
    index.validate()
    if not Path(index.path).expanduser().is_dir():
        raise ValueError(f"Pinned profile index directory does not exist: {expected_profile_id}")
    return index


def _logical_path(path: Path, *, target: str, wsl_distribution: str | None) -> str:
    resolved = path.expanduser().resolve()
    if target == "wsl":
        return unc_path_to_linux(str(resolved), distribution=wsl_distribution)
    return str(resolved)


def load_samplesheet(
    path: Path,
    *,
    target: str = "windows",
    wsl_distribution: str | None = None,
) -> tuple[Sample, ...]:
    source = path.expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"Samplesheet does not exist: {source}")
    delimiter = "\t" if source.suffix.lower() == ".tsv" else ","
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        fields = set(reader.fieldnames or [])
        missing = sorted(set(SAMPLE_COLUMNS) - fields)
        if missing:
            raise ValueError("Samplesheet is missing columns: " + ", ".join(missing))
        rows = [{key: (row.get(key) or "").strip() for key in SAMPLE_COLUMNS} for row in reader]
    structural = validate_samples(rows)
    if not structural.valid:
        raise ValueError("Invalid samplesheet: " + "; ".join(structural.errors))
    samples: list[Sample] = []
    for row in rows:
        resolved: dict[str, str] = dict(row)
        for key in ("fastq_1", "fastq_2"):
            if not row[key]:
                continue
            candidate = Path(row[key]).expanduser()
            candidate = (candidate if candidate.is_absolute() else source.parent / candidate).resolve()
            if not candidate.is_file():
                raise ValueError(f"{key} does not exist for sample {row['sample']}: {candidate}")
            resolved[key] = _logical_path(candidate, target=target, wsl_distribution=wsl_distribution)
        samples.append(Sample(**resolved))
    return tuple(samples)


def _reference(*, species: str, assembly: str, annotation_provider: str,
               annotation_release: str, fasta: Path, gtf: Path,
               transcript_fasta: Path | None, target: str,
               wsl_distribution: str | None) -> ReferenceContract:
    fasta_path = fasta.expanduser().resolve()
    gtf_path = gtf.expanduser().resolve()
    if not fasta_path.is_file():
        raise ValueError(f"FASTA does not exist: {fasta_path}")
    if not gtf_path.is_file():
        raise ValueError(f"GTF does not exist: {gtf_path}")
    transcript_path = transcript_fasta.expanduser().resolve() if transcript_fasta else None
    if transcript_path is not None and not transcript_path.is_file():
        raise ValueError(f"Transcript FASTA does not exist: {transcript_path}")
    fasta_digest = sha256_path(fasta_path)
    gtf_digest = sha256_path(gtf_path)
    transcript_digest = sha256_path(transcript_path) if transcript_path else None
    pack_payload = {
        "schema_version": 1, "species": species, "assembly": assembly,
        "annotation_provider": annotation_provider, "annotation_release": annotation_release,
        "fasta_sha256": fasta_digest, "gtf_sha256": gtf_digest,
        "transcript_fasta_sha256": transcript_digest,
    }
    contract = ReferenceContract(
        species=species,
        assembly=assembly,
        annotation_provider=annotation_provider,
        annotation_release=annotation_release,
        fasta_path=_logical_path(fasta_path, target=target, wsl_distribution=wsl_distribution),
        fasta_sha256=fasta_digest,
        gtf_path=_logical_path(gtf_path, target=target, wsl_distribution=wsl_distribution),
        gtf_sha256=gtf_digest,
        reference_pack_id=sha256_payload({"kind": "harako-reference-pack", "payload": pack_payload}),
        transcript_fasta_path=(
            _logical_path(transcript_path, target=target, wsl_distribution=wsl_distribution)
            if transcript_path else None
        ),
        transcript_fasta_sha256=transcript_digest,
        parabricks_index_status=IndexStatus.NOT_TESTED,
        salmon_index_status=IndexStatus.NOT_TESTED,
    )
    contract.validate(require_existing=target != "wsl")
    return contract


def _nf_samplesheet(samples: tuple[Sample, ...]) -> str:
    lines = ["sample,fastq_1,fastq_2,strandedness"]
    for sample in samples:
        values = [sample.sample, sample.fastq_1, sample.fastq_2, sample.strandedness]
        if any("," in value or "\n" in value or '"' in value for value in values):
            raise ValueError("Samplesheet values requiring CSV quoting are not supported in the MVP contract")
        lines.append(",".join(values))
    return "\n".join(lines) + "\n"


def create_plan(*, samplesheet: Path, plan_dir: Path, output_root: Path, work_root: Path,
                fasta: Path, gtf: Path, bam_retention: BamRetention, gpu_selection: str,
                memory_mode: MemoryMode, species: str, assembly: str, annotation_provider: str,
                annotation_release: str, project_slug: str, target: str,
                transcript_fasta: Path | None = None,
                qualification_debug_mode: QualificationDebugMode = QualificationDebugMode.DISABLED,
                save_reference: bool = False, skip_pseudo_alignment: bool = False,
                salmon_index_manifest: Path | None = None,
                quantification_mode: str = "recommended-only",
                primary_quantification_profile: str | None = None,
                salmon_2_5_1_index_manifest: Path | None = None,
                salmon_1_10_3_index_manifest: Path | None = None,
                star_index: Path | None = None,
                star_index_sjdb_overhang: int | None = None,
                qualification_resource_contract: str | None = None,
                explicit_library_type: str = "ISR",
                alignment_profile_id: str = TWO_PASS_PROFILE_ID,
                allow_alignment_qualification_candidate: bool = False,
                allow_small_fixture_star_index: bool = False,
                bam_output_mode: BamOutputMode | None = None,
                wsl_distribution: str | None = None,
                host_profile_id: str = WINDOWS_HOST_PROFILE_ID,
                host_qualification_receipt: HostQualificationReceipt | None = None,
                qualification_report_root: Path | None = None,
                parabricks_provenance: OfflinePlatformImageProvenance | None = None,
                observed_parabricks_image: Mapping[str, Any] | None = None,
                workflow_backend: str | None = None) -> RunPlan:
    if not PROJECT_RE.fullmatch(project_slug):
        raise ValueError("project_slug must contain lowercase letters/digits separated by single hyphens")
    if skip_pseudo_alignment:
        raise ValueError("Independent FASTQ Salmon cannot set skip_pseudo_alignment=true")
    if transcript_fasta is None:
        raise ValueError("Independent FASTQ Salmon requires an explicit transcript FASTA")
    samples = load_samplesheet(
        samplesheet, target=target, wsl_distribution=wsl_distribution,
    )
    analysis_plan_from_rows(rows_for_analysis([sample.as_dict() for sample in samples]))
    if explicit_library_type not in {"U", "ISF", "ISR"}:
        raise ValueError("Versioned quantification requires an explicit U, ISF, or ISR library type")
    if star_index_sjdb_overhang not in {None, 74} and not (
        allow_small_fixture_star_index
        and star_index_sjdb_overhang == 100
        and assembly == "test-mini"
        and annotation_provider == "nf-core-test-datasets"
    ):
        raise ValueError("STAR index sjdbOverhang is restricted to an explicitly qualified fixed contract")
    if qualification_resource_contract not in {
        None, "full_human_47gib_probe_v1",
        "ubuntu_native_rtx3090_ram128_one_pass_42gb_v1",
        "ubuntu_native_rtx3090_ram128_two_pass_96gb_v1",
    }:
        raise ValueError("Unknown qualification resource contract")
    expected_strandedness = {"U": "unstranded", "ISF": "forward", "ISR": "reverse"}[explicit_library_type]
    for sample in samples:
        if sample.strandedness not in {"auto", expected_strandedness}:
            raise ValueError("Samplesheet strandedness conflicts with the explicit Salmon library type")
    reference = _reference(
        species=species, assembly=assembly, annotation_provider=annotation_provider,
        annotation_release=annotation_release, fasta=fasta, gtf=gtf,
        transcript_fasta=transcript_fasta, target=target, wsl_distribution=wsl_distribution,
    )
    bam_mode = bam_output_mode or BamOutputMode(bam_retention.value)
    if bam_mode.value != bam_retention.value:
        raise ValueError("bam_output_mode and bam_retention must match exactly")
    quant_only = bam_mode is BamOutputMode.NONE
    report_root = qualification_report_root or (
        Path(__file__).resolve().parents[3] / "docs/qualification"
    )
    host_receipt_validated = False
    if host_qualification_receipt is not None:
        try:
            host_qualification_receipt.validate(report_root=report_root)
        except ValueError:
            # Capability evaluation below retains the authoritative error and
            # blocks the plan. An invalid receipt must never select native.
            pass
        else:
            host_receipt_validated = True
    workflow = default_workflow_backend_for_new_plan(
        requested=workflow_backend,
        target=target,
        host_profile_id=host_profile_id,
        host_receipt_validated=host_receipt_validated,
        qualification_report_root=report_root,
    )
    alignment_backend = alignment_backend_for_route(quantification_only=quant_only)
    validate_backend_alignment(workflow.workflow_backend, alignment_backend.value)
    full_human_capacity_reference = (
        reference.fasta_sha256 == "e49b92b3e4f321bf254c042f25b726d9931c4d74c7523e8b6bb530e63b0cfd4b"
        and reference.gtf_sha256 == "8eb596086228540c93ccf56fbb6601fd99f19a6df2cecdde239af423e5db0729"
        and reference.transcript_fasta_sha256 == "c41a37f792b10399838246200dbaf54a334ec3f514cd36545bb2f9c9995b27ac"
    )
    if full_human_capacity_reference and star_index_sjdb_overhang is None:
        # The exact reference pack has one versioned STAR-index contract.  The
        # public CLI derives its immutable overhang; callers cannot substitute
        # an arbitrary value.
        star_index_sjdb_overhang = 74
    if quant_only:
        if alignment_profile_id not in {"none", ""}:
            raise ValueError("BAM none requires --alignment-profile none; implicit route conversion is forbidden")
        if star_index is not None:
            raise ValueError("BAM none cannot request a STAR index or comparator")
        alignment_profile = None
    elif full_human_capacity_reference:
        alignment_profile = get_alignment_profile(alignment_profile_id)
    elif alignment_profile_id == ONE_PASS_PROFILE_ID:
        alignment_profile = validate_alignment_profile_selection(
            alignment_profile_id, allow_qualification_candidate=allow_alignment_qualification_candidate,
            reject_current_host_two_pass=False,
        )
    else:
        alignment_profile = get_alignment_profile(alignment_profile_id)
    try:
        mode = AnalysisMode(quantification_mode.replace("-", "_"))
        profile_selection = ModeSelection.create(mode, primary_quantification_profile)
    except ValueError as exc:
        raise ValueError(f"Invalid versioned quantification selection: {exc}") from exc
    index_manifest_paths = {
        "salmon_2_5_1_deterministic": salmon_2_5_1_index_manifest,
        "salmon_1_10_3_compatibility": salmon_1_10_3_index_manifest,
    }
    required_profiles = tuple(
        value for value in (profile_selection.primary_profile_id, profile_selection.secondary_profile_id)
        if value is not None
    )
    missing = [profile_id for profile_id in required_profiles if index_manifest_paths[profile_id] is None]
    if missing:
        if profile_selection.mode is AnalysisMode.RECOMMENDED_ONLY:
            message = "recommended-only requires the fixed Salmon 2.5.1 profile index manifest"
        elif profile_selection.mode is AnalysisMode.COMPATIBILITY_ONLY:
            message = "compatibility-only requires the fixed Salmon 1.10.3 profile index manifest"
        else:
            message = "compare-both requires both fixed profile index manifests"
        raise ValueError(message)
    execution_indices = {
        profile_id: _profile_index_from_manifest(index_manifest_paths[profile_id], profile_id)
        for profile_id in required_profiles
    }
    for index in execution_indices.values():
        if index.genome_source_sha256 != reference.fasta_sha256:
            raise ValueError("Salmon index genome FASTA identity does not match the reference contract")
        if index.transcript_source_sha256 != reference.transcript_fasta_sha256:
            raise ValueError("Salmon index transcript FASTA identity does not match the reference contract")
        if index.gtf_sha256 != reference.gtf_sha256:
            raise ValueError("Salmon index GTF identity does not match the reference contract")
    quantification = versioned_quantification_contract(
        profile_selection, explicit_library_type=explicit_library_type, indices=execution_indices,
    )
    profile = qualified_backend_profile(
        bam_retention=bam_retention,
        gpu_selection=gpu_selection,
        memory_mode=memory_mode,
        qualification_debug_mode=qualification_debug_mode,
    )
    destination = plan_dir.expanduser().resolve()
    output = _logical_path(output_root, target=target, wsl_distribution=wsl_distribution)
    work = _logical_path(work_root, target=target, wsl_distribution=wsl_distribution)
    logical_star_index = _logical_path(star_index, target=target, wsl_distribution=wsl_distribution) if star_index else None
    nf_sheet = destination / "nf-samplesheet.csv"
    params_path = destination / "nf-params.json"
    logical_nf_sheet = _logical_path(nf_sheet, target=target, wsl_distribution=wsl_distribution)
    logical_params_path = _logical_path(params_path, target=target, wsl_distribution=wsl_distribution)
    paths = {
        "samplesheet": logical_nf_sheet, "outdir": output, "work_root": work,
        "fasta": reference.fasta_path, "gtf": reference.gtf_path, "params_file": logical_params_path,
    }
    reject_mixed_path_context(paths, target=target)
    if quant_only:
        params: dict[str, Any] = {"execution_route": ExecutionRoute.FASTQ_QUANTIFICATION_ONLY.value}
        argv = ("harako-fixed-route", ExecutionRoute.FASTQ_QUANTIFICATION_ONLY.value)
    elif workflow.workflow_backend == HARAKO_NATIVE_V1:
        if logical_star_index is None:
            raise ValueError("Harako-native Parabricks alignment requires the fixed STAR index")
        feature_type, group_type = featurecounts_contract(
            "human_grch38p14_gencode49_harako_gpu_v1" if full_human_capacity_reference
            else reference.reference_pack_id,
            feature_type="exon", group_type="gene_type" if full_human_capacity_reference else "gene_id",
        )
        params = {
            "input": logical_nf_sheet,
            "outdir": output,
            "fasta": reference.fasta_path,
            "gtf": reference.gtf_path,
            "star_index": logical_star_index,
            "library_type": explicit_library_type,
            "featurecounts_feature_type": feature_type,
            "featurecounts_group_type": group_type,
            "parabricks_two_pass_mode": "Basic" if alignment_profile.two_pass else "None",
            "parabricks_extra_args": fixed_parabricks_extra_args(alignment_profile.profile_id),
        }
        argv = (
            "nextflow", "run", "pipelines/harako-native-v1", "-params-file",
            logical_params_path, "-work-dir", work,
        )
    else:
        params = build_nf_params(
            profile, samplesheet=logical_nf_sheet, outdir=output, fasta=reference.fasta_path,
            gtf=reference.gtf_path, transcript_fasta=reference.transcript_fasta_path,
            save_reference=save_reference, skip_pseudo_alignment=True, star_index=logical_star_index,
        )
        if memory_mode is MemoryMode.LOW_MEMORY_CANDIDATE and star_index_sjdb_overhang == 74:
            params["extra_star_align_args"] = fixed_parabricks_extra_args(
                alignment_profile.profile_id,
                qualification_debug_x3=qualification_debug_mode is QualificationDebugMode.X3,
            )
        if full_human_capacity_reference:
            feature_type, group_type = featurecounts_contract(
                "human_grch38p14_gencode49_harako_gpu_v1",
                feature_type="exon", group_type="gene_type",
            )
            params["featurecounts_feature_type"] = feature_type
            params["featurecounts_group_type"] = group_type
        validate_nf_params(params)
        argv = build_nextflow_argv(samplesheet=logical_nf_sheet, outdir=output, fasta=reference.fasta_path,
            gtf=reference.gtf_path, params_file=logical_params_path, work_dir=work)
    warnings = retention_warnings(bam_retention)
    warnings.append("Versioned profile selection and execution route are immutable run inputs.")
    if workflow.workflow_backend == HARAKO_NATIVE_V1:
        warnings.append(
            "harako_native_v1 is qualified only for receipt-backed Ubuntu high-memory execution."
        )
    if memory_mode is MemoryMode.LOW_MEMORY_CANDIDATE:
        warnings.append("low_memory_candidate applies the fixed --low-memory mapping and remains scientifically unqualified.")
    seed = sha256_payload({
        "project_slug": project_slug, "samples": [sample.as_dict() for sample in samples],
        "reference_pack_id": reference.reference_pack_id, "backend_profile": profile.as_dict(),
        "output_root": output, "work_root": work, "quantification": quantification,
        "versioned_profile_selection": asdict(profile_selection),
        "alignment_profile": alignment_profile.as_dict() if alignment_profile else {"profile_id": "none", "mode": "not_applicable"},
        "execution_route": ExecutionRoute.FASTQ_QUANTIFICATION_ONLY.value if quant_only else ExecutionRoute.GPU_BAM_ALIGNMENT.value,
        "workflow_backend": workflow.workflow_backend,
        "alignment_backend": alignment_backend.value,
    })
    capability = evaluate_capability(
        reference=reference.as_dict(), bam_output_mode=bam_mode,
        alignment_profile_id=alignment_profile.profile_id if alignment_profile else None,
        quantification_mode=profile_selection.mode.value,
        primary_profile_id=profile_selection.primary_profile_id,
        secondary_profile_id=profile_selection.secondary_profile_id,
        execution_context="native_linux" if host_profile_id != WINDOWS_HOST_PROFILE_ID else "wsl2:Ubuntu",
        host_profile_id=host_profile_id, host_receipt=host_qualification_receipt,
        report_root=qualification_report_root, parabricks_provenance=parabricks_provenance,
        observed_parabricks_image=observed_parabricks_image,
    )
    blocked_statuses = {
        CapabilityStatus.UNSUPPORTED_HOST_MEMORY,
        CapabilityStatus.BLOCKED_IDENTITY_MISMATCH,
        CapabilityStatus.BLOCKED_PROVENANCE,
    }
    if (capability.status in blocked_statuses
            or (host_profile_id != WINDOWS_HOST_PROFILE_ID
                and capability.status not in {CapabilityStatus.AVAILABLE_QUALIFIED, CapabilityStatus.AVAILABLE_WITH_LIMITATION})):
        raise ValueError(f"Capability blocked: {capability.reason_code}: {capability.explanation}")
    fixed_resource = None
    if not quant_only:
        fixed_resource = select_resource_contract(
            host_profile_id, capability.reference_pack_id, alignment_profile.profile_id,
        )
    effective_resource_contract = fixed_resource.contract_id if fixed_resource else qualification_resource_contract
    if fixed_resource and qualification_resource_contract not in {None, fixed_resource.contract_id}:
        raise ValueError("Requested resource contract conflicts with the fixed host/reference/profile contract")
    if fixed_resource and qualification_debug_mode is not QualificationDebugMode.DISABLED:
        raise ValueError("High-memory host resource contracts cannot be replaced by a debug resource envelope")
    placeholder = RunPlan(
        "", "", project_slug, f"{project_slug}-{seed[:12]}", samples, reference, profile,
        bam_retention, output, work, (), tuple(warnings), tuple(argv),
        build_nextflow_environment(), profile.minimum_nextflow_version, profile.qualified_nextflow_version,
        None, NextflowVersionStatus.NOT_TESTED, {
            **quantification,
            "profile_catalog_version": PROFILE_CATALOG_VERSION,
            "mode": profile_selection.mode.value,
            "primary_profile_id": profile_selection.primary_profile_id,
            "secondary_profile_id": profile_selection.secondary_profile_id,
            "downstream_primary_profile_id": profile_selection.downstream_primary_profile_id,
            "profiles": {
                key: {
                    **get_profile(key).as_dict(),
                    "index": asdict(execution_indices[key]),
                    "runtime_image": (
                        runtime_quantification_image_contract(host_profile_id, key).as_dict()
                        if runtime_quantification_image_contract(host_profile_id, key) else None
                    ),
                }
                for key in (profile_selection.primary_profile_id, profile_selection.secondary_profile_id)
                if key is not None
            },
            "execution_indices_ready": True,
            "shared_processed_fastq_identity": "required_before_execution",
            "explicit_library_type": explicit_library_type,
            "parabricks_star_index": logical_star_index,
            "parabricks_star_sjdb_overhang": star_index_sjdb_overhang,
            "qualification_resource_contract": effective_resource_contract,
            "concordance_requested": profile_selection.secondary_profile_id is not None,
            "gpu_used": False,
            "input_kind": "processed_fastq",
            "star_gene_counts_comparator": "not_applicable" if quant_only else "planned_optional",
        }, alignment_profile.profile_id if alignment_profile else "none",
        alignment_profile.as_dict() if alignment_profile else {"profile_id": "none", "mode": "not_applicable"},
        ExecutionRoute.FASTQ_QUANTIFICATION_ONLY.value if quant_only else ExecutionRoute.GPU_BAM_ALIGNMENT.value,
        bam_mode.value,
        {"enabled": not quant_only, "profile_id": alignment_profile.profile_id if alignment_profile else None,
         "capability_status": None, "GPU_used": not quant_only, "BAM_expected": not quant_only},
        {},
    )
    alignment_snapshot = {**dict(placeholder.alignment or {}), "capability_status": capability.status.value}
    placeholder = replace(placeholder, alignment=alignment_snapshot,
                          capability_snapshot={"capability_matrix_version": CAPABILITY_MATRIX_VERSION,
                                               "result": capability.as_dict(),
                                               "workflow_backend": workflow.as_dict(),
                                               "evaluated_at": "plan_creation"})
    placeholder = replace(
        placeholder,
        workflow_backend=workflow.workflow_backend,
        alignment_backend=alignment_backend.value,
        processed_fastq_contract=(
            HARAKO_PROCESSED_FASTQ_CONTRACT
            if quant_only or workflow.workflow_backend == HARAKO_NATIVE_V1
            else NFCORE_PROCESSED_FASTQ_CONTRACT
        ),
        output_artifact_contract=CANONICAL_OUTPUT_CONTRACT,
        runtime_image_closure=workflow.image_closure_id,
        resource_contract_id=effective_resource_contract,
    )
    payload = execution_payload(placeholder)
    plan = replace(placeholder, plan_id=plan_id_for(payload), approval_hash=approval_hash_for(payload))
    artifacts = {
        destination / "nf-samplesheet.csv": _nf_samplesheet(samples),
        params_path: json.dumps(params, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        destination / "nextflow.config": (
            "// not applicable: FASTQ quantification-only route\n" if quant_only
            else "// harako_native_v1: repository-owned fixed DSL2 configuration\n"
            if workflow.workflow_backend == HARAKO_NATIVE_V1
            else config_fragment(profile, independent_fastq_salmon=True)
        ),
        destination / "command-preview.txt": quote_argv(argv, target=target) + "\n",
        destination / "plan.json": json.dumps(plan.as_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        destination / "warnings.json": json.dumps({"schema_version": 1, "warnings": warnings, "unresolved": []}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    }
    for path, content in artifacts.items():
        write_new_text(path, content)
    return plan


def validate_plan_file(path: Path) -> dict[str, Any]:
    try:
        plan = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read plan: {exc}") from exc
    if not isinstance(plan, dict) or plan.get("schema_version") != 1:
        raise ValueError("Run plan schema_version must be 1")
    workflow = parse_workflow_backend(str(
        plan.get("workflow_backend") or HISTORICAL_MISSING_WORKFLOW_BACKEND
    ))
    backend = dict(plan.get("backend_profile") or {})
    if (workflow.workflow_backend != HARAKO_NATIVE_V1
            and (backend.get("nf_core_revision") in {"dev", "latest"}
                 or backend.get("nf_core_revision") != "3.26.0")):
        raise ValueError("nf-core/rnaseq revision must be pinned to 3.26.0")
    route = str(plan.get("execution_route") or ExecutionRoute.GPU_BAM_ALIGNMENT.value)
    quant_only = route == ExecutionRoute.FASTQ_QUANTIFICATION_ONLY.value
    if backend.get("use_parabricks_star") is not (not quant_only):
        raise ValueError("Backend alignment identity conflicts with execution route")
    quantification_data = dict(plan.get("quantification") or {})
    if quantification_data.get("schema_version") == 2:
        validate_versioned_quantification_contract(quantification_data)
    else:
        # Historical schema-v1 plans retain their immutable Salmon 1.10.3
        # compatibility meaning and are never rewritten in place.
        quantification_contract_from_dict(quantification_data)
    try:
        selection = ModeSelection.create(
            AnalysisMode(str(quantification_data["mode"])),
            str(quantification_data["primary_profile_id"]),
        )
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Invalid versioned profile selection: {exc}") from exc
    if quantification_data.get("secondary_profile_id") != selection.secondary_profile_id:
        raise ValueError("Stored secondary profile does not match the fixed mode")
    if quantification_data.get("downstream_primary_profile_id") != selection.primary_profile_id:
        raise ValueError("Missing or mismatched downstream primary profile")
    if quantification_data.get("execution_indices_ready"):
        profiles_data = dict(quantification_data.get("profiles") or {})
        for profile_id in (selection.primary_profile_id, selection.secondary_profile_id):
            if profile_id is None:
                continue
            try:
                index_data = dict(profiles_data[profile_id]["index"])
                index = ProfileIndex(**index_data)
            except (KeyError, TypeError) as exc:
                raise ValueError("Missing fixed execution index contract") from exc
            index.validate()
            reference = dict(plan.get("reference") or {})
            if index.genome_source_sha256 != reference.get("fasta_sha256") or index.gtf_sha256 != reference.get("gtf_sha256"):
                raise ValueError("Execution index biological reference does not match the plan")
    plan_dir = path.expanduser().resolve().parent
    params_path = plan_dir / "nf-params.json"
    try:
        params = json.loads(params_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read nf-params.json: {exc}") from exc
    if quant_only:
        if params != {"execution_route": ExecutionRoute.FASTQ_QUANTIFICATION_ONLY.value}:
            raise ValueError("Quantification-only params contract was mutated")
    elif workflow.workflow_backend == HARAKO_NATIVE_V1:
        required = {
            "input", "outdir", "fasta", "gtf", "star_index", "library_type",
            "featurecounts_feature_type", "featurecounts_group_type",
            "parabricks_two_pass_mode", "parabricks_extra_args",
        }
        if set(params) != required:
            raise ValueError("Harako-native fixed parameter contract was mutated")
        if params["library_type"] not in {"U", "ISF", "ISR"}:
            raise ValueError("Harako-native requires explicit library type")
    else:
        validate_nf_params(params)
    if plan.get("bam_retention") not in {item.value for item in BamRetention}:
        raise ValueError("Invalid BAM retention policy")
    effective_alignment = str(plan.get("alignment_backend") or (
        "none" if quant_only else "parabricks_star"
    ))
    validate_backend_alignment(workflow.workflow_backend, effective_alignment)
    payload = execution_payload(plan)
    if plan.get("minimum_nextflow_version") != "25.04.3" or plan.get("qualified_nextflow_version") != "25.04.3":
        raise ValueError("Run plan Nextflow version contract must be pinned to 25.04.3")
    validate_capability_snapshot_version(str(
        dict(plan.get("capability_snapshot") or {}).get("capability_matrix_version")
    ))
    if plan.get("nextflow_environment") != {"NXF_VER": "25.04.3"}:
        raise ValueError("Run plan must provide structured NXF_VER=25.04.3")
    if quant_only:
        if plan.get("bam_output_mode") != "none" or plan.get("alignment_profile_id") != "none":
            raise ValueError("Quantification-only route must freeze BAM none and alignment none")
        if dict(plan.get("alignment") or {}).get("enabled") is not False:
            raise ValueError("Quantification-only route cannot enable alignment")
    else:
        alignment_profile = get_alignment_profile(str(plan.get("alignment_profile_id")))
        if sha256_payload(dict(plan.get("alignment_profile") or {})) != sha256_payload(alignment_profile.as_dict()):
            raise ValueError("Alignment profile identity does not match the fixed catalog")
    if plan_id_for(payload) != plan.get("plan_id"):
        raise ValueError("plan_id does not match the execution payload")
    if approval_hash_for(payload) != plan.get("approval_hash"):
        raise ValueError("approval_hash does not match the execution payload")
    return {
        "schema_version": 1,
        "valid": True,
        "plan_id": plan["plan_id"],
        "workflow_backend": workflow.workflow_backend,
        "alignment_backend": effective_alignment,
        "warnings": plan.get("warnings", []),
        "unresolved": plan.get("unresolved", []),
    }
