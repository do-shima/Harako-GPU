"""Artifact types and BAM retention state machine."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path


ARTIFACT_SCHEMA_VERSION = 1


class ArtifactType(StrEnum):
    GENOMIC_BAM = "genomic_bam"
    GENOMIC_BAI = "genomic_bai"
    SPLICE_JUNCTIONS = "splice_junctions"
    SALMON_QUANT = "salmon_quant"
    GENE_COUNTS = "gene_counts"
    GENE_TPM = "gene_tpm"
    TRANSCRIPT_COUNTS = "transcript_counts"
    TRANSCRIPT_TPM = "transcript_tpm"
    RAW_TRANSCRIPTOME_BAM = "raw_transcriptome_bam"
    SALMON_READY_TRANSCRIPTOME_BAM = "salmon_ready_transcriptome_bam"
    FASTQ_SALMON_QUANT = "fastq_salmon_quant"
    STAR_GENE_COUNTS = "star_gene_counts"
    TRANSCRIPT_EFFECTIVE_LENGTH = "transcript_effective_length"
    GENE_EFFECTIVE_LENGTH = "gene_effective_length"
    TX2GENE_MANIFEST = "tx2gene_manifest"
    MULTIQC = "multiqc"
    NEXTFLOW_REPORT = "nextflow_report"
    NEXTFLOW_TIMELINE = "nextflow_timeline"
    NEXTFLOW_TRACE = "nextflow_trace"
    HARAKO_REPORT = "harako_report"
    RUN_MANIFEST = "run_manifest"
    HARDWARE_REPORT = "hardware_report"
    VERSIONS = "versions"
    CONTAINER_MANIFEST = "container_manifest"


class BamState(StrEnum):
    PLANNED = "planned"
    GENERATED = "generated"
    VERIFIED = "verified"
    RETAINED = "retained"
    ARCHIVED = "archived"
    DISCARDED_AFTER_VALIDATION = "discarded_after_validation"
    ABSENT_DUE_TO_FAILURE = "absent_due_to_failure"
    NOT_APPLICABLE = "not_applicable"


ALLOWED_BAM_TRANSITIONS: dict[BamState, frozenset[BamState]] = {
    BamState.PLANNED: frozenset({BamState.GENERATED, BamState.ABSENT_DUE_TO_FAILURE}),
    BamState.GENERATED: frozenset({BamState.VERIFIED, BamState.ABSENT_DUE_TO_FAILURE}),
    BamState.VERIFIED: frozenset({BamState.RETAINED, BamState.ARCHIVED, BamState.DISCARDED_AFTER_VALIDATION}),
    BamState.RETAINED: frozenset({BamState.ARCHIVED}),
    BamState.ARCHIVED: frozenset(),
    BamState.DISCARDED_AFTER_VALIDATION: frozenset(),
    BamState.ABSENT_DUE_TO_FAILURE: frozenset(),
    BamState.NOT_APPLICABLE: frozenset(),
}


DISCARD_GATES = (
    "alignment_process_success", "bam_exists", "bam_index_exists", "samtools_quickcheck_success",
    "coordinate_sorted", "reference_contigs_match", "downstream_quantification_success",
    "required_alignment_qc_success", "multiqc_success", "terminal_run_success", "artifact_manifest_finalized",
)


def transition_bam(current: BamState, target: BamState, gates: dict[str, bool] | None = None) -> BamState:
    if target not in ALLOWED_BAM_TRANSITIONS[current]:
        raise ValueError(f"Invalid BAM transition: {current.value} -> {target.value}")
    if target is BamState.DISCARDED_AFTER_VALIDATION:
        missing = [gate for gate in DISCARD_GATES if not bool((gates or {}).get(gate))]
        if missing:
            raise ValueError("BAM discard gates are incomplete: " + ", ".join(missing))
    return target


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_type: ArtifactType
    relative_path: str
    exists: bool
    bam_state: BamState | None = None

    def as_dict(self) -> dict[str, object]:
        return {"schema_version": ARTIFACT_SCHEMA_VERSION, **asdict(self)}


def artifact_response(
    run: Path,
    kind: str,
    relative: str,
    mode: str | None,
    description: str,
    *,
    applicable: bool = True,
) -> dict[str, object]:
    """Port the Harako artifact response fields without output-discovery policy."""
    path = run / Path(relative)
    exists = path.is_file() and applicable
    return {
        "artifact_type": kind,
        "relative_path": Path(relative).as_posix(),
        "exists": exists,
        "size_bytes": int(path.stat().st_size) if exists else None,
        "generated": exists,
        "applicable": applicable,
        "analysis_mode": mode,
        "description": description,
    }
