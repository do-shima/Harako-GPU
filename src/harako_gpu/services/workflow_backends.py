"""Fixed workflow-backend and alignment-adapter product contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import hashlib
from pathlib import Path
from typing import Any, Mapping

from harako_gpu.services.host_profiles import UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID


HARAKO_NATIVE_V1 = "harako_native_v1"
NFCORE_REFERENCE = "nfcore_rnaseq_3_26_reference"
HISTORICAL_MISSING_WORKFLOW_BACKEND = NFCORE_REFERENCE
# Backward-compatible import for callers that mean the historical schema-v1
# interpretation. New-plan selection is deliberately host-aware below.
DEFAULT_WORKFLOW_BACKEND = HISTORICAL_MISSING_WORKFLOW_BACKEND
HARAKO_NATIVE_PUBLIC = "harako-native-v1"
NFCORE_REFERENCE_PUBLIC = "nfcore-rnaseq-3-26-reference"

HARAKO_NATIVE_C1_PARITY_EVIDENCE = (
    (
        "harako-native-vs-nfcore-c1-parity.md",
        "ae2a4e3ada5b2226717b4c5a96190c13911d644deb99893008f431ef0488812c",
    ),
    (
        "harako-native-vs-nfcore-c1-parity.json",
        "8ee18a091408dc4433725ed7515bb3b2210395beede91487ce0adebbc4a37ccc",
    ),
)

HARAKO_NATIVE_IMAGE_CLOSURE_ID = "harako-native-v1-minimal-images-v1"
NFCORE_IMAGE_CLOSURE_ID = "nfcore-rnaseq-3.26.0-full-human-images-v1"
HARAKO_PROCESSED_FASTQ_CONTRACT = "harako-fastp-1.0.1-fixed-v1"
NFCORE_PROCESSED_FASTQ_CONTRACT = "nfcore-rnaseq-3.26.0-fastp-fixed-v1"
CANONICAL_OUTPUT_CONTRACT = "harako-backend-output-manifest-v1"


class AlignmentBackend(StrEnum):
    PARABRICKS_STAR = "parabricks_star"
    STAR_CPU = "star_cpu"
    NONE = "none"


@dataclass(frozen=True)
class WorkflowBackendContract:
    workflow_backend: str
    public_value: str
    qualification_state: str
    supported_alignment_backends: tuple[str, ...]
    requires_nf_schema: bool
    image_closure_id: str
    limitations: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


WORKFLOW_BACKENDS = {
    NFCORE_REFERENCE: WorkflowBackendContract(
        NFCORE_REFERENCE,
        NFCORE_REFERENCE_PUBLIC,
        "AVAILABLE_QUALIFIED_REFERENCE",
        (AlignmentBackend.PARABRICKS_STAR.value, AlignmentBackend.NONE.value),
        True,
        NFCORE_IMAGE_CLOSURE_ID,
        ("comparison/reference backend", "pinned nf-core/rnaseq 3.26.0"),
    ),
    HARAKO_NATIVE_V1: WorkflowBackendContract(
        HARAKO_NATIVE_V1,
        HARAKO_NATIVE_PUBLIC,
        "AVAILABLE_QUALIFIED_UBUNTU_HIGH_MEMORY",
        (AlignmentBackend.PARABRICKS_STAR.value, AlignmentBackend.NONE.value),
        False,
        HARAKO_NATIVE_IMAGE_CLOSURE_ID,
        (
            "qualified only on the receipt-backed Ubuntu high-memory host profile",
            "Windows/WSL scientific execution is not qualified",
        ),
    ),
}


def parse_workflow_backend(value: str) -> WorkflowBackendContract:
    normalized = value.strip().lower().replace("-", "_")
    aliases = {
        HARAKO_NATIVE_V1: HARAKO_NATIVE_V1,
        NFCORE_REFERENCE: NFCORE_REFERENCE,
    }
    try:
        return WORKFLOW_BACKENDS[aliases[normalized]]
    except KeyError as exc:
        raise ValueError(f"Unknown workflow backend: {value}") from exc


def workflow_backend_for_plan(plan: Mapping[str, Any]) -> WorkflowBackendContract:
    """Return the frozen backend; missing means the historical nf-core path."""
    return parse_workflow_backend(str(
        plan.get("workflow_backend") or HISTORICAL_MISSING_WORKFLOW_BACKEND
    ))


def harako_native_parity_evidence_valid(
    qualification_report_root: Path | None = None,
) -> bool:
    """Verify the exact committed C1 one-pass/two-pass parity reports."""
    root = qualification_report_root or (
        Path(__file__).resolve().parents[3] / "docs/qualification"
    )
    for name, expected in HARAKO_NATIVE_C1_PARITY_EVIDENCE:
        path = root / name
        try:
            if not path.is_file():
                return False
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return False
        if actual != expected:
            return False
    return True


def default_workflow_backend_for_new_plan(
    *,
    requested: str | None,
    target: str,
    host_profile_id: str,
    host_receipt_validated: bool,
    qualification_report_root: Path | None = None,
) -> WorkflowBackendContract:
    """Resolve a new plan without changing historical missing-field meaning."""
    if requested is not None:
        return parse_workflow_backend(requested)
    if (
        target == "linux"
        and host_profile_id == UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID
        and host_receipt_validated
        and harako_native_parity_evidence_valid(qualification_report_root)
    ):
        return WORKFLOW_BACKENDS[HARAKO_NATIVE_V1]
    return WORKFLOW_BACKENDS[NFCORE_REFERENCE]


def alignment_backend_for_route(*, quantification_only: bool) -> AlignmentBackend:
    return AlignmentBackend.NONE if quantification_only else AlignmentBackend.PARABRICKS_STAR


def validate_backend_alignment(workflow_backend: str, alignment_backend: str) -> None:
    backend = parse_workflow_backend(workflow_backend)
    try:
        alignment = AlignmentBackend(alignment_backend)
    except ValueError as exc:
        raise ValueError(f"Unknown alignment backend: {alignment_backend}") from exc
    if alignment is AlignmentBackend.STAR_CPU:
        raise ValueError("CPU STAR alignment is NOT_QUALIFIED and unavailable")
    if alignment.value not in backend.supported_alignment_backends:
        raise ValueError("Workflow backend does not support the requested alignment adapter")


def selected_image_roles(
    workflow_backend: str,
    *,
    quantification_only: bool,
    quantification_profiles: tuple[str, ...],
) -> tuple[str, ...]:
    """Return the exact small role set; this is not a runtime plugin registry."""
    backend = parse_workflow_backend(workflow_backend)
    salmon_roles = tuple(quantification_profiles)
    if quantification_only:
        return ("fastp", *salmon_roles)
    if backend.workflow_backend == NFCORE_REFERENCE:
        return ("parabricks", "fastp", *salmon_roles)
    return (
        "parabricks", "fastp", "samtools", "subread_featurecounts", "multiqc",
        *salmon_roles,
    )
