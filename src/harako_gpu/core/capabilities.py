"""Reference-aware execution capability value objects."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


LEGACY_CAPABILITY_MATRIX_VERSION = "reference-aware-capability-v1"
CAPABILITY_MATRIX_VERSION = "reference-aware-capability-v2"
SUPPORTED_CAPABILITY_MATRIX_VERSIONS = frozenset({
    LEGACY_CAPABILITY_MATRIX_VERSION,
    CAPABILITY_MATRIX_VERSION,
})


class ExecutionRoute(StrEnum):
    GPU_BAM_ALIGNMENT = "gpu_bam_alignment"
    FASTQ_QUANTIFICATION_ONLY = "fastq_quantification_only"


class BamOutputMode(StrEnum):
    NONE = "none"
    KEEP = "keep"
    DISCARD_AFTER_VALIDATION = "discard_after_validation"


class ReferenceResourceClass(StrEnum):
    SMALL_REFERENCE_QUALIFIED = "SMALL_REFERENCE_QUALIFIED"
    FULL_MAMMALIAN_HIGH_MEMORY = "FULL_MAMMALIAN_HIGH_MEMORY"
    CUSTOM_UNQUALIFIED = "CUSTOM_UNQUALIFIED"


class CapabilityStatus(StrEnum):
    AVAILABLE_QUALIFIED = "AVAILABLE_QUALIFIED"
    AVAILABLE_WITH_LIMITATION = "AVAILABLE_WITH_LIMITATION"
    CANDIDATE_REQUIRES_RUNTIME_QUALIFICATION = "CANDIDATE_REQUIRES_RUNTIME_QUALIFICATION"
    UNSUPPORTED_HOST_MEMORY = "UNSUPPORTED_HOST_MEMORY"
    UNSUPPORTED_REFERENCE_PROFILE = "UNSUPPORTED_REFERENCE_PROFILE"
    NOT_QUALIFIED = "NOT_QUALIFIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    BLOCKED_IDENTITY_MISMATCH = "BLOCKED_IDENTITY_MISMATCH"
    BLOCKED_PROVENANCE = "BLOCKED_PROVENANCE"


@dataclass(frozen=True)
class CapabilityResult:
    status: CapabilityStatus
    requested_route: ExecutionRoute
    host_profile_id: str
    reference_pack_id: str
    reference_resource_class: ReferenceResourceClass
    bam_output_mode: BamOutputMode
    alignment_profile_id: str | None
    quantification_mode: str
    primary_quantification_profile: str | None
    secondary_quantification_profile: str | None
    execution_context: str
    gpu_used: bool
    bam_generated: bool
    reason_code: str
    explanation: str
    technical_evidence: tuple[str, ...]
    qualification_report_ids: tuple[str, ...]
    allowed_next_actions: tuple[str, ...]
    forbidden_fallback: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
