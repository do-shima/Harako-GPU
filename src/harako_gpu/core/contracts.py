"""Versioned Harako-GPU product contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
NF_CORE_PIPELINE = "nf-core/rnaseq"
NF_CORE_RNASEQ_REVISION = "3.26.0"
NF_CORE_REVISION = NF_CORE_RNASEQ_REVISION
MINIMUM_JAVA_MAJOR = 17
MINIMUM_NEXTFLOW_VERSION = "25.04.3"
QUALIFIED_NEXTFLOW_VERSION = "25.04.3"
MINIMUM_WSL_CPU_THREADS = 24
RECOMMENDED_PARABRICKS_HOST_RAM_BYTES = 100 * 1024**3
MINIMUM_WORK_ROOT_FREE_BYTES = 100 * 1024**3
ALIGNER = "star_salmon"
PARABRICKS_CONTAINER_VERSION = "4.6.0-1"
MINIMAL_FEASIBILITY_RESOURCE_CPUS = 8
MINIMAL_FEASIBILITY_RESOURCE_MEMORY = "30.GB"
MINIMAL_FEASIBILITY_RESOURCE_TIME = "2.h"


class BamRetention(StrEnum):
    NONE = "none"
    KEEP = "keep"
    DISCARD_AFTER_VALIDATION = "discard_after_validation"


class MemoryMode(StrEnum):
    STANDARD = "standard"
    LOW_MEMORY_CANDIDATE = "low_memory_candidate"


class QualificationDebugMode(StrEnum):
    DISABLED = "disabled"
    X3 = "x3"


class JavaVersionStatus(StrEnum):
    NOT_TESTED = "NOT_TESTED"
    JAVA_NOT_FOUND = "JAVA_NOT_FOUND"
    JAVA_VERSION_UNSUPPORTED = "JAVA_VERSION_UNSUPPORTED"
    JAVA_VERSION_MALFORMED = "JAVA_VERSION_MALFORMED"
    VERSION_GATE_PASS = "VERSION_GATE_PASS"


class NextflowVersionStatus(StrEnum):
    NOT_TESTED = "NOT_TESTED"
    NEXTFLOW_NOT_FOUND = "NEXTFLOW_NOT_FOUND"
    NEXTFLOW_VERSION_UNSUPPORTED = "NEXTFLOW_VERSION_UNSUPPORTED"
    NEXTFLOW_VERSION_MALFORMED = "NEXTFLOW_VERSION_MALFORMED"
    QUALIFIED_VERSION_MATCH = "QUALIFIED_VERSION_MATCH"
    VERSION_SUPPORTED_BUT_NOT_YET_QUALIFIED = "VERSION_SUPPORTED_BUT_NOT_YET_QUALIFIED"


class PrerequisiteSeverity(StrEnum):
    HARD_BLOCKER = "hard_blocker"
    WARNING = "warning"
    OPTIONAL = "optional"


class QualificationStatus(StrEnum):
    PREFLIGHT_READY = "PREFLIGHT_READY"
    PREFLIGHT_READY_LOW_MEMORY_CANDIDATE = "PREFLIGHT_READY_LOW_MEMORY_CANDIDATE"
    BLOCKED = "BLOCKED"
    NOT_TESTED = "NOT_TESTED"


class IndexStatus(StrEnum):
    PRESENT = "present"
    MISSING = "missing"
    NOT_TESTED = "not_tested"


@dataclass(frozen=True)
class BackendProfile:
    profile_id: str
    nf_core_pipeline: str = NF_CORE_PIPELINE
    nf_core_revision: str = NF_CORE_REVISION
    aligner: str = ALIGNER
    use_parabricks_star: bool = True
    container_engine: str = "docker"
    memory_mode: MemoryMode = MemoryMode.STANDARD
    gpu_selection: str = "all"
    bam_retention: BamRetention = BamRetention.KEEP
    qualification_debug_mode: QualificationDebugMode = QualificationDebugMode.DISABLED
    minimum_nextflow_version: str = MINIMUM_NEXTFLOW_VERSION
    qualified_nextflow_version: str = QUALIFIED_NEXTFLOW_VERSION
    detected_nextflow_version: str | None = None
    nextflow_version_status: NextflowVersionStatus = NextflowVersionStatus.NOT_TESTED
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> None:
        errors: list[str] = []
        if self.schema_version != 1:
            errors.append("backend schema_version must be 1")
        if self.nf_core_pipeline != NF_CORE_PIPELINE:
            errors.append(f"pipeline must be {NF_CORE_PIPELINE}")
        if self.nf_core_revision in {"dev", "latest"} or self.nf_core_revision != NF_CORE_REVISION:
            errors.append(f"revision must be pinned to {NF_CORE_REVISION}")
        quant_only = self.profile_id == "cpu_fastq_quantification_only_v1"
        if self.aligner != ("none" if quant_only else ALIGNER):
            errors.append(f"aligner must be {'none' if quant_only else ALIGNER}")
        if self.use_parabricks_star is not (not quant_only):
            errors.append("Parabricks use must exactly match the fixed execution route" if quant_only
                          else "CPU fallback is forbidden; use_parabricks_star must be true")
        if self.container_engine != "docker":
            errors.append("container_engine must be docker")
        if self.minimum_nextflow_version != MINIMUM_NEXTFLOW_VERSION:
            errors.append(f"minimum Nextflow version must be {MINIMUM_NEXTFLOW_VERSION}")
        if self.qualified_nextflow_version != QUALIFIED_NEXTFLOW_VERSION:
            errors.append(f"qualified Nextflow version must be {QUALIFIED_NEXTFLOW_VERSION}")
        if self.detected_nextflow_version is None and self.nextflow_version_status is not NextflowVersionStatus.NOT_TESTED:
            errors.append("undetected Nextflow must have NOT_TESTED status in a static backend profile")
        if self.qualification_debug_mode is not QualificationDebugMode.DISABLED and self.memory_mode is not MemoryMode.LOW_MEMORY_CANDIDATE:
            errors.append("qualification debug mode is only valid with low_memory_candidate")
        if not self.gpu_selection.strip():
            errors.append("gpu_selection must be explicit")
        if errors:
            raise ValueError("; ".join(errors))

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


def qualified_backend_profile(*, bam_retention: BamRetention, gpu_selection: str,
                              memory_mode: MemoryMode,
                              qualification_debug_mode: QualificationDebugMode = QualificationDebugMode.DISABLED) -> BackendProfile:
    if bam_retention is BamRetention.NONE:
        profile = BackendProfile(
            profile_id="cpu_fastq_quantification_only_v1", aligner="none",
            use_parabricks_star=False, gpu_selection="none", bam_retention=bam_retention,
            memory_mode=memory_mode, qualification_debug_mode=QualificationDebugMode.DISABLED,
        )
        profile.validate()
        return profile
    profile_suffix = "bam_keep" if bam_retention is BamRetention.KEEP else "bam_discard"
    profile = BackendProfile(
        profile_id=f"gpu_alignment_{profile_suffix}",
        bam_retention=bam_retention,
        gpu_selection=gpu_selection,
        memory_mode=memory_mode,
        qualification_debug_mode=qualification_debug_mode,
    )
    profile.validate()
    return profile


def minimal_feasibility_profile(*, bam_retention: BamRetention = BamRetention.KEEP,
                                gpu_selection: str = "all",
                                qualification_debug_mode: QualificationDebugMode = QualificationDebugMode.DISABLED) -> BackendProfile:
    return qualified_backend_profile(
        bam_retention=bam_retention,
        gpu_selection=gpu_selection,
        memory_mode=MemoryMode.LOW_MEMORY_CANDIDATE,
        qualification_debug_mode=qualification_debug_mode,
    )


@dataclass(frozen=True)
class ReferenceContract:
    species: str
    assembly: str
    annotation_provider: str
    annotation_release: str
    fasta_path: str
    fasta_sha256: str
    gtf_path: str
    gtf_sha256: str
    reference_pack_id: str
    transcript_fasta_path: str | None = None
    transcript_fasta_sha256: str | None = None
    parabricks_index_status: IndexStatus = IndexStatus.NOT_TESTED
    salmon_index_status: IndexStatus = IndexStatus.NOT_TESTED
    schema_version: int = SCHEMA_VERSION

    def validate(self, *, require_existing: bool = True) -> None:
        values = asdict(self)
        required = (
            "species", "assembly", "annotation_provider", "annotation_release", "fasta_path",
            "fasta_sha256", "gtf_path", "gtf_sha256", "reference_pack_id",
        )
        missing = [key for key in required if not str(values[key]).strip()]
        if missing:
            raise ValueError("Reference fields are required: " + ", ".join(missing))
        if bool(self.transcript_fasta_path) != bool(self.transcript_fasta_sha256):
            raise ValueError("transcript_fasta_path and transcript_fasta_sha256 must be provided together")
        for label in ("fasta_sha256", "gtf_sha256", "transcript_fasta_sha256"):
            if values[label] is None:
                continue
            digest = str(values[label])
            if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest.lower()):
                raise ValueError(f"{label} must be a 64-character SHA-256")
        if require_existing:
            if not Path(self.fasta_path).is_file():
                raise ValueError(f"FASTA does not exist: {self.fasta_path}")
            if not Path(self.gtf_path).is_file():
                raise ValueError(f"GTF does not exist: {self.gtf_path}")
            if self.transcript_fasta_path and not Path(self.transcript_fasta_path).is_file():
                raise ValueError(f"Transcript FASTA does not exist: {self.transcript_fasta_path}")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GpuInfo:
    name: str
    uuid: str
    total_vram_bytes: int
    free_vram_bytes: int


@dataclass(frozen=True)
class ProbeStatus:
    available: bool | None
    status: str
    detail: str = ""
    stderr: str = ""
    reason_code: str | None = None
    detected_version: str | None = None


@dataclass(frozen=True)
class PrerequisiteFinding:
    code: str
    severity: PrerequisiteSeverity
    active: bool
    detail: str


@dataclass(frozen=True)
class HardwareReport:
    os: str
    execution_context: str
    wsl_status: dict[str, Any]
    cpu: dict[str, Any]
    host_ram_bytes: int | None
    disk: dict[str, Any]
    nvidia_gpus: tuple[GpuInfo, ...]
    driver_version: str | None
    nvidia_smi: ProbeStatus
    docker: ProbeStatus
    docker_gpu_runtime: ProbeStatus
    docker_gpu_access: ProbeStatus
    java: ProbeStatus
    nextflow: ProbeStatus
    nf_core: ProbeStatus
    parabricks_image: ProbeStatus
    cuda_test_image: ProbeStatus
    minimum_nextflow_version: str
    qualified_nextflow_version: str
    detected_nextflow_version: str | None
    nextflow_version_status: NextflowVersionStatus
    prerequisites: tuple[PrerequisiteFinding, ...]
    qualification_status: QualificationStatus
    python: dict[str, Any]
    support_details: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
