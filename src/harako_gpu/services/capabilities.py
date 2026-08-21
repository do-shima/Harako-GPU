"""Fixed host/reference/profile capability matrix and handoff contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from harako_gpu.adapters.execution_context import parse_execution_context
from harako_gpu.adapters.filesystem import write_new_text
from harako_gpu.core.capabilities import (
    CAPABILITY_MATRIX_VERSION, BamOutputMode, CapabilityResult, CapabilityStatus,
    ExecutionRoute, ReferenceResourceClass,
)
from harako_gpu.services.alignment_profiles import ONE_PASS_PROFILE_ID, TWO_PASS_PROFILE_ID
from harako_gpu.services.host_profiles import (
    HostQualificationReceipt, OfflinePlatformImageProvenance,
    ONE_PASS_REPORT_ID, TWO_PASS_REPORT_ID,
    UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID, WINDOWS_HOST_PROFILE_ID,
    get_host_profile,
)


CURRENT_HOST_PROFILE_ID = WINDOWS_HOST_PROFILE_ID
FULL_HUMAN_REFERENCE_PACK_ID = "human_grch38p14_gencode49_harako_gpu_v1"
SMALL_REFERENCE_PACK_ID = "403ab9e9e9877b6ff27d78344113d5bc3cf11ddf92280817e930482b147f40b8"
SMALL_REFERENCE_SHA = {
    "fasta_sha256": "df70973809f672aa58a414fef3f01e0e465bf26f10159174a616b0dee2d458e1",
    "gtf_sha256": "913092a6524a7de2a95c3a1695d0dfc8143f047f4c9c9bc7b206719a7388242a",
    "transcript_fasta_sha256": "4f6a6733546b01a96a71f13c63215d9b854dfb1873c2fa484ed69707d6443ac3",
}
FULL_HUMAN_SHA = {
    "fasta_sha256": "e49b92b3e4f321bf254c042f25b726d9931c4d74c7523e8b6bb530e63b0cfd4b",
    "gtf_sha256": "8eb596086228540c93ccf56fbb6601fd99f19a6df2cecdde239af423e5db0729",
    "transcript_fasta_sha256": "c41a37f792b10399838246200dbaf54a334ec3f514cd36545bb2f9c9995b27ac",
}
HISTORICAL_REPORTS = (
    "medium-human-capacity-resource-envelope",
    "parabricks-one-pass-workstation-profile",
)
HUMAN_QUANTIFICATION_RUNTIME_QUALIFIED = True


@dataclass(frozen=True)
class ReferenceClassification:
    reference_pack_id: str
    resource_class: ReferenceResourceClass
    evidence: tuple[str, ...]


def classify_reference(reference: Mapping[str, Any]) -> ReferenceClassification:
    observed = {key: str(reference.get(key) or "") for key in FULL_HUMAN_SHA}
    if observed == FULL_HUMAN_SHA:
        return ReferenceClassification(
            FULL_HUMAN_REFERENCE_PACK_ID,
            ReferenceResourceClass.FULL_MAMMALIAN_HIGH_MEMORY,
            (
                "exact GRCh38.p14 primary genome SHA-256",
                "exact GENCODE 49 GTF SHA-256",
                "exact GENCODE 49 transcript-target SHA-256",
                "full-human one-pass and two-pass current-host failures retained",
            ),
        )
    if observed == SMALL_REFERENCE_SHA:
        return ReferenceClassification(
            SMALL_REFERENCE_PACK_ID,
            ReferenceResourceClass.SMALL_REFERENCE_QUALIFIED,
            ("exact qualified WT_REP1 small-reference contract",),
        )
    return ReferenceClassification(
        str(reference.get("reference_pack_id") or "unknown"),
        ReferenceResourceClass.CUSTOM_UNQUALIFIED,
        ("no exact reference qualification record",),
    )


def execution_route_for_bam_mode(mode: BamOutputMode) -> ExecutionRoute:
    return (ExecutionRoute.FASTQ_QUANTIFICATION_ONLY if mode is BamOutputMode.NONE
            else ExecutionRoute.GPU_BAM_ALIGNMENT)


def evaluate_capability(*, reference: Mapping[str, Any], bam_output_mode: BamOutputMode,
                        alignment_profile_id: str | None, quantification_mode: str,
                        primary_profile_id: str | None, secondary_profile_id: str | None,
                        execution_context: str = "wsl2:Ubuntu",
                        host_profile_id: str = CURRENT_HOST_PROFILE_ID,
                        runtime_qualified: bool | None = None,
                        host_receipt: HostQualificationReceipt | None = None,
                        report_root: Path | None = None,
                        parabricks_provenance: OfflinePlatformImageProvenance | None = None,
                        observed_parabricks_image: Mapping[str, Any] | None = None) -> CapabilityResult:
    if runtime_qualified is None:
        runtime_qualified = HUMAN_QUANTIFICATION_RUNTIME_QUALIFIED
    classification = classify_reference(reference)
    route = execution_route_for_bam_mode(bam_output_mode)
    forbidden = ("no silent BAM-mode conversion", "no alignment-profile substitution", "no CPU STAR fallback")
    try:
        profile = get_host_profile(host_profile_id)
    except ValueError:
        return _result(CapabilityStatus.NOT_QUALIFIED, route, classification, bam_output_mode,
                       alignment_profile_id, quantification_mode, primary_profile_id,
                       secondary_profile_id, execution_context, host_profile_id, route is ExecutionRoute.GPU_BAM_ALIGNMENT,
                       route is ExecutionRoute.GPU_BAM_ALIGNMENT, "UNKNOWN_HOST_PROFILE",
                       "The requested host has no fixed qualification profile.", forbidden)
    try:
        context_matches = (
            parse_execution_context(profile.execution_context).identity
            == parse_execution_context(execution_context).identity
        )
    except ValueError:
        context_matches = False
    if not context_matches:
        return _result(CapabilityStatus.BLOCKED_IDENTITY_MISMATCH, route, classification,
                       bam_output_mode, alignment_profile_id, quantification_mode, primary_profile_id,
                       secondary_profile_id, execution_context, host_profile_id, route is ExecutionRoute.GPU_BAM_ALIGNMENT,
                       route is ExecutionRoute.GPU_BAM_ALIGNMENT, "HOST_EXECUTION_CONTEXT_MISMATCH",
                       "The requested execution context does not match the fixed host profile.", forbidden)
    receipt_error: str | None = None
    if host_profile_id == UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID:
        if host_receipt is None:
            receipt_error = "installed host qualification receipt is missing"
        else:
            try:
                host_receipt.validate(report_root=report_root or Path(__file__).resolve().parents[3] / "docs/qualification")
            except ValueError as exc:
                receipt_error = str(exc)
    if route is ExecutionRoute.FASTQ_QUANTIFICATION_ONLY:
        if alignment_profile_id not in {None, "none"}:
            return _result(CapabilityStatus.BLOCKED_IDENTITY_MISMATCH, route, classification,
                           bam_output_mode, alignment_profile_id, quantification_mode, primary_profile_id,
                           secondary_profile_id, execution_context, host_profile_id, False, False,
                           "BAM_NONE_ALIGNMENT_ENABLED", "BAM none requires alignment_profile_id=none.", forbidden)
        if primary_profile_id is None:
            return _result(CapabilityStatus.NOT_QUALIFIED, route, classification, bam_output_mode,
                           alignment_profile_id, quantification_mode, primary_profile_id, secondary_profile_id,
                           execution_context, host_profile_id, False, False, "QUANTIFICATION_DISABLED",
                           "BAM none requires an explicit visible Salmon quantification profile.", forbidden)
        if receipt_error:
            return _result(CapabilityStatus.BLOCKED_PROVENANCE, route, classification, bam_output_mode,
                           None, quantification_mode, primary_profile_id, secondary_profile_id,
                           execution_context, host_profile_id, False, False, "HOST_RECEIPT_INVALID",
                           f"Ubuntu host qualification is unavailable: {receipt_error}.", forbidden)
        if classification.resource_class is ReferenceResourceClass.FULL_MAMMALIAN_HIGH_MEMORY:
            if host_profile_id == UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID:
                compatibility_selected = primary_profile_id == "salmon_1_10_3_compatibility" or bool(secondary_profile_id)
                status = (CapabilityStatus.AVAILABLE_WITH_LIMITATION
                          if compatibility_selected else CapabilityStatus.AVAILABLE_QUALIFIED)
                reason = ("UBUNTU_HUMAN_FASTQ_QUANTIFICATION_COMPATIBILITY_LIMITED"
                          if compatibility_selected else "UBUNTU_HUMAN_FASTQ_QUANTIFICATION_QUALIFIED")
                explanation = (
                    "Salmon 1.10.3 is a visible compatibility profile with bounded numerical, not byte-exact, "
                    "descriptive comparison; downstream primary remains explicit and observed agreement never "
                    "causes an automatic profile switch."
                    if compatibility_selected else
                    "The installed Ubuntu evidence receipt qualifies CPU-only Salmon 2.5.1 quantification."
                )
                return _result(status, route, classification, bam_output_mode, None,
                               quantification_mode, primary_profile_id, secondary_profile_id,
                               execution_context, host_profile_id, False, False, reason, explanation, forbidden)
            status = CapabilityStatus.AVAILABLE_QUALIFIED if runtime_qualified else CapabilityStatus.CANDIDATE_REQUIRES_RUNTIME_QUALIFICATION
            if runtime_qualified and secondary_profile_id:
                status = CapabilityStatus.AVAILABLE_WITH_LIMITATION
            return _result(status, route, classification, bam_output_mode, None, quantification_mode,
                           primary_profile_id, secondary_profile_id, execution_context, host_profile_id,
                           False, False, "HUMAN_FASTQ_QUANTIFICATION_CPU_ONLY",
                           "Full-human FASTQ quantification is CPU-only and does not generate BAM or STAR artifacts.", forbidden)
        if classification.resource_class is ReferenceResourceClass.CUSTOM_UNQUALIFIED:
            return _result(CapabilityStatus.UNSUPPORTED_REFERENCE_PROFILE, route, classification,
                           bam_output_mode, None, quantification_mode, primary_profile_id, secondary_profile_id,
                           execution_context, host_profile_id, False, False, "REFERENCE_NOT_QUALIFIED",
                           "This exact reference pack has no quantification-route qualification evidence.", forbidden)
        compatibility_selected = primary_profile_id == "salmon_1_10_3_compatibility" or bool(secondary_profile_id)
        status = CapabilityStatus.AVAILABLE_WITH_LIMITATION if compatibility_selected else CapabilityStatus.AVAILABLE_QUALIFIED
        return _result(status, route, classification, bam_output_mode, None,
                       quantification_mode, primary_profile_id, secondary_profile_id, execution_context,
                       host_profile_id, False, False, "SMALL_REFERENCE_QUANTIFICATION_QUALIFIED",
                       ("The exact small reference is available with the Salmon 1.10.3 bounded-numerical, "
                        "not-byte-exact descriptive limitation; downstream primary remains explicit."
                        if compatibility_selected else
                        "The exact small reference has qualified FASTQ quantification evidence."), forbidden)
    if alignment_profile_id not in {ONE_PASS_PROFILE_ID, TWO_PASS_PROFILE_ID}:
        return _result(CapabilityStatus.UNSUPPORTED_REFERENCE_PROFILE, route, classification, bam_output_mode,
                       alignment_profile_id, quantification_mode, primary_profile_id, secondary_profile_id,
                       execution_context, host_profile_id, True, True, "UNKNOWN_ALIGNMENT_PROFILE",
                       "The requested alignment profile is not fixed in the catalog.", forbidden)
    if receipt_error:
        return _result(CapabilityStatus.BLOCKED_PROVENANCE, route, classification, bam_output_mode,
                       alignment_profile_id, quantification_mode, primary_profile_id,
                       secondary_profile_id, execution_context, host_profile_id, True, True,
                       "HOST_RECEIPT_INVALID",
                       f"Ubuntu host qualification is unavailable: {receipt_error}.", forbidden)
    if classification.resource_class is ReferenceResourceClass.FULL_MAMMALIAN_HIGH_MEMORY:
        if host_profile_id == UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID:
            if primary_profile_id != "salmon_2_5_1_deterministic" or secondary_profile_id:
                return _result(CapabilityStatus.NOT_QUALIFIED, route, classification, bam_output_mode,
                               alignment_profile_id, quantification_mode, primary_profile_id,
                               secondary_profile_id, execution_context, host_profile_id, True, True,
                               "QUANTIFICATION_PROFILE_NOT_QUALIFIED",
                               "Full-human Ubuntu alignment is qualified only with the Salmon 2.5.1 primary profile.", forbidden)
            if parabricks_provenance is None or observed_parabricks_image is None:
                return _result(CapabilityStatus.BLOCKED_PROVENANCE, route, classification, bam_output_mode,
                               alignment_profile_id, quantification_mode, primary_profile_id,
                               secondary_profile_id, execution_context, host_profile_id, True, True,
                               "PARABRICKS_PROVENANCE_MISSING",
                               "The installed Parabricks offline provenance receipt is required.", forbidden)
            try:
                assert host_receipt is not None
                parabricks_provenance.validate(
                    observed_image=observed_parabricks_image,
                    expected_receipt_sha256=host_receipt.parabricks_provenance_receipt_sha256,
                    expected_archive_sha256=host_receipt.parabricks_archive_sha256,
                )
            except ValueError as exc:
                return _result(CapabilityStatus.BLOCKED_PROVENANCE, route, classification, bam_output_mode,
                               alignment_profile_id, quantification_mode, primary_profile_id,
                               secondary_profile_id, execution_context, host_profile_id, True, True,
                               "PARABRICKS_PROVENANCE_INVALID", str(exc), forbidden)
            return _result(CapabilityStatus.AVAILABLE_QUALIFIED, route, classification, bam_output_mode,
                           alignment_profile_id, quantification_mode, primary_profile_id,
                           secondary_profile_id, execution_context, host_profile_id, True, True,
                           "UBUNTU_FULL_HUMAN_GPU_BAM_QUALIFIED",
                           "The installed Ubuntu evidence and offline Parabricks provenance qualify this exact full-human route.", forbidden)
        return _result(CapabilityStatus.UNSUPPORTED_HOST_MEMORY, route, classification, bam_output_mode,
                       alignment_profile_id, quantification_mode, primary_profile_id, secondary_profile_id,
                       execution_context, host_profile_id, True, True, "FULL_HUMAN_PARABRICKS_MEMORY",
                       "Full-human Parabricks alignment exceeded the qualified memory envelope on this host.", forbidden)
    if classification.resource_class is ReferenceResourceClass.SMALL_REFERENCE_QUALIFIED:
        return _result(CapabilityStatus.AVAILABLE_QUALIFIED, route, classification, bam_output_mode,
                       alignment_profile_id, quantification_mode, primary_profile_id, secondary_profile_id,
                       execution_context, host_profile_id, True, True, "SMALL_REFERENCE_GPU_BAM_QUALIFIED",
                       "The exact small reference and requested Parabricks profile are qualified on this host.", forbidden)
    return _result(CapabilityStatus.UNSUPPORTED_REFERENCE_PROFILE, route, classification, bam_output_mode,
                   alignment_profile_id, quantification_mode, primary_profile_id, secondary_profile_id,
                   execution_context, host_profile_id, True, True, "REFERENCE_NOT_QUALIFIED",
                   "This exact reference pack has no GPU-BAM qualification evidence.", forbidden)


def _result(status: CapabilityStatus, route: ExecutionRoute, reference: ReferenceClassification,
            bam: BamOutputMode, alignment: str | None, quant_mode: str, primary: str | None,
            secondary: str | None, context: str, host: str, gpu: bool, bam_generated: bool,
            reason: str, explanation: str, forbidden: tuple[str, ...]) -> CapabilityResult:
    if status is CapabilityStatus.UNSUPPORTED_HOST_MEMORY:
        actions = ("create a BAM-none FASTQ quantification plan", "export high-memory-host handoff")
    elif status is CapabilityStatus.BLOCKED_PROVENANCE:
        actions = ("install and verify the fixed host/provenance receipts",)
    else:
        actions = ("run prepare with the exact frozen plan",)
    reports = ((ONE_PASS_REPORT_ID, TWO_PASS_REPORT_ID)
               if host == UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID else HISTORICAL_REPORTS)
    return CapabilityResult(status, route, host, reference.reference_pack_id, reference.resource_class,
                            bam, alignment, quant_mode, primary, secondary, context, gpu, bam_generated,
                            reason, explanation, reference.evidence, reports, actions, forbidden)


def capability_matrix(*, runtime_qualified: bool | None = None,
                      host_profile_id: str = CURRENT_HOST_PROFILE_ID,
                      execution_context: str = "wsl2:Ubuntu",
                      host_receipt: HostQualificationReceipt | None = None,
                      report_root: Path | None = None,
                      parabricks_provenance: OfflinePlatformImageProvenance | None = None,
                      observed_parabricks_image: Mapping[str, Any] | None = None) -> dict[str, Any]:
    full = {**FULL_HUMAN_SHA, "reference_pack_id": FULL_HUMAN_REFERENCE_PACK_ID}
    small = {**SMALL_REFERENCE_SHA, "assembly": "test-mini",
             "annotation_provider": "nf-core-test-datasets", "reference_pack_id": SMALL_REFERENCE_PACK_ID}
    requests = (
        ("small_one_pass_keep", small, BamOutputMode.KEEP, ONE_PASS_PROFILE_ID, "recommended_only", "salmon_2_5_1_deterministic", None),
        ("small_two_pass_keep", small, BamOutputMode.KEEP, TWO_PASS_PROFILE_ID, "recommended_only", "salmon_2_5_1_deterministic", None),
        ("human_one_pass_keep", full, BamOutputMode.KEEP, ONE_PASS_PROFILE_ID, "recommended_only", "salmon_2_5_1_deterministic", None),
        ("human_two_pass_keep", full, BamOutputMode.KEEP, TWO_PASS_PROFILE_ID, "recommended_only", "salmon_2_5_1_deterministic", None),
        ("human_discard_after_validation", full, BamOutputMode.DISCARD_AFTER_VALIDATION, ONE_PASS_PROFILE_ID, "recommended_only", "salmon_2_5_1_deterministic", None),
        ("human_quant_recommended", full, BamOutputMode.NONE, None, "recommended_only", "salmon_2_5_1_deterministic", None),
        ("human_quant_compare_both", full, BamOutputMode.NONE, None, "compare_both", "salmon_2_5_1_deterministic", "salmon_1_10_3_compatibility"),
    )
    return {"schema_version": 1, "capability_matrix_version": CAPABILITY_MATRIX_VERSION,
            "host_profile_id": host_profile_id,
            "entries": {key: evaluate_capability(reference=reference, bam_output_mode=bam,
                alignment_profile_id=alignment, quantification_mode=mode, primary_profile_id=primary,
                secondary_profile_id=secondary, runtime_qualified=runtime_qualified,
                host_profile_id=host_profile_id, execution_context=execution_context,
                host_receipt=host_receipt, report_root=report_root,
                parabricks_provenance=parabricks_provenance,
                observed_parabricks_image=observed_parabricks_image).as_dict()
                for key, reference, bam, alignment, mode, primary, secondary in requests}}


def validate_capability_snapshot_version(value: str) -> str:
    from harako_gpu.core.capabilities import SUPPORTED_CAPABILITY_MATRIX_VERSIONS
    if value not in SUPPORTED_CAPABILITY_MATRIX_VERSIONS:
        raise ValueError(f"Unsupported capability matrix version: {value}")
    return value


def high_memory_handoff() -> dict[str, Any]:
    return {
        "schema_version": 1, "handoff_id": "full-human-gpu-bam-high-memory-v1",
        "reference_pack_id": FULL_HUMAN_REFERENCE_PACK_ID,
        "reference_checksums": FULL_HUMAN_SHA,
        "star_index_id": "star-2.7.2a-c15a9d6fe6df9716",
        "salmon_index_ids": {"1.10.3": "salmon-1.10.3-52224ad2355cc52b", "2.5.1": "salmon-2.5.1-1c037278d376f40f"},
        "nf_core_revision": "3.26.0", "nextflow_version": "25.04.3",
        "parabricks_image": "nvcr.io/nvidia/clara/clara-parabricks:4.6.0-1",
        "parabricks_image_identity": "sha256:d0761eb4b9921bc046c53520287316d545eb79feaeb8f22387e9bb5734650447",
        "expected_host_class": "NVIDIA GPU host with prospectively qualified >=100 GiB host memory",
        "minimum_vendor_guidance": "size host memory for the selected genome/index and validate before production use",
        "previous_failure_evidence": list(HISTORICAL_REPORTS),
        "profiles": [ONE_PASS_PROFILE_ID, TWO_PASS_PROFILE_ID],
        "command_contracts": {
            "one_pass": ["--low-memory", "--two-pass-mode", "None", "--quantMode", "TranscriptomeSAM", "GeneCounts"],
            "two_pass": ["--low-memory", "--two-pass-mode", "Basic", "--quantMode", "TranscriptomeSAM", "GeneCounts"],
        },
        "input_roles": ["paired_fastq_r1", "paired_fastq_r2"],
        "contains_biological_data": False, "contains_credentials": False,
        "limitations": ["prospective qualification required", "no automatic remote execution"],
    }


def write_handoff(path: Path) -> dict[str, Any]:
    import json
    payload = high_memory_handoff()
    write_new_text(path.expanduser().resolve(), json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return payload
