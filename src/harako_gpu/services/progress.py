"""Stable user-facing stage mapping for verbose Nextflow process identities."""

from __future__ import annotations


PROCESS_STAGE_RULES = (
    ("PARABRICKS_RNA_FQ2BAM", "GPU alignment"),
    ("FASTP", "preprocessing"),
    ("FASTQC", "preprocessing"),
    ("PREPARE_GENOME", "reference preparation"),
    ("SAMTOOLS", "BAM processing"),
    ("PICARD", "BAM processing"),
    ("QUALIMAP", "alignment QC"),
    ("MULTIQC", "report generation"),
)


def user_stage(process_name: str) -> str:
    normalized = process_name.upper()
    for marker, stage in PROCESS_STAGE_RULES:
        if marker in normalized:
            return stage
    return "validation"
