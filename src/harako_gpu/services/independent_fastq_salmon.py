"""Fail-closed contract for independent FASTQ-mode Salmon quantification."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Iterable


SCHEMA_VERSION = 1
SALMON_VERSION = "1.10.3"
SALMON_IMAGE = "quay.io/biocontainers/salmon:1.10.3--h6dccd9a_2"
SALMON_IMAGE_DIGEST = "sha256:f83ebb158845ee8138d793347f83b92c75e83c58dd8f4600c6fea2a2453ef08e"
SALMON_THREADS = 6
SALMON_LIBRARY_TYPE = "ISR"
SALMON_OPTION_PROFILE_ID = "nfcore-rnaseq-3.26.0-fastq-salmon-isr-v1"
FASTP_VERSION = "1.0.1"
FASTP_IMAGE_DIGEST = "sha256:d228dace961ab50d04471e02e7fd2c8f2b8cd5b1b37be2d4039e2db64fcfae45"
BAM_SALMON_PROCESS = "NFCORE_RNASEQ:RNASEQ:QUANTIFY_BAM_SALMON:SALMON_QUANT"
FASTQ_SALMON_PROCESS = "NFCORE_RNASEQ:RNASEQ:QUANTIFY_PSEUDO_ALIGNMENT:SALMON_QUANT"
STRANDEDNESS_PROBE_PROCESS = (
    "NFCORE_RNASEQ:RNASEQ:FASTQ_QC_TRIM_FILTER_SETSTRANDEDNESS:"
    "FASTQ_SUBSAMPLE_FQ_SALMON:SALMON_QUANT"
)
PSEUDO_TRANSCRIPT_SUMMARIZED_EXPERIMENT_PROCESS = (
    "NFCORE_RNASEQ:RNASEQ:QUANTIFY_PSEUDO_ALIGNMENT:"
    "QUANT_TXIMPORT_SUMMARIZEDEXPERIMENT:SE_TRANSCRIPT_UNIFIED"
)
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class QuantificationBackend(StrEnum):
    FASTQ_SALMON = "fastq_salmon"


class QuantificationMode(StrEnum):
    MAPPING = "mapping"


class QuantificationInput(StrEnum):
    PROCESSED_FASTQ = "processed_fastq"


class AlignmentModeSalmon(StrEnum):
    DISABLED_UNQUALIFIED = "disabled_unqualified"


@dataclass(frozen=True)
class SalmonIndexIdentity:
    salmon_index_id: str
    index_path: str
    index_builder_version: str
    index_builder_image_digest: str
    transcript_fasta_sha256: str
    genome_fasta_sha256: str
    decoys_sha256: str
    index_parameters: tuple[str, ...]
    index_manifest_sha256: str
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Salmon index schema_version must be 1")
        if not self.salmon_index_id.strip() or not self.index_path.strip():
            raise ValueError("Salmon index identity and path are required")
        if self.index_builder_version != SALMON_VERSION:
            raise ValueError(f"Salmon index must be built by {SALMON_VERSION}")
        if self.index_builder_image_digest != SALMON_IMAGE_DIGEST:
            raise ValueError("Salmon index builder image must be pinned to the qualified digest")
        for field in (
            "transcript_fasta_sha256",
            "genome_fasta_sha256",
            "decoys_sha256",
            "index_manifest_sha256",
        ):
            if not _HEX_64.fullmatch(getattr(self, field)):
                raise ValueError(f"{field} must be a lowercase SHA-256")
        if self.index_parameters != ("-k", "31", "decoy_aware_gentrome"):
            raise ValueError("Salmon index parameters must use the fixed decoy-aware k=31 contract")

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class ProcessedFastqIdentity:
    sample_id: str
    r1_sha256: str
    r2_sha256: str
    r1_read_count: int
    r2_read_count: int
    fastp_version: str
    fastp_image_digest: str
    fastp_command_argv: tuple[str, ...]
    strandedness: str
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> None:
        if not self.sample_id.strip():
            raise ValueError("Processed FASTQ sample identity is required")
        for field in ("r1_sha256", "r2_sha256"):
            if not _HEX_64.fullmatch(getattr(self, field)):
                raise ValueError(f"{field} must be a lowercase SHA-256")
        if self.r1_read_count < 1 or self.r1_read_count != self.r2_read_count:
            raise ValueError("Processed paired FASTQ read counts must be equal and non-zero")
        if self.fastp_version != FASTP_VERSION or self.fastp_image_digest != FASTP_IMAGE_DIGEST:
            raise ValueError("fastp version and image digest must match the pinned preprocessing contract")
        if not self.fastp_command_argv or self.fastp_command_argv[0] != "fastp":
            raise ValueError("fastp command must be structured argv")
        if self.strandedness not in {"forward", "reverse", "unstranded", "auto"}:
            raise ValueError("Unsupported processed FASTQ strandedness")

    @property
    def paired_fragment_count(self) -> int:
        return self.r1_read_count

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class FastqSalmonQuantificationContract:
    salmon_index: SalmonIndexIdentity
    quantification_backend: QuantificationBackend = QuantificationBackend.FASTQ_SALMON
    quantification_mode: QuantificationMode = QuantificationMode.MAPPING
    quantification_input: QuantificationInput = QuantificationInput.PROCESSED_FASTQ
    salmon_version: str = SALMON_VERSION
    salmon_image_digest: str = SALMON_IMAGE_DIGEST
    salmon_threads: int = SALMON_THREADS
    salmon_library_type: str = SALMON_LIBRARY_TYPE
    salmon_option_profile_id: str = SALMON_OPTION_PROFILE_ID
    alignment_mode_salmon: AlignmentModeSalmon = AlignmentModeSalmon.DISABLED_UNQUALIFIED
    processed_fastq_identity_required: bool = True
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> None:
        self.salmon_index.validate()
        if self.quantification_backend is not QuantificationBackend.FASTQ_SALMON:
            raise ValueError("quantification_backend must be fastq_salmon")
        if self.quantification_mode is not QuantificationMode.MAPPING:
            raise ValueError("Salmon alignment mode is unqualified and forbidden")
        if self.quantification_input is not QuantificationInput.PROCESSED_FASTQ:
            raise ValueError("Transcriptome BAM input is forbidden")
        if self.salmon_version != SALMON_VERSION or self.salmon_image_digest != SALMON_IMAGE_DIGEST:
            raise ValueError("Salmon backend must be pinned to the qualified version and digest")
        if self.salmon_threads != SALMON_THREADS:
            raise ValueError("Product Salmon thread count must be fixed at 6")
        if self.salmon_library_type != SALMON_LIBRARY_TYPE:
            raise ValueError("Product Salmon library type must be ISR")
        if self.salmon_option_profile_id != SALMON_OPTION_PROFILE_ID:
            raise ValueError("Unknown Salmon option profile")
        if self.alignment_mode_salmon is not AlignmentModeSalmon.DISABLED_UNQUALIFIED:
            raise ValueError("alignment-mode Salmon must remain disabled_unqualified")
        if self.processed_fastq_identity_required is not True:
            raise ValueError("Processed FASTQ identity must be required before execution")

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


def quantification_contract_from_dict(data: dict[str, Any]) -> FastqSalmonQuantificationContract:
    try:
        index_data = dict(data["salmon_index"])
        index_data["index_parameters"] = tuple(index_data["index_parameters"])
        index = SalmonIndexIdentity(**index_data)
        contract = FastqSalmonQuantificationContract(
            salmon_index=index,
            quantification_backend=QuantificationBackend(data["quantification_backend"]),
            quantification_mode=QuantificationMode(data["quantification_mode"]),
            quantification_input=QuantificationInput(data["quantification_input"]),
            salmon_version=str(data["salmon_version"]),
            salmon_image_digest=str(data["salmon_image_digest"]),
            salmon_threads=int(data["salmon_threads"]),
            salmon_library_type=str(data["salmon_library_type"]),
            salmon_option_profile_id=str(data["salmon_option_profile_id"]),
            alignment_mode_salmon=AlignmentModeSalmon(data["alignment_mode_salmon"]),
            processed_fastq_identity_required=data["processed_fastq_identity_required"],
            schema_version=int(data["schema_version"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid FASTQ Salmon quantification contract: {exc}") from exc
    contract.validate()
    return contract


def salmon_mapping_argv(
    *, index: str, gene_map: str, r1: str, r2: str, output: str, threads: int = SALMON_THREADS
) -> tuple[str, ...]:
    if threads != SALMON_THREADS:
        raise ValueError("Product Salmon thread count must be fixed at 6")
    paths = (index, gene_map, r1, r2, output)
    if any(not value or "\x00" in value for value in paths):
        raise ValueError("Salmon paths must be non-empty and contain no NUL")
    return (
        "salmon", "quant", "--geneMap", gene_map, "--threads", str(threads),
        f"--libType={SALMON_LIBRARY_TYPE}", "--index", index,
        "-1", r1, "-2", r2, "-o", output,
    )


def independent_fastq_salmon_config() -> str:
    """Return a precise source-free override; it does not accept user selectors."""

    return (
        "// Harako-GPU independent FASTQ Salmon contract v1.\n"
        "process {\n"
        f"    withName: '{BAM_SALMON_PROCESS}' {{\n"
        "        ext.when = false\n"
        "    }\n"
        f"    withName: '{FASTQ_SALMON_PROCESS}' {{\n"
        f"        cpus = {SALMON_THREADS}\n"
        "    }\n"
        "    // The small empty-tid fixture cannot populate transcript rowData.\n"
        "    // Matrix outputs remain mandatory; only the optional transcript RDS is disabled.\n"
        f"    withName: '{PSEUDO_TRANSCRIPT_SUMMARIZED_EXPERIMENT_PROCESS}' {{\n"
        "        ext.when = false\n"
        "    }\n"
        "}\n"
    )


def independent_fastq_nf_params(*, salmon_index: str) -> dict[str, Any]:
    if not salmon_index or "\x00" in salmon_index:
        raise ValueError("A pinned Salmon index path is required")
    return {
        "pseudo_aligner": "salmon",
        "skip_pseudo_alignment": False,
        "salmon_index": salmon_index,
        "salmon_quant_libtype": SALMON_LIBRARY_TYPE,
        "trimmer": "fastp",
        "save_trimmed": True,
    }


@dataclass(frozen=True)
class SalmonTraceSummary:
    bam_alignment_mode_tasks: int
    fastq_mapping_tasks: int
    strandedness_probe_tasks: int
    unexpected_salmon_tasks: tuple[str, ...]
    cached_fastq_mapping_tasks: int

    def validate_first_run(self, *, samples: int) -> None:
        if self.bam_alignment_mode_tasks:
            raise ValueError("Alignment-mode Salmon task executed")
        if self.unexpected_salmon_tasks:
            raise ValueError("Unexpected Salmon process: " + ", ".join(self.unexpected_salmon_tasks))
        if self.fastq_mapping_tasks != samples:
            raise ValueError("FASTQ Salmon task count does not match the sample count")

    def validate_resume(self, *, samples: int) -> None:
        self.validate_first_run(samples=samples)
        if self.cached_fastq_mapping_tasks != samples:
            raise ValueError("FASTQ Salmon was not fully cached during resume")


def parse_nextflow_trace(text: str) -> SalmonTraceSummary:
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    process_column = "process" if reader.fieldnames and "process" in reader.fieldnames else "name"
    if not reader.fieldnames or process_column not in reader.fieldnames or "status" not in reader.fieldnames:
        raise ValueError("Nextflow trace must contain name/process and status columns")
    bam = fastq = probe = cached = 0
    unexpected: list[str] = []
    for row in reader:
        process = (row.get(process_column) or "").split(" (")[0]
        status = (row.get("status") or "").upper()
        if "SALMON_QUANT" not in process:
            continue
        if process == BAM_SALMON_PROCESS:
            bam += 1
        elif process == FASTQ_SALMON_PROCESS:
            fastq += 1
            cached += status == "CACHED"
        elif process == STRANDEDNESS_PROBE_PROCESS:
            probe += 1
        else:
            unexpected.append(process)
    return SalmonTraceSummary(bam, fastq, probe, tuple(sorted(set(unexpected))), cached)


def validate_salmon_task_argv(argv: Iterable[str]) -> None:
    values = tuple(argv)
    if "-a" in values or "--alignments" in values:
        raise ValueError("Alignment-mode Salmon input is forbidden")
    if len(values) != 15 or values[:2] != ("salmon", "quant"):
        raise ValueError("FASTQ Salmon argv does not match the fixed option profile")
    required = ("--index", "-1", "-2", "--geneMap", f"--libType={SALMON_LIBRARY_TYPE}")
    missing = [token for token in required if token not in values]
    if missing:
        raise ValueError("FASTQ Salmon argv is incomplete: " + ", ".join(missing))
    allowed_options = {
        "--geneMap", "--threads", f"--libType={SALMON_LIBRARY_TYPE}",
        "--index", "-1", "-2", "-o",
    }
    unknown = [token for token in values[2:] if token.startswith("-") and token not in allowed_options]
    if unknown or values[values.index("--threads") + 1] != str(SALMON_THREADS):
        raise ValueError("Arbitrary Salmon arguments are forbidden")


MATRIX_ARTIFACT_NAMES = {
    "transcript_counts": "fastq_salmon.transcript_counts.tsv",
    "transcript_tpm": "fastq_salmon.transcript_tpm.tsv",
    "transcript_effective_length": "fastq_salmon.transcript_effective_length.tsv",
    "gene_counts": "fastq_salmon.gene_counts.tsv",
    "gene_tpm": "fastq_salmon.gene_tpm.tsv",
    "gene_effective_length": "fastq_salmon.gene_effective_length.tsv",
}


def quantification_manifest(
    *, contract: FastqSalmonQuantificationContract, processed_fastq: ProcessedFastqIdentity,
    quant_sf_sha256: str, canonical_numerical_digest: str, tx2gene_sha256: str,
) -> dict[str, Any]:
    contract.validate()
    processed_fastq.validate()
    for name, value in (
        ("quant_sf_sha256", quant_sf_sha256),
        ("canonical_numerical_digest", canonical_numerical_digest),
        ("tx2gene_sha256", tx2gene_sha256),
    ):
        if not _HEX_64.fullmatch(value):
            raise ValueError(f"{name} must be a lowercase SHA-256")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "quantifier": "salmon",
        "version": SALMON_VERSION,
        "input_kind": "processed_fastq",
        "index_id": contract.salmon_index.salmon_index_id,
        "aggregation_method": "nf-core tximport",
        "tx2gene_sha256": tx2gene_sha256,
        "processed_fastq": processed_fastq.as_dict(),
        "quant_sf_sha256": quant_sf_sha256,
        "canonical_numerical_digest": canonical_numerical_digest,
        "alignment_mode_salmon": contract.alignment_mode_salmon,
        "artifacts": MATRIX_ARTIFACT_NAMES,
    }
    identity = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {**payload, "manifest_sha256": hashlib.sha256(identity).hexdigest()}


def validate_multiqc_salmon_sources(sources: Iterable[dict[str, Any]], *, sample_id: str) -> None:
    matched = [item for item in sources if item.get("module") == "salmon" and item.get("sample") == sample_id]
    if len(matched) != 1:
        raise ValueError("MultiQC must contain exactly one FASTQ Salmon source per sample")
    if matched[0].get("mapping_mode") != "fastq":
        raise ValueError("MultiQC Salmon provenance must identify FASTQ mapping mode")
