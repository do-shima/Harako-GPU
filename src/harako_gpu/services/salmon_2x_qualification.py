"""Fail-closed Salmon 2.5.1 deterministic candidate qualification contracts."""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any, Iterable, Mapping, Sequence

from harako_gpu.services.independent_fastq_salmon import (
    BAM_SALMON_PROCESS,
    FASTQ_SALMON_PROCESS,
)
from harako_gpu.services.salmon_reproducibility import (
    QuantTable,
    SalmonMetadataIdentity,
    canonical_numerical_digest,
)


SCHEMA_VERSION = 1
CANDIDATE_VERSION = "2.5.1"
CANDIDATE_RELEASE_TAG = "v2.5.1"
CANDIDATE_SOURCE_COMMIT = "c360459bbf16e649a5c10c097e59f3c72e6b2e3c"
CANDIDATE_ASSET_NAME = "salmon-cli-x86_64-unknown-linux-gnu.tar.xz"
CANDIDATE_ASSET_SHA256 = "6ad2a01b2022092f88f4c95601d19751e594dd3aa7be77ee7c11c1abf4842cbe"
CANDIDATE_SOURCE_ARCHIVE_SHA256 = "6adde21a2baa6d0c3b8725e3180f7228b2c8a913668a81130990e6fb4dbd6036"
CANDIDATE_LOCAL_IMAGE = "harako-gpu/salmon:2.5.1-qualification"
CANDIDATE_PROFILE_ID = "fastq_salmon_2_5_1_deterministic_candidate"
CANDIDATE_DIAGNOSTIC_PROFILE_ID = "fastq_salmon_2_5_1_online_diagnostic"
CANDIDATE_THREADS = 6
CANDIDATE_LIBRARY_TYPE = "ISR"
CANDIDATE_DECODER = "serial"
CANDIDATE_IMPLEMENTATION = "rust"
TRUTH_FIXTURE_ID = "harako_truth_bulk_v1"
REPRODUCIBILITY_CLASS = "exact"
SALMON_INDEX_PROCESS = "NFCORE_RNASEQ:PREPARE_GENOME:SALMON_INDEX"
BASE_IMAGE = "debian:12.11-slim"
BASE_IMAGE_DIGEST = "sha256:b1a741487078b369e78119849663d7f1a5341ef2768798f7b7406c4240f86aef"
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")


class CandidateStatus(StrEnum):
    QUALIFICATION_ONLY = "qualification_only"
    DIRECT_GATES_PASSED = "direct_gates_passed"
    CANDIDATE_QUALIFIED = "candidate_qualified"
    REJECTED = "rejected"


class TruthStratum(StrEnum):
    UNIQUE_IDENTIFIABLE = "unique_identifiable"
    AMBIGUOUS_ISOFORM = "ambiguous_isoform"
    PARALOG_GROUP = "paralog_group"
    ZERO_EXPRESSION = "zero_expression"


@dataclass(frozen=True)
class CandidateReleaseIdentity:
    version: str = CANDIDATE_VERSION
    release_tag: str = CANDIDATE_RELEASE_TAG
    source_commit: str = CANDIDATE_SOURCE_COMMIT
    asset_name: str = CANDIDATE_ASSET_NAME
    asset_sha256: str = CANDIDATE_ASSET_SHA256
    source_archive_sha256: str = CANDIDATE_SOURCE_ARCHIVE_SHA256
    implementation: str = CANDIDATE_IMPLEMENTATION
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> None:
        if self != CandidateReleaseIdentity():
            raise ValueError("Salmon candidate is not the pinned 2.5.1 Rust release")


@dataclass(frozen=True)
class CandidateImageIdentity:
    image: str
    image_id: str
    config_digest: str
    dockerfile_sha256: str
    salmon_version_output: str

    def validate(self) -> None:
        if self.image != CANDIDATE_LOCAL_IMAGE:
            raise ValueError("Candidate image must use the qualification-only local tag")
        if not _IMAGE_ID.fullmatch(self.image_id) or not _IMAGE_ID.fullmatch(self.config_digest):
            raise ValueError("Candidate image and config identities must be pinned SHA-256 values")
        if not _HEX_64.fullmatch(self.dockerfile_sha256):
            raise ValueError("Dockerfile SHA-256 is required")
        if self.salmon_version_output.strip() != "salmon 2.5.1":
            raise ValueError("Candidate binary did not report Salmon 2.5.1")


@dataclass(frozen=True)
class CandidateIndexIdentity:
    salmon_index_id: str
    index_builder_version: str
    index_builder_image_id: str
    transcript_fasta_sha256: str
    genome_fasta_sha256: str
    gentrome_sha256: str
    decoys_sha256: str
    kmer_size: int
    index_inventory_sha256: str
    index_format: str = "piscem-cf1-rs"
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "builder_version": self.index_builder_version,
            "builder_image": self.index_builder_image_id,
            "transcript_fasta": self.transcript_fasta_sha256,
            "genome_fasta": self.genome_fasta_sha256,
            "gentrome": self.gentrome_sha256,
            "decoys": self.decoys_sha256,
            "kmer_size": self.kmer_size,
            "inventory": self.index_inventory_sha256,
            "index_format": self.index_format,
        }

    @property
    def expected_index_id(self) -> str:
        encoded = json.dumps(self._identity_payload(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()

    def validate(self, *, salmon_version: str = CANDIDATE_VERSION) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Candidate index schema version is unsupported")
        if salmon_version != CANDIDATE_VERSION or self.index_builder_version != CANDIDATE_VERSION:
            raise ValueError("Salmon 2.5.1 requires an index built by Salmon 2.5.1")
        if not _IMAGE_ID.fullmatch(self.index_builder_image_id):
            raise ValueError("Candidate index builder image identity must be pinned")
        hashes = (
            self.transcript_fasta_sha256, self.genome_fasta_sha256,
            self.gentrome_sha256, self.decoys_sha256, self.index_inventory_sha256,
        )
        if not all(_HEX_64.fullmatch(value) for value in hashes):
            raise ValueError("Candidate index sources and inventory require SHA-256 identities")
        if self.kmer_size != 31 or self.index_format != "piscem-cf1-rs":
            raise ValueError("Candidate index must be the Salmon 2.x PISCEM k=31 format")
        if self.salmon_index_id != self.expected_index_id:
            raise ValueError("Candidate index ID does not match its scientific identity")


def validate_asset_sha256(actual: str) -> None:
    if actual != CANDIDATE_ASSET_SHA256:
        raise ValueError("Official Salmon 2.5.1 asset SHA-256 mismatch")


def validate_source_archive_sha256(actual: str) -> None:
    if actual != CANDIDATE_SOURCE_ARCHIVE_SHA256:
        raise ValueError("Official Salmon 2.5.1 source archive SHA-256 mismatch")


def deterministic_mapping_argv(
    *, index: str, gene_map: str, r1: str, r2: str, output: str,
    threads: int = CANDIDATE_THREADS,
) -> tuple[str, ...]:
    if threads not in {1, 2, 4, 6}:
        raise ValueError("Qualification threads must be one of 1, 2, 4, or 6")
    paths = (index, gene_map, r1, r2, output)
    if any(not value or "\x00" in value for value in paths):
        raise ValueError("Candidate Salmon paths must be non-empty and contain no NUL")
    return (
        "salmon", "quant", "--deterministic", "--decoder", CANDIDATE_DECODER,
        "--geneMap", gene_map, "--threads", str(threads),
        f"--libType={CANDIDATE_LIBRARY_TYPE}", "--index", index,
        "-1", r1, "-2", r2, "-o", output,
    )


def validate_deterministic_argv(argv: Iterable[str]) -> None:
    values = tuple(argv)
    if values[:2] != ("salmon", "quant") or len(values) != 18:
        raise ValueError("Candidate argv does not match the fixed deterministic profile")
    if "--deterministic" not in values or values[values.index("--decoder") + 1] != "serial":
        raise ValueError("Deterministic serial decoding is mandatory")
    forbidden = {"-a", "--alignments", "--sketch", "--seqBias", "--gcBias", "--posBias"}
    if forbidden & set(values):
        raise ValueError("BAM, sketch, and bias options are forbidden in this profile")
    allowed = {
        "--deterministic", "--decoder", "--geneMap", "--threads", "--libType=ISR",
        "--index", "-1", "-2", "-o",
    }
    unknown = [value for value in values[2:] if value.startswith("-") and value not in allowed]
    if unknown:
        raise ValueError("Arbitrary Salmon arguments are forbidden")


@dataclass(frozen=True)
class ExactRunIdentity:
    quant_sf_sha256: str
    gene_quant_sha256: str
    canonical_numerical_digest: str
    scientific_meta_sha256: str
    num_processed: int
    num_mapped: int
    partial_rad_signature: bool = False

    def validate(self, *, expected_fragments: int) -> None:
        for field in (
            "quant_sf_sha256", "gene_quant_sha256", "canonical_numerical_digest",
            "scientific_meta_sha256",
        ):
            if not _HEX_64.fullmatch(getattr(self, field)):
                raise ValueError(f"{field} must be SHA-256")
        if self.num_processed != expected_fragments:
            raise ValueError("Salmon did not process the absolute input fragment count")
        if not 0 <= self.num_mapped <= self.num_processed:
            raise ValueError("Mapped fragment accounting is invalid")
        if self.partial_rad_signature:
            raise ValueError("Partial or truncated RAD output signature detected")


def validate_exact_repeats(runs: Sequence[ExactRunIdentity], *, expected_fragments: int) -> None:
    if not runs:
        raise ValueError("At least one deterministic run is required")
    for run in runs:
        run.validate(expected_fragments=expected_fragments)
    if len(set(runs)) != 1:
        raise ValueError("Deterministic Salmon outputs are not exact across runs or threads")


@dataclass(frozen=True)
class TruthFeature:
    transcript_id: str
    gene_id: str
    stratum: TruthStratum
    expressed_fragments: int
    group_id: str


@dataclass(frozen=True)
class AccuracyVector:
    count: int
    pearson: float
    spearman: float
    median_absolute_percentage_error: float
    p95_absolute_percentage_error: float


@dataclass(frozen=True)
class TruthAccuracyReport:
    fragment_accounting_exact: bool
    estimated_mass_accounting_exact: bool
    expressed_zero_transitions: int
    unique_transcripts: AccuracyVector
    expressed_genes: AccuracyVector
    ambiguous_group_max_relative_error: float
    zero_false_positive_mass_fraction: float
    high_expression_false_positives: int
    decoy_leakage_fraction: float
    fold_change_direction_accuracy: float
    fold_change_rmse: float
    fold_change_spearman: float

    @property
    def passed(self) -> bool:
        return all((
            self.fragment_accounting_exact,
            self.estimated_mass_accounting_exact,
            self.expressed_zero_transitions == 0,
            self.unique_transcripts.pearson >= 0.995,
            self.unique_transcripts.spearman >= 0.995,
            self.unique_transcripts.median_absolute_percentage_error <= 0.05,
            self.unique_transcripts.p95_absolute_percentage_error <= 0.15,
            self.expressed_genes.pearson >= 0.995,
            self.expressed_genes.spearman >= 0.995,
            self.expressed_genes.median_absolute_percentage_error <= 0.05,
            self.expressed_genes.p95_absolute_percentage_error <= 0.15,
            self.ambiguous_group_max_relative_error <= 0.05,
            self.zero_false_positive_mass_fraction <= 0.005,
            self.high_expression_false_positives == 0,
            self.decoy_leakage_fraction <= 0.01,
            self.fold_change_direction_accuracy == 1.0,
            self.fold_change_rmse <= 0.25,
            self.fold_change_spearman >= 0.95,
        ))


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(enumerate(values), key=lambda item: item[1])
    result = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and order[end][1] == order[cursor][1]:
            end += 1
        rank = (cursor + 1 + end) / 2
        for original, _ in order[cursor:end]:
            result[original] = rank
        cursor = end
    return result


def _correlation(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Correlation requires equal non-empty vectors")
    mean_left = statistics.fmean(left)
    mean_right = statistics.fmean(right)
    numerator = sum((a - mean_left) * (b - mean_right) for a, b in zip(left, right))
    denominator = math.sqrt(
        sum((a - mean_left) ** 2 for a in left) *
        sum((b - mean_right) ** 2 for b in right)
    )
    return numerator / denominator if denominator else (1.0 if list(left) == list(right) else 0.0)


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def accuracy_vector(truth: Mapping[str, int], estimated: Mapping[str, Decimal]) -> AccuracyVector:
    ids = sorted(truth)
    if not ids or any(truth[name] <= 0 for name in ids):
        raise ValueError("Accuracy vectors require positive truth counts")
    expected = [float(truth[name]) for name in ids]
    observed = [float(estimated.get(name, Decimal(0))) for name in ids]
    ape = [abs(a - b) / a for a, b in zip(expected, observed)]
    return AccuracyVector(
        count=len(ids), pearson=_correlation(expected, observed),
        spearman=_correlation(_ranks(expected), _ranks(observed)),
        median_absolute_percentage_error=statistics.median(ape),
        p95_absolute_percentage_error=_percentile(ape, 0.95),
    )


def quant_num_reads(table: QuantTable) -> dict[str, Decimal]:
    return {row.transcript_id: row.num_reads for row in table.rows}


def build_truth_accuracy_report(
    *, manifest: Mapping[str, Any], quant_by_sample: Mapping[str, QuantTable],
    metadata_by_sample: Mapping[str, SalmonMetadataIdentity],
) -> TruthAccuracyReport:
    """Compare Salmon estimates with the predeclared independent fragment truth."""

    transcript_rows = {row["transcript_id"]: row for row in manifest["transcripts"]}
    sample_rows = {row["sample"]: row for row in manifest["samples"]}
    if set(quant_by_sample) != set(sample_rows) or set(metadata_by_sample) != set(sample_rows):
        raise ValueError("Truth quantification samples do not match the fixture manifest")
    # The Rust 2.x quant.sf retains decoy reference rows (normally with zero
    # estimated mass), unlike the 1.x table.  They are permitted but never
    # treated as transcript features.  The fixture declares their count and
    # stable ``decoy_NN`` identity.
    decoy_ids = {f"decoy_{number:02d}" for number in range(1, int(manifest["decoy_count"]) + 1)}
    expected_ids = set(transcript_rows) | decoy_ids
    unique_truth: dict[str, int] = {}
    unique_estimated: dict[str, Decimal] = {}
    gene_truth: dict[str, int] = {}
    gene_estimated: dict[str, Decimal] = {}
    group_truth: dict[str, int] = {}
    group_estimated: dict[str, Decimal] = {}
    zero_estimated = Decimal(0)
    total_mapped = 0
    total_estimated = Decimal(0)
    total_transcript_origin = 0
    total_decoy_origin = 0
    expressed_zero_transitions = 0
    fragment_exact = True
    mass_exact = True

    condition_truth: dict[str, dict[str, list[int]]] = {}
    condition_estimated: dict[str, dict[str, list[Decimal]]] = {}
    for sample, sample_row in sample_rows.items():
        table = quant_by_sample[sample]
        all_estimates = quant_num_reads(table)
        if set(all_estimates) not in (set(transcript_rows), expected_ids):
            raise ValueError(f"Truth transcript identity mismatch for {sample}")
        estimates = {name: all_estimates[name] for name in transcript_rows}
        metadata = metadata_by_sample[sample]
        expected_fragments = int(sample_row["fragments"])
        fragment_exact &= metadata.num_processed == expected_fragments
        sample_mass = sum(all_estimates.values(), Decimal(0))
        mass_exact &= abs(sample_mass - Decimal(metadata.num_mapped)) <= Decimal("0.001")
        total_mapped += metadata.num_mapped
        total_estimated += sample_mass
        total_transcript_origin += int(sample_row["transcript_origin_fragments"])
        total_decoy_origin += int(sample_row["decoy_origin_fragments"])
        condition = str(sample_row["condition"])
        condition_truth.setdefault(condition, {})
        condition_estimated.setdefault(condition, {})
        counts = sample_row["transcript_counts"]
        for transcript_id, row in transcript_rows.items():
            truth = int(counts[transcript_id])
            estimate = estimates[transcript_id]
            gene = str(row["gene_id"])
            stratum = TruthStratum(row["stratum"])
            key = f"{sample}:{transcript_id}"
            if stratum is TruthStratum.UNIQUE_IDENTIFIABLE and truth > 0:
                unique_truth[key] = truth
                unique_estimated[key] = estimate
            if truth >= 50 and estimate == 0:
                expressed_zero_transitions += 1
            gene_key = f"{sample}:{gene}"
            if stratum is not TruthStratum.PARALOG_GROUP:
                gene_truth[gene_key] = gene_truth.get(gene_key, 0) + truth
                gene_estimated[gene_key] = gene_estimated.get(gene_key, Decimal(0)) + estimate
            if stratum in {TruthStratum.AMBIGUOUS_ISOFORM, TruthStratum.PARALOG_GROUP}:
                group_key = f"{sample}:{row['group_id']}"
                group_truth[group_key] = group_truth.get(group_key, 0) + truth
                group_estimated[group_key] = group_estimated.get(group_key, Decimal(0)) + estimate
            if stratum is TruthStratum.ZERO_EXPRESSION:
                zero_estimated += estimate
            condition_truth[condition].setdefault(gene, []).append(truth)
            condition_estimated[condition].setdefault(gene, []).append(estimate)

    # Remove zero-expression genes from the expressed-gene accuracy vector.
    gene_truth = {name: value for name, value in gene_truth.items() if value > 0}
    gene_estimated = {name: gene_estimated[name] for name in gene_truth}
    group_errors = [
        abs(float(group_estimated[name]) - truth) / truth
        for name, truth in group_truth.items() if truth > 0
    ]
    false_positive_fraction = float(zero_estimated / total_estimated) if total_estimated else 1.0
    high_false_positives = sum(
        estimates[transcript_id] >= 50
        for estimates in (quant_num_reads(table) for table in quant_by_sample.values())
        for transcript_id, row in transcript_rows.items()
        if TruthStratum(row["stratum"]) is TruthStratum.ZERO_EXPRESSION
    )
    excess_mass = max(Decimal(0), total_estimated - Decimal(total_transcript_origin))
    # Two aggregate signals observe the same leakage event: mass on the
    # zero-expression homologs and excess estimated mass above true
    # transcript-origin fragments.  Use their maximum so the event is not
    # double-counted while remaining fail-closed if either signal is larger.
    decoy_leakage = float(max(zero_estimated, excess_mass) / Decimal(total_decoy_origin))

    true_fc: list[float] = []
    estimated_fc: list[float] = []
    all_genes = sorted(set(condition_truth.get("A", {})) & set(condition_truth.get("B", {})))
    for gene in all_genes:
        truth_a = sum(condition_truth["A"][gene]) / 3
        truth_b = sum(condition_truth["B"][gene]) / 3
        if max(truth_a, truth_b) < 100 or truth_a <= 0 or truth_b <= 0:
            continue
        truth_log2 = math.log2(truth_b / truth_a)
        if abs(truth_log2) < 1:
            continue
        estimate_a = sum(condition_estimated["A"][gene], Decimal(0)) / Decimal(3)
        estimate_b = sum(condition_estimated["B"][gene], Decimal(0)) / Decimal(3)
        estimated_log2 = math.log2(max(float(estimate_b), 1e-12) / max(float(estimate_a), 1e-12))
        true_fc.append(truth_log2)
        estimated_fc.append(estimated_log2)
    if not true_fc:
        raise ValueError("Truth fixture has no fold-change gate features")
    directions = sum((a > 0) == (b > 0) for a, b in zip(true_fc, estimated_fc)) / len(true_fc)
    rmse = math.sqrt(statistics.fmean((a - b) ** 2 for a, b in zip(true_fc, estimated_fc)))
    fc_spearman = _correlation(_ranks(true_fc), _ranks(estimated_fc))
    return TruthAccuracyReport(
        fragment_accounting_exact=fragment_exact,
        estimated_mass_accounting_exact=mass_exact,
        expressed_zero_transitions=expressed_zero_transitions,
        unique_transcripts=accuracy_vector(unique_truth, unique_estimated),
        expressed_genes=accuracy_vector(gene_truth, gene_estimated),
        ambiguous_group_max_relative_error=max(group_errors, default=0.0),
        zero_false_positive_mass_fraction=false_positive_fraction,
        high_expression_false_positives=high_false_positives,
        decoy_leakage_fraction=decoy_leakage,
        fold_change_direction_accuracy=directions,
        fold_change_rmse=rmse,
        fold_change_spearman=fc_spearman,
    )


def candidate_nfcore_override(*, image_id: str, status: CandidateStatus) -> str:
    if status is not CandidateStatus.CANDIDATE_QUALIFIED:
        raise ValueError("nf-core integration is forbidden until reproducibility and truth gates pass")
    if not _IMAGE_ID.fullmatch(image_id):
        raise ValueError("Candidate nf-core override requires an exact image identity")
    image = f"{CANDIDATE_LOCAL_IMAGE}@{image_id}"
    return (
        "// Salmon 2.5.1 deterministic qualification candidate; never the default.\n"
        "process {\n"
        f"    withName: '{SALMON_INDEX_PROCESS}' {{\n"
        f"        container = '{image}'\n"
        "    }\n"
        f"    withName: '{FASTQ_SALMON_PROCESS}' {{\n"
        f"        container = '{image}'\n"
        "        cpus = 6\n"
        "        ext.args = '--deterministic --decoder serial'\n"
        "    }\n"
        "}\n"
    )


def validate_candidate_trace(processes: Iterable[str]) -> None:
    names = tuple(processes)
    if BAM_SALMON_PROCESS in names:
        raise ValueError("BAM-based Salmon must remain disabled")
    if names.count(FASTQ_SALMON_PROCESS) != 1:
        raise ValueError("Exactly one FASTQ Salmon process is required per sample")


def scientific_meta_digest(metadata: SalmonMetadataIdentity) -> str:
    payload = asdict(metadata)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def exact_identity(
    *, quant_bytes: bytes, gene_quant_bytes: bytes, quant: QuantTable,
    metadata: SalmonMetadataIdentity, partial_rad_signature: bool = False,
) -> ExactRunIdentity:
    return ExactRunIdentity(
        quant_sf_sha256=hashlib.sha256(quant_bytes).hexdigest(),
        gene_quant_sha256=hashlib.sha256(gene_quant_bytes).hexdigest(),
        canonical_numerical_digest=canonical_numerical_digest(quant),
        scientific_meta_sha256=scientific_meta_digest(metadata),
        num_processed=metadata.num_processed,
        num_mapped=metadata.num_mapped,
        partial_rad_signature=partial_rad_signature,
    )
