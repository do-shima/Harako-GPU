"""Run-plan serialization contract at the application-service boundary."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from harako_gpu.core.contracts import BackendProfile, BamRetention, NextflowVersionStatus, ReferenceContract, SCHEMA_VERSION
from harako_gpu.core.samples import Sample


@dataclass(frozen=True)
class RunPlan:
    plan_id: str
    approval_hash: str
    project_slug: str
    run_id_proposal: str
    samples: tuple[Sample, ...]
    reference: ReferenceContract
    backend_profile: BackendProfile
    bam_retention: BamRetention
    output_root: str
    work_root: str
    unresolved: tuple[str, ...]
    warnings: tuple[str, ...]
    command_argv: tuple[str, ...]
    nextflow_environment: dict[str, str]
    minimum_nextflow_version: str
    qualified_nextflow_version: str
    detected_nextflow_version: str | None
    nextflow_version_status: NextflowVersionStatus
    quantification: dict[str, Any]
    alignment_profile_id: str
    alignment_profile: dict[str, Any]
    execution_route: str = "gpu_bam_alignment"
    bam_output_mode: str = "keep"
    alignment: dict[str, Any] | None = None
    capability_snapshot: dict[str, Any] | None = None
    workflow_backend: str = "nfcore_rnaseq_3_26_reference"
    alignment_backend: str = "parabricks_star"
    processed_fastq_contract: str = "nfcore-rnaseq-3.26.0-fastp-fixed-v1"
    output_artifact_contract: str = "harako-backend-output-manifest-v1"
    runtime_image_closure: str = "nfcore-rnaseq-3.26.0-full-human-images-v1"
    resource_contract_id: str | None = None
    schema_version: int = SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def execution_payload(plan: RunPlan | dict[str, Any]) -> dict[str, Any]:
    raw = plan.as_dict() if isinstance(plan, RunPlan) else dict(plan)
    keys = (
        "schema_version", "project_slug", "run_id_proposal", "samples", "reference",
        "backend_profile", "bam_retention", "output_root", "work_root", "command_argv",
        "nextflow_environment", "minimum_nextflow_version", "qualified_nextflow_version",
        "detected_nextflow_version", "nextflow_version_status",
        "quantification", "alignment_profile_id", "alignment_profile", "execution_route",
        "bam_output_mode", "alignment", "capability_snapshot",
    )
    payload = {key: raw.get(key) for key in keys}
    # Historical plans predate backend selection. Their existing approval hash
    # excludes these fields and remains valid; new RunPlan objects always carry
    # and hash the explicit backend identity.
    for key in (
        "workflow_backend", "alignment_backend", "processed_fastq_contract",
        "output_artifact_contract", "runtime_image_closure", "resource_contract_id",
    ):
        if key in raw:
            payload[key] = raw[key]
    return payload
