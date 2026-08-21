"""Pinned Parabricks STAR GeneCounts capability and artifact contracts."""

from __future__ import annotations

import csv
import io
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Iterable, Mapping
from pathlib import Path


PARABRICKS_VERSION = "4.6.0-1"
PARABRICKS_IMAGE_DIGEST = "sha256:d0761eb4b9921bc046c53520287316d545eb79feaeb8f22387e9bb5734650447"
RNABAM_MODULE_BLOB = "ddaf70c77733e4d85a2a912e30d01e82652dba2b"
ALIGN_STAR_CONFIG_BLOB = "3bdcb00cc8855b1604ea63279eaf1d3f8f051ce2"
GENECOUNTS_ARGS = ("--low-memory", "--quantMode", "TranscriptomeSAM", "GeneCounts")
GENECOUNTS_DEBUG_ARGS = ("--low-memory", "--x3", "--quantMode", "TranscriptomeSAM", "GeneCounts")
METADATA_ROWS = ("N_unmapped", "N_multimapping", "N_noFeature", "N_ambiguous")


class StarComparatorStatus(StrEnum):
    AVAILABLE_QUALIFIED = "AVAILABLE_QUALIFIED"
    AVAILABLE_UNQUALIFIED = "AVAILABLE_UNQUALIFIED"
    UNAVAILABLE_NOT_GENERATED = "UNAVAILABLE_NOT_GENERATED"
    UNSUPPORTED_BY_PINNED_BACKEND = "UNSUPPORTED_BY_PINNED_BACKEND"
    INVALID_ARTIFACT = "INVALID_ARTIFACT"
    UNKNOWN_LIBRARY_TYPE = "UNKNOWN_LIBRARY_TYPE"


@dataclass(frozen=True)
class ParabricksGeneCountsCapability:
    transcriptome_sam: bool
    gene_counts: bool
    variadic_quant_mode: bool

    @property
    def supported(self) -> bool:
        return self.transcriptome_sam and self.gene_counts and self.variadic_quant_mode


def parse_parabricks_help(text: str) -> ParabricksGeneCountsCapability:
    normalized = " ".join(text.replace("\x1b", " ").split())
    return ParabricksGeneCountsCapability(
        "TranscriptomeSAM" in normalized,
        "GeneCounts" in normalized and "ReadsPerGene.out.tab" in normalized,
        "--quantMode QUANTMODE [QUANTMODE ...]" in normalized,
    )


def gene_counts_args(*, debug: bool = False) -> tuple[str, ...]:
    return GENECOUNTS_DEBUG_ARGS if debug else GENECOUNTS_ARGS


def replace_quant_mode(existing: Iterable[str], *, debug: bool = False) -> tuple[str, ...]:
    """Replace one fixed nf-core quantMode entry without accepting arbitrary args."""
    values = tuple(existing)
    if values.count("--quantMode TranscriptomeSAM") != 1:
        raise ValueError("Expected exactly one fixed TranscriptomeSAM quantMode entry")
    replacement = "--quantMode TranscriptomeSAM GeneCounts"
    result = tuple(replacement if value == "--quantMode TranscriptomeSAM" else value for value in values)
    if any("--quantMode" in value and value != replacement for value in result):
        raise ValueError("Arbitrary quantMode is forbidden")
    if debug and "--x3" not in result:
        result += ("--x3",)
    return result


@dataclass(frozen=True)
class StarGeneCountsTable:
    metadata: Mapping[str, tuple[int, int, int]]
    genes: Mapping[str, tuple[int, int, int]]

    def selected(self, library_type: str) -> tuple[int, Mapping[str, int]]:
        column = {"U": 2, "unstranded": 2, "ISF": 3, "forward": 3,
                  "ISR": 4, "reverse": 4}.get(library_type)
        if column is None:
            raise ValueError("Unknown/automatic library type cannot select a STAR column")
        offset = column - 2
        return column, {gene: counts[offset] for gene, counts in self.genes.items()}


def parse_reads_per_gene(text: str) -> StarGeneCountsTable:
    metadata: dict[str, tuple[int, int, int]] = {}
    genes: dict[str, tuple[int, int, int]] = {}
    reader = csv.reader(io.StringIO(text), delimiter="\t")
    for line, row in enumerate(reader, 1):
        if len(row) != 4:
            raise ValueError(f"ReadsPerGene line {line} must contain exactly four columns")
        gene = row[0]
        if not gene or gene in metadata or gene in genes:
            raise ValueError(f"Duplicate or empty ReadsPerGene ID: {gene}")
        try:
            counts = tuple(int(value) for value in row[1:])
        except ValueError as exc:
            raise ValueError(f"ReadsPerGene counts must be integers at line {line}") from exc
        if any(value < 0 for value in counts):
            raise ValueError(f"ReadsPerGene counts must be nonnegative at line {line}")
        (metadata if gene in METADATA_ROWS else genes)[gene] = counts  # type: ignore[index]
    if set(metadata) != set(METADATA_ROWS) or not genes:
        raise ValueError("ReadsPerGene must contain four metadata rows and gene rows")
    return StarGeneCountsTable(metadata, genes)


def validate_gene_universe(table: StarGeneCountsTable, gtf_gene_ids: Iterable[str]) -> dict[str, tuple[str, ...]]:
    annotated = set(gtf_gene_ids)
    observed = set(table.genes)
    if not annotated:
        raise ValueError("GTF gene identity is required")
    return {"unexpected_gene_ids": tuple(sorted(observed - annotated)), "missing_gene_ids": tuple(sorted(annotated - observed))}


def column_manifest(*, sample: str, source_file: str, source_sha256: str, library_type: str,
                    gtf_sha256: str, reference_pack_id: str, processed_fastq_sha256: str,
                    run_identity: str) -> dict[str, Any]:
    column = {"U": 2, "ISF": 3, "ISR": 4}.get(library_type)
    if column is None:
        raise ValueError("Explicit U/ISF/ISR library type is required")
    semantics = {2: "unstranded counts", 3: "first-read strand aligned with RNA", 4: "second-read strand aligned with RNA"}
    return {
        "schema_version": 1, "sample": sample, "source_file": source_file,
        "source_sha256": source_sha256, "library_type": library_type,
        "selected_column": column, "column_semantics": semantics[column],
        "star_lineage": "Parabricks rna_fq2bam STAR", "parabricks_version": PARABRICKS_VERSION,
        "image_digest": PARABRICKS_IMAGE_DIGEST, "reference_pack_id": reference_pack_id,
        "gtf_sha256": gtf_sha256, "processed_fastq_sha256": processed_fastq_sha256,
        "run_identity": run_identity,
    }


def selected_counts_tsv(counts: Mapping[str, int]) -> str:
    return "gene_id\tcount\n" + "".join(f"{gene}\t{count}\n" for gene, count in sorted(counts.items()))


def metadata_counts_tsv(metadata: Mapping[str, tuple[int, int, int]], selected_column: int) -> str:
    offset = selected_column - 2
    return "metric\tcount\n" + "".join(f"{key}\t{metadata[key][offset]}\n" for key in METADATA_ROWS)


def resolve_reads_per_gene(paths: Iterable[Path], *, sample: str) -> Path:
    matched = [path for path in paths if path.name == f"{sample}.ReadsPerGene.out.tab" and path.is_file() and path.stat().st_size > 0]
    if len(matched) != 1:
        raise ValueError("Expected exactly one non-empty sample ReadsPerGene artifact")
    return matched[0]
