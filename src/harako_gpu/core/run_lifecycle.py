"""Immutable run identities and explicit execution state transitions."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from harako_gpu.core.canonical import sha256_payload


RUN_SCHEMA_VERSION = 1
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")


class RunState(StrEnum):
    PREPARED = "PREPARED"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_LIMITATION = "COMPLETED_WITH_LIMITATION"
    RETENTION_PENDING = "RETENTION_PENDING"


class AttemptState(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"


class TaskState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CACHED = "CACHED"
    INTERRUPTED = "INTERRUPTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ArtifactState(StrEnum):
    EXPECTED = "EXPECTED"
    PRESENT = "PRESENT"
    VALIDATED = "VALIDATED"
    MISSING = "MISSING"
    INVALID = "INVALID"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    RETENTION_PENDING = "RETENTION_PENDING"


class FailureClassification(StrEnum):
    PREPARE_VALIDATION = "PREPARE_VALIDATION"
    RUNTIME_PREREQUISITE = "RUNTIME_PREREQUISITE"
    PIPELINE_IDENTITY = "PIPELINE_IDENTITY"
    PATCH_IDENTITY = "PATCH_IDENTITY"
    REFERENCE = "REFERENCE"
    INDEX = "INDEX"
    DOCKER = "DOCKER"
    GPU_ACCESS = "GPU_ACCESS"
    NEXTFLOW = "NEXTFLOW"
    PREPROCESSING = "PREPROCESSING"
    PARABRICKS = "PARABRICKS"
    VRAM = "VRAM"
    HOST_RAM = "HOST_RAM"
    DISK = "DISK"
    BAM_VALIDATION = "BAM_VALIDATION"
    STAR_GENECOUNTS = "STAR_GENECOUNTS"
    SALMON_PRIMARY = "SALMON_PRIMARY"
    SALMON_SECONDARY = "SALMON_SECONDARY"
    MATRIX = "MATRIX"
    CONCORDANCE = "CONCORDANCE"
    REPORT = "REPORT"
    ARTIFACT_VALIDATION = "ARTIFACT_VALIDATION"
    INTERRUPTION = "INTERRUPTION"
    UNKNOWN = "UNKNOWN"


class StageId(StrEnum):
    PREFLIGHT = "01_preflight_revalidation"
    NFCORE = "02_preprocessing_or_nfcore_alignment"
    ALIGNMENT_VALIDATION = "03_processed_input_or_alignment_validation"
    SALMON_PRIMARY = "04_salmon_primary"
    SALMON_SECONDARY = "05_salmon_secondary"
    MATRICES = "06_profile_matrices"
    STAR_COUNTS = "07_star_gene_counts_selection"
    CONCORDANCE = "08_concordance"
    REPORT = "09_self_contained_report"
    ARTIFACTS = "10_artifact_inventory_verification"
    TERMINAL = "11_terminal_status"


STAGE_ORDER = tuple(StageId)


_ALLOWED_RUN_TRANSITIONS = {
    RunState.PREPARED: {RunState.RUNNING},
    RunState.RUNNING: {
        RunState.COMPLETED, RunState.COMPLETED_WITH_LIMITATION,
        RunState.RETENTION_PENDING, RunState.FAILED, RunState.INTERRUPTED,
    },
    RunState.FAILED: {RunState.RUNNING},
    RunState.INTERRUPTED: {RunState.RUNNING},
    RunState.BLOCKED: set(),
    RunState.COMPLETED: set(),
    RunState.COMPLETED_WITH_LIMITATION: set(),
    RunState.RETENTION_PENDING: set(),
}


def transition_run(current: RunState, target: RunState, *, resume: bool = False) -> RunState:
    if target not in _ALLOWED_RUN_TRANSITIONS[current]:
        raise ValueError(f"Forbidden run transition: {current.value} -> {target.value}")
    if current in {RunState.FAILED, RunState.INTERRUPTED} and target is RunState.RUNNING and not resume:
        raise ValueError("FAILED/INTERRUPTED runs may return to RUNNING only through resume")
    return target


_ALLOWED_ATTEMPT_TRANSITIONS = {
    AttemptState.CREATED: {AttemptState.RUNNING},
    AttemptState.RUNNING: {AttemptState.SUCCEEDED, AttemptState.FAILED, AttemptState.INTERRUPTED},
    AttemptState.SUCCEEDED: set(), AttemptState.FAILED: set(), AttemptState.INTERRUPTED: set(),
}


def transition_attempt(current: AttemptState, target: AttemptState) -> AttemptState:
    if target not in _ALLOWED_ATTEMPT_TRANSITIONS[current]:
        raise ValueError(f"Forbidden attempt transition: {current.value} -> {target.value}")
    return target


@dataclass(frozen=True)
class FailureRecord:
    classification: FailureClassification
    stage: str
    task: str | None
    process: str | None
    exit_code: int | None
    message: str
    user_explanation: str
    technical_detail: str
    log_paths: tuple[str, ...]
    resumable: bool
    recommended_action: str

    def validate(self) -> None:
        if not self.stage or not self.message or not self.user_explanation or not self.recommended_action:
            raise ValueError("Failure record requires stage, message, explanation, and action")
        if "cpu fallback" in self.recommended_action.casefold():
            raise ValueError("CPU fallback must not be recommended")


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    stage_id: str
    sample: str | None
    profile_id: str | None
    input_identity: str
    command_identity: str
    image_identity: str | None
    state: TaskState = TaskState.PENDING
    attempt: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    exit_code: int | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None
    expected_outputs: tuple[str, ...] = ()
    output_validation: str = "NOT_RUN"
    resumable: bool = True
    cached: bool = False
    failure_classification: str | None = None

    def validate(self) -> None:
        if not self.task_id or self.stage_id not in {item.value for item in StageId}:
            raise ValueError("Task ID and fixed stage ID are required")
        if not self.input_identity or not self.command_identity:
            raise ValueError("Task input and command identities are required")


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    role: str
    profile_id: str | None
    sample: str | None
    path_role: str
    relative_path: str
    media_type: str
    size: int | None
    source_stage: str
    source_task: str
    required: bool
    state: ArtifactState
    structural_validation: str = "NOT_RUN"
    scientific_validation: str = "NOT_RUN"
    sha256_status: str = "NOT_COMPUTED"
    sha256: str | None = None
    retention_state: str = "RETAIN"
    user_facing: bool = True
    limitation: str | None = None
    alignment_profile_id: str | None = None

    def validate(self) -> None:
        if not self.artifact_id or not self.role or not self.relative_path:
            raise ValueError("Artifact identity, role, and relative path are required")
        if self.relative_path.startswith(("/", "\\")) or ".." in self.relative_path.replace("\\", "/").split("/"):
            raise ValueError("Artifact paths must be safe relative paths")
        if self.size is not None and self.size < 0:
            raise ValueError("Artifact size cannot be negative")


@dataclass(frozen=True)
class RunIdentity:
    run_id: str
    project_slug: str
    plan_id: str
    approval_hash: str
    analysis_series_id: str
    primary_profile_id: str
    secondary_profile_id: str | None
    comparison_mode: str
    reference_pack_id: str
    fasta_sha256: str
    gtf_sha256: str
    tx2gene_sha256: str
    samplesheet_sha256: str
    processed_input_contract: str
    nf_core_revision: str
    resolved_pipeline_commit: str
    nextflow_version: str
    parabricks_image_identity: str
    patch_set_identity: str
    salmon_image_identities: Mapping[str, str]
    salmon_index_identities: Mapping[str, str]
    gene_counts_contract_version: str
    created_at: str
    execution_context: str
    output_root: str
    work_root: str
    launch_directory: str
    alignment_profile_id: str = "parabricks_star_two_pass_high_memory"
    two_pass: bool = True
    annotation_backed: bool = True
    alignment_profile_limitations: tuple[str, ...] = ()
    execution_route: str = "gpu_bam_alignment"
    bam_output_mode: str = "keep"
    gpu_used: bool = True
    workflow_backend: str = "nfcore_rnaseq_3_26_reference"
    alignment_backend: str = "parabricks_star"
    output_artifact_contract: str = "harako-backend-output-manifest-v1"
    schema_version: int = RUN_SCHEMA_VERSION

    def validate(self) -> None:
        if self.schema_version != 1 or not RUN_ID_RE.fullmatch(self.run_id):
            raise ValueError("Run identity schema/run ID is invalid")
        required = (
            self.project_slug, self.plan_id, self.approval_hash, self.analysis_series_id,
            self.primary_profile_id, self.reference_pack_id, self.fasta_sha256,
            self.gtf_sha256, self.tx2gene_sha256, self.samplesheet_sha256,
            self.resolved_pipeline_commit, self.nextflow_version,
            self.parabricks_image_identity, self.patch_set_identity,
            self.output_root, self.work_root, self.launch_directory,
            self.alignment_profile_id,
        )
        if any(not value for value in required):
            raise ValueError("Run identity fields must be complete")
        if self.output_root.startswith(("/mnt/c", "/mnt/d")) or self.work_root.startswith(("/mnt/c", "/mnt/d")):
            raise ValueError("Runtime output/work must use Linux filesystem, not Windows mounts")
        if not self.output_root.startswith("/") or not self.work_root.startswith("/"):
            raise ValueError("Canonical runtime paths must be Linux absolute paths")
        if self.nextflow_version != "25.04.3":
            raise ValueError("Pipeline/Nextflow identity mismatch")
        if self.workflow_backend == "nfcore_rnaseq_3_26_reference":
            if self.nf_core_revision != "3.26.0":
                raise ValueError("nf-core reference pipeline identity mismatch")
        elif self.workflow_backend == "harako_native_v1":
            if self.nf_core_revision != "harako-native-v1":
                raise ValueError("Harako-native pipeline identity mismatch")
        else:
            raise ValueError("Unknown frozen workflow backend")
        if self.alignment_backend == "star_cpu":
            raise ValueError("CPU STAR alignment is not qualified")
        if self.execution_route == "fastq_quantification_only":
            if self.bam_output_mode != "none" or self.gpu_used or self.alignment_profile_id != "none":
                raise ValueError("Quantification-only run identity is inconsistent")
        if not self.salmon_image_identities or not self.salmon_index_identities:
            raise ValueError("Profile image/index identities are required")

    @property
    def identity_digest(self) -> str:
        self.validate()
        return sha256_payload({"kind": "harako-run-identity-v1", "payload": asdict(self)})

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return {**asdict(self), "identity_digest": self.identity_digest}


@dataclass(frozen=True)
class RunStatus:
    run_id: str
    state: RunState
    current_stage: str | None
    current_task: str | None
    attempt_id: str | None
    updated_at: str
    started_at: str | None = None
    ended_at: str | None = None
    task_counts: Mapping[str, int] = field(default_factory=dict)
    process_counts: Mapping[str, int] = field(default_factory=dict)
    resource_snapshot: Mapping[str, Any] = field(default_factory=dict)
    artifact_status: Mapping[str, int] = field(default_factory=dict)
    resumable: bool = False
    failure: Mapping[str, Any] | None = None
    warnings: tuple[str, ...] = ()
    next_actions: tuple[str, ...] = ()
    schema_version: int = RUN_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
