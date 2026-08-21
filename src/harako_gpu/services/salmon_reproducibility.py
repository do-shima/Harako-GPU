"""Scientific identity and bounded comparison for pinned Salmon quantification."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Collection, Iterable, Mapping, Sequence


TOLERANCE_SCHEMA_VERSION = 1
EFFECTIVE_LENGTH_MAX_ABSOLUTE = Decimal("0.1")
TPM_HIGH_MINIMUM = Decimal("1")
TPM_HIGH_MAX_RELATIVE = Decimal("0.001")
TPM_MIDDLE_MINIMUM = Decimal("0.1")
TPM_MIDDLE_MAX_ABSOLUTE = Decimal("0.001")
TPM_SPEARMAN_MINIMUM = 0.999999
COUNT_ESTIMATE_SERIALIZATION_QUANTUM = Decimal("0.001")
SALMON_IMAGE = "quay.io/biocontainers/salmon:1.10.3--h6dccd9a_2"
SALMON_IMAGE_DIGEST = "sha256:f83ebb158845ee8138d793347f83b92c75e83c58dd8f4600c6fea2a2453ef08e"
SALMON_VERSION = "1.10.3"
SALMON_ALLOWED_THREADS = frozenset({1, 2, 4, 6, 8})
_QUANT_HEADER = ("Name", "Length", "EffectiveLength", "TPM", "NumReads")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_GTF_ATTRIBUTE = re.compile(r'(gene_id|transcript_id)\s+"([^"]+)"')


class TpmStratum(str, Enum):
    ZERO = "TPM_EQ_0"
    LOW = "TPM_GT_0_LT_0_1"
    MIDDLE = "TPM_GE_0_1_LT_1"
    HIGH = "TPM_GE_1"


class ReproducibilityClass(str, Enum):
    EXACT = "EXACT_REPRODUCIBILITY"
    BOUNDED_NUMERICAL = "BOUNDED_NUMERICAL_REPRODUCIBILITY"
    MATERIAL_VARIABILITY = "MATERIAL_VARIABILITY"


@dataclass(frozen=True)
class QuantRow:
    transcript_id: str
    length: int
    effective_length: Decimal
    tpm: Decimal
    num_reads: Decimal


@dataclass(frozen=True)
class QuantTable:
    rows: tuple[QuantRow, ...]

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(row.transcript_id for row in self.rows)

    def by_id(self) -> dict[str, QuantRow]:
        return {row.transcript_id: row for row in self.rows}


@dataclass(frozen=True)
class ExpressionRow:
    feature_id: str
    tpm: Decimal
    num_reads: Decimal


@dataclass(frozen=True)
class ExpressionTable:
    rows: tuple[ExpressionRow, ...]

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(row.feature_id for row in self.rows)

    def by_id(self) -> dict[str, ExpressionRow]:
        return {row.feature_id: row for row in self.rows}


@dataclass(frozen=True)
class StratumComparison:
    count: int
    max_absolute_difference: Decimal
    max_relative_difference: Decimal | None


@dataclass(frozen=True)
class QuantComparison:
    id_set_equal: bool
    row_order_equal: bool
    missing_ids: tuple[str, ...]
    unexpected_ids: tuple[str, ...]
    length_exact: bool
    total_num_reads_exact: bool
    num_reads_max_absolute_difference: Decimal
    effective_length_max_absolute_difference: Decimal
    effective_length_median_absolute_difference: float
    effective_length_p95_absolute_difference: float
    tpm_max_absolute_difference: Decimal
    tpm_max_relative_difference: Decimal
    tpm_median_relative_difference: float
    tpm_p95_relative_difference: float
    tpm_pearson: float
    tpm_spearman: float
    zero_nonzero_transition_ids: tuple[str, ...]
    strata: Mapping[TpmStratum, StratumComparison]


@dataclass(frozen=True)
class ExpressionComparison:
    id_set_equal: bool
    row_order_equal: bool
    num_reads_max_absolute_difference: Decimal
    tpm_max_absolute_difference: Decimal
    tpm_max_relative_difference: Decimal
    tpm_pearson: float
    tpm_spearman: float
    zero_nonzero_transition_ids: tuple[str, ...]
    strata: Mapping[TpmStratum, StratumComparison]


@dataclass(frozen=True)
class SalmonMetadataIdentity:
    salmon_version: str
    mapping_type: str
    library_types: tuple[str, ...]
    num_processed: int
    num_mapped: int
    num_valid_targets: int
    seq_bias_correct: bool
    gc_bias_correct: bool


@dataclass(frozen=True)
class DeterministicCapability:
    deterministic_option: str | None
    seed_options: tuple[str, ...]
    alignment_mode_help: bool


@dataclass(frozen=True)
class BamScientificIdentity:
    byte_sha256: str
    header_normalized_sha256: str
    record_multiset_sha256: str
    record_order_sha256: str
    record_count: int


@dataclass(frozen=True)
class BamIdentityComparison:
    byte_identical: bool
    header_identical: bool
    record_multiset_identical: bool
    record_order_identical: bool
    record_count_identical: bool


@dataclass(frozen=True)
class SalmonQuantificationIdentity:
    schema_version: int
    salmon_version: str
    image_digest: str
    command_argv: tuple[str, ...]
    thread_count: int
    input_bam_scientific_checksum: str
    transcript_fasta_sha256: str
    quant_sf_sha256: str
    canonical_numerical_digest: str
    reproducibility_class: ReproducibilityClass
    tolerance_schema_version: int


@dataclass(frozen=True)
class SamRecordInventory:
    record_count: int
    unique_qname_count: int
    qname_group_count: int
    record_multiset_sha256: str
    record_order_sha256: str
    qname_groups_contiguous: bool
    split_qname_count: int
    tag_counts: Mapping[str, int]


def _decimal(raw: str, field: str, line: int) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid {field} at quant.sf line {line}") from exc
    if not value.is_finite() or value < 0:
        raise ValueError(f"Invalid {field} at quant.sf line {line}")
    return value


def parse_quant_sf(text: str, *, expected_ids: Collection[str] | None = None) -> QuantTable:
    """Parse Salmon quant.sf strictly and preserve its feature order."""

    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    if tuple(reader.fieldnames or ()) != _QUANT_HEADER:
        raise ValueError("quant.sf header must be Name, Length, EffectiveLength, TPM, NumReads")
    rows: list[QuantRow] = []
    seen: set[str] = set()
    for line, raw in enumerate(reader, start=2):
        transcript_id = (raw["Name"] or "").strip()
        if not transcript_id:
            raise ValueError(f"Missing transcript ID at quant.sf line {line}")
        if transcript_id in seen:
            raise ValueError(f"Duplicate transcript ID: {transcript_id}")
        seen.add(transcript_id)
        try:
            length = int(raw["Length"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid Length at quant.sf line {line}") from exc
        if length <= 0:
            raise ValueError(f"Invalid Length at quant.sf line {line}")
        rows.append(
            QuantRow(
                transcript_id,
                length,
                _decimal(raw["EffectiveLength"], "EffectiveLength", line),
                _decimal(raw["TPM"], "TPM", line),
                _decimal(raw["NumReads"], "NumReads", line),
            )
        )
    if not rows:
        raise ValueError("quant.sf has no transcript rows")
    if expected_ids is not None:
        expected = set(expected_ids)
        missing = sorted(expected - seen)
        unexpected = sorted(seen - expected)
        if missing or unexpected:
            raise ValueError(
                "quant.sf feature identity mismatch; "
                f"missing={missing or []}, unexpected={unexpected or []}"
            )
    return QuantTable(tuple(rows))


def parse_salmon_metadata(text: str) -> SalmonMetadataIdentity:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Malformed Salmon meta_info.json") from exc
    required = {
        "salmon_version",
        "mapping_type",
        "library_types",
        "num_processed",
        "num_mapped",
        "num_valid_targets",
        "seq_bias_correct",
        "gc_bias_correct",
    }
    missing = sorted(required - set(data))
    if missing:
        raise ValueError("Salmon metadata is missing fields: " + ", ".join(missing))
    library_types = data["library_types"]
    if not isinstance(library_types, list) or not all(isinstance(item, str) for item in library_types):
        raise ValueError("Salmon library_types must be a string array")
    identity = SalmonMetadataIdentity(
        salmon_version=str(data["salmon_version"]),
        mapping_type=str(data["mapping_type"]),
        library_types=tuple(library_types),
        num_processed=int(data["num_processed"]),
        num_mapped=int(data["num_mapped"]),
        num_valid_targets=int(data["num_valid_targets"]),
        seq_bias_correct=bool(data["seq_bias_correct"]),
        gc_bias_correct=bool(data["gc_bias_correct"]),
    )
    if identity.num_processed < 0 or identity.num_mapped < 0:
        raise ValueError("Salmon fragment counts cannot be negative")
    if identity.num_mapped > identity.num_processed:
        raise ValueError("Salmon mapped fragments exceed processed fragments")
    return identity


def tpm_stratum(value: Decimal) -> TpmStratum:
    if value == 0:
        return TpmStratum.ZERO
    if value < TPM_MIDDLE_MINIMUM:
        return TpmStratum.LOW
    if value < TPM_HIGH_MINIMUM:
        return TpmStratum.MIDDLE
    return TpmStratum.HIGH


def _relative(base: Decimal, candidate: Decimal) -> Decimal:
    difference = abs(candidate - base)
    return difference / abs(base) if base != 0 else Decimal(0 if candidate == 0 else "Infinity")


def _percentile(values: Sequence[Decimal], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _pearson(left: Sequence[Decimal], right: Sequence[Decimal]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Correlation requires equal non-empty vectors")
    x = [float(value) for value in left]
    y = [float(value) for value in right]
    mean_x = statistics.fmean(x)
    mean_y = statistics.fmean(y)
    numerator = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y))
    denominator = math.sqrt(
        sum((a - mean_x) ** 2 for a in x) * sum((b - mean_y) ** 2 for b in y)
    )
    if denominator == 0:
        return 1.0 if x == y else 0.0
    return numerator / denominator


def _ranks(values: Sequence[Decimal]) -> list[Decimal]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [Decimal(0)] * len(values)
    cursor = 0
    while cursor < len(indexed):
        end = cursor + 1
        while end < len(indexed) and indexed[end][1] == indexed[cursor][1]:
            end += 1
        rank = Decimal(cursor + 1 + end) / Decimal(2)
        for original_index, _ in indexed[cursor:end]:
            ranks[original_index] = rank
        cursor = end
    return ranks


def _strata(
    baseline: Sequence[tuple[str, Decimal, Decimal]],
) -> dict[TpmStratum, StratumComparison]:
    result: dict[TpmStratum, StratumComparison] = {}
    for stratum in TpmStratum:
        pairs = [(left, right) for _, left, right in baseline if tpm_stratum(left) is stratum]
        absolute = [abs(right - left) for left, right in pairs]
        relative = [_relative(left, right) for left, right in pairs if left != 0]
        result[stratum] = StratumComparison(
            count=len(pairs),
            max_absolute_difference=max(absolute, default=Decimal(0)),
            max_relative_difference=max(relative) if relative else None,
        )
    return result


def compare_quant_tables(baseline: QuantTable, candidate: QuantTable) -> QuantComparison:
    left = baseline.by_id()
    right = candidate.by_id()
    shared = sorted(left.keys() & right.keys())
    effective_differences = [
        abs(right[name].effective_length - left[name].effective_length) for name in shared
    ]
    tpm_pairs = [(name, left[name].tpm, right[name].tpm) for name in shared]
    tpm_differences = [abs(candidate_tpm - baseline_tpm) for _, baseline_tpm, candidate_tpm in tpm_pairs]
    relative = [_relative(baseline_tpm, candidate_tpm) for _, baseline_tpm, candidate_tpm in tpm_pairs if baseline_tpm != 0]
    num_reads_differences = [abs(right[name].num_reads - left[name].num_reads) for name in shared]
    transitions = tuple(
        name for name, baseline_tpm, candidate_tpm in tpm_pairs
        if (baseline_tpm == 0) != (candidate_tpm == 0)
    )
    return QuantComparison(
        id_set_equal=set(left) == set(right),
        row_order_equal=baseline.ids == candidate.ids,
        missing_ids=tuple(sorted(set(left) - set(right))),
        unexpected_ids=tuple(sorted(set(right) - set(left))),
        length_exact=all(left[name].length == right[name].length for name in shared),
        total_num_reads_exact=sum((row.num_reads for row in baseline.rows), Decimal(0))
        == sum((row.num_reads for row in candidate.rows), Decimal(0)),
        num_reads_max_absolute_difference=max(num_reads_differences, default=Decimal(0)),
        effective_length_max_absolute_difference=max(effective_differences, default=Decimal(0)),
        effective_length_median_absolute_difference=(
            float(statistics.median(effective_differences)) if effective_differences else 0.0
        ),
        effective_length_p95_absolute_difference=_percentile(effective_differences, 0.95),
        tpm_max_absolute_difference=max(tpm_differences, default=Decimal(0)),
        tpm_max_relative_difference=max(relative, default=Decimal(0)),
        tpm_median_relative_difference=float(statistics.median(relative)) if relative else 0.0,
        tpm_p95_relative_difference=_percentile(relative, 0.95),
        tpm_pearson=_pearson(
            [left[name].tpm for name in shared], [right[name].tpm for name in shared]
        ) if shared else 0.0,
        tpm_spearman=_pearson(
            _ranks([left[name].tpm for name in shared]),
            _ranks([right[name].tpm for name in shared]),
        ) if shared else 0.0,
        zero_nonzero_transition_ids=transitions,
        strata=_strata(tpm_pairs),
    )


def parse_transcript_gene_map(gtf_text: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line_number, line in enumerate(gtf_text.splitlines(), start=1):
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 9:
            raise ValueError(f"Malformed GTF line {line_number}")
        attributes = dict(_GTF_ATTRIBUTE.findall(fields[8]))
        transcript_id = attributes.get("transcript_id")
        gene_id = attributes.get("gene_id")
        if transcript_id is None:
            continue
        if gene_id is None:
            raise ValueError(f"Transcript has no gene_id at GTF line {line_number}")
        previous = mapping.setdefault(transcript_id, gene_id)
        if previous != gene_id:
            raise ValueError(f"Transcript maps to multiple genes: {transcript_id}")
    if not mapping:
        raise ValueError("GTF contains no transcript-to-gene mapping")
    return mapping


def aggregate_by_gene(table: QuantTable, transcript_to_gene: Mapping[str, str]) -> ExpressionTable:
    missing = sorted(set(table.ids) - set(transcript_to_gene))
    if missing:
        raise ValueError("Missing transcript-to-gene mappings: " + ", ".join(missing))
    order: list[str] = []
    totals: dict[str, tuple[Decimal, Decimal]] = {}
    for row in table.rows:
        gene = transcript_to_gene[row.transcript_id]
        if gene not in totals:
            order.append(gene)
            totals[gene] = (Decimal(0), Decimal(0))
        tpm, num_reads = totals[gene]
        totals[gene] = (tpm + row.tpm, num_reads + row.num_reads)
    return ExpressionTable(
        tuple(ExpressionRow(gene, totals[gene][0], totals[gene][1]) for gene in order)
    )


def compare_expression_tables(
    baseline: ExpressionTable,
    candidate: ExpressionTable,
) -> ExpressionComparison:
    left = baseline.by_id()
    right = candidate.by_id()
    shared = sorted(left.keys() & right.keys())
    pairs = [(name, left[name].tpm, right[name].tpm) for name in shared]
    num_reads_differences = [abs(right[name].num_reads - left[name].num_reads) for name in shared]
    tpm_differences = [abs(candidate_tpm - baseline_tpm) for _, baseline_tpm, candidate_tpm in pairs]
    relative = [_relative(baseline_tpm, candidate_tpm) for _, baseline_tpm, candidate_tpm in pairs if baseline_tpm != 0]
    transitions = tuple(
        name for name, baseline_tpm, candidate_tpm in pairs
        if (baseline_tpm == 0) != (candidate_tpm == 0)
    )
    return ExpressionComparison(
        id_set_equal=set(left) == set(right),
        row_order_equal=baseline.ids == candidate.ids,
        num_reads_max_absolute_difference=max(num_reads_differences, default=Decimal(0)),
        tpm_max_absolute_difference=max(tpm_differences, default=Decimal(0)),
        tpm_max_relative_difference=max(relative, default=Decimal(0)),
        tpm_pearson=_pearson(
            [left[name].tpm for name in shared], [right[name].tpm for name in shared]
        ) if shared else 0.0,
        tpm_spearman=_pearson(
            _ranks([left[name].tpm for name in shared]),
            _ranks([right[name].tpm for name in shared]),
        ) if shared else 0.0,
        zero_nonzero_transition_ids=transitions,
        strata=_strata(pairs),
    )


def _canonical_decimal(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def canonical_numerical_digest(table: QuantTable) -> str:
    payload = [
        [
            row.transcript_id,
            row.length,
            _canonical_decimal(row.effective_length),
            _canonical_decimal(row.tpm),
            _canonical_decimal(row.num_reads),
        ]
        for row in table.rows
    ]
    serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def normalize_sam_header(text: str) -> str:
    """Remove path/timestamp command text while retaining scientific header fields."""

    normalized: list[str] = []
    for line in text.splitlines():
        if not line:
            continue
        fields = line.split("\t")
        if fields[0] == "@CO":
            continue
        if fields[0] == "@PG":
            fields = [field for field in fields if not field.startswith("CL:")]
        normalized.append("\t".join(fields))
    return "\n".join(normalized) + ("\n" if normalized else "")


def header_normalized_sha256(text: str) -> str:
    return hashlib.sha256(normalize_sam_header(text).encode("utf-8")).hexdigest()


def inspect_sam_records(lines: Iterable[str]) -> SamRecordInventory:
    order_hasher = hashlib.sha256()
    normalized_records: list[str] = []
    tag_counts: Counter[str] = Counter()
    closed_qnames: set[str] = set()
    split_qnames: set[str] = set()
    qnames: set[str] = set()
    qname_groups = 0
    previous_qname: str | None = None
    count = 0
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip("\r\n")
        if not line or line.startswith("@"):
            continue
        fields = line.split("\t")
        if len(fields) < 11:
            raise ValueError(f"Malformed SAM record at line {line_number}")
        qname = fields[0]
        qnames.add(qname)
        if qname != previous_qname:
            qname_groups += 1
        if previous_qname is not None and qname != previous_qname:
            closed_qnames.add(previous_qname)
        if qname in closed_qnames and qname != previous_qname:
            split_qnames.add(qname)
        previous_qname = qname
        tags = sorted(fields[11:])
        for tag in tags:
            if len(tag) >= 3 and tag[2] == ":":
                tag_counts[tag[:2]] += 1
        normalized = "\t".join([*fields[:11], *tags])
        normalized_records.append(normalized)
        order_hasher.update(normalized.encode("utf-8") + b"\n")
        count += 1
    if count == 0:
        raise ValueError("SAM input has no alignment records")
    multiset_hasher = hashlib.sha256()
    for record in sorted(normalized_records):
        multiset_hasher.update(record.encode("utf-8") + b"\n")
    return SamRecordInventory(
        record_count=count,
        unique_qname_count=len(qnames),
        qname_group_count=qname_groups,
        record_multiset_sha256=multiset_hasher.hexdigest(),
        record_order_sha256=order_hasher.hexdigest(),
        qname_groups_contiguous=not split_qnames,
        split_qname_count=len(split_qnames),
        tag_counts=dict(sorted(tag_counts.items())),
    )


def compare_bam_identities(
    baseline: BamScientificIdentity,
    candidate: BamScientificIdentity,
) -> BamIdentityComparison:
    return BamIdentityComparison(
        byte_identical=baseline.byte_sha256 == candidate.byte_sha256,
        header_identical=baseline.header_normalized_sha256 == candidate.header_normalized_sha256,
        record_multiset_identical=baseline.record_multiset_sha256 == candidate.record_multiset_sha256,
        record_order_identical=baseline.record_order_sha256 == candidate.record_order_sha256,
        record_count_identical=baseline.record_count == candidate.record_count,
    )


def bam_scientific_checksum(identity: BamScientificIdentity) -> str:
    """Hash the BAM properties that affect alignment-mode quantification."""

    validate_bam_identity(identity)
    payload = {
        "header_normalized_sha256": identity.header_normalized_sha256,
        "record_count": identity.record_count,
        "record_multiset_sha256": identity.record_multiset_sha256,
        "record_order_sha256": identity.record_order_sha256,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def salmon_quant_argv(
    *,
    alignments: str,
    transcript_fasta: str,
    gene_map: str,
    output: str,
    threads: int,
) -> tuple[str, ...]:
    if threads not in SALMON_ALLOWED_THREADS:
        raise ValueError(f"Unsupported qualification thread count: {threads}")
    paths = {
        "alignments": alignments,
        "transcript_fasta": transcript_fasta,
        "gene_map": gene_map,
        "output": output,
    }
    if any(not value or "\x00" in value for value in paths.values()):
        raise ValueError("Salmon paths must be non-empty and contain no NUL")
    return (
        "salmon",
        "quant",
        "--geneMap",
        gene_map,
        "--threads",
        str(threads),
        "--libType=ISR",
        "-t",
        transcript_fasta,
        "-a",
        alignments,
        "-o",
        output,
    )


def detect_deterministic_capability(help_text: str) -> DeterministicCapability:
    options = set(re.findall(r"(?<![\w-])--[A-Za-z][A-Za-z0-9-]*", help_text))
    deterministic = "--deterministic" if "--deterministic" in options else None
    seed_options = tuple(sorted(option for option in options if "seed" in option.lower()))
    return DeterministicCapability(
        deterministic_option=deterministic,
        seed_options=seed_options,
        alignment_mode_help="alignment" in help_text.lower(),
    )


def build_quantification_identity(
    *,
    bam_identity: BamScientificIdentity,
    transcript_fasta_sha256: str,
    quant_sf_bytes: bytes,
    quant_table: QuantTable,
    alignments: str,
    transcript_fasta: str,
    gene_map: str,
    output: str,
    threads: int,
    reproducibility_class: ReproducibilityClass,
) -> SalmonQuantificationIdentity:
    _validate_sha256(transcript_fasta_sha256, "transcript_fasta_sha256")
    argv = salmon_quant_argv(
        alignments=alignments,
        transcript_fasta=transcript_fasta,
        gene_map=gene_map,
        output=output,
        threads=threads,
    )
    return SalmonQuantificationIdentity(
        schema_version=1,
        salmon_version=SALMON_VERSION,
        image_digest=SALMON_IMAGE_DIGEST,
        command_argv=argv,
        thread_count=threads,
        input_bam_scientific_checksum=bam_scientific_checksum(bam_identity),
        transcript_fasta_sha256=transcript_fasta_sha256,
        quant_sf_sha256=hashlib.sha256(quant_sf_bytes).hexdigest(),
        canonical_numerical_digest=canonical_numerical_digest(quant_table),
        reproducibility_class=reproducibility_class,
        tolerance_schema_version=TOLERANCE_SCHEMA_VERSION,
    )


def _validate_sha256(value: str, field: str) -> None:
    if not _HEX_64.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")


def validate_bam_identity(identity: BamScientificIdentity) -> None:
    for field in (
        "byte_sha256",
        "header_normalized_sha256",
        "record_multiset_sha256",
        "record_order_sha256",
    ):
        _validate_sha256(getattr(identity, field), field)
    if identity.record_count < 0:
        raise ValueError("record_count cannot be negative")


def classify_reproducibility(
    *,
    quant_byte_identical: bool,
    transcript: QuantComparison,
    gene: ExpressionComparison,
    metadata_exact: bool,
) -> ReproducibilityClass:
    exact_identity = (
        quant_byte_identical
        and metadata_exact
        and transcript.id_set_equal
        and transcript.row_order_equal
        and transcript.length_exact
        and transcript.total_num_reads_exact
        and transcript.num_reads_max_absolute_difference == 0
        and transcript.effective_length_max_absolute_difference == 0
        and transcript.tpm_max_absolute_difference == 0
        and not transcript.zero_nonzero_transition_ids
        and gene.num_reads_max_absolute_difference == 0
        and gene.tpm_max_absolute_difference == 0
    )
    if exact_identity:
        return ReproducibilityClass.EXACT
    middle = transcript.strata[TpmStratum.MIDDLE]
    high = transcript.strata[TpmStratum.HIGH]
    gene_high = gene.strata[TpmStratum.HIGH]
    bounded = (
        metadata_exact
        and transcript.id_set_equal
        and transcript.row_order_equal
        and transcript.length_exact
        and transcript.total_num_reads_exact
        and transcript.num_reads_max_absolute_difference <= COUNT_ESTIMATE_SERIALIZATION_QUANTUM
        and transcript.effective_length_max_absolute_difference <= EFFECTIVE_LENGTH_MAX_ABSOLUTE
        and (middle.count == 0 or middle.max_absolute_difference <= TPM_MIDDLE_MAX_ABSOLUTE)
        and (
            high.count == 0
            or (
                high.max_relative_difference is not None
                and high.max_relative_difference <= TPM_HIGH_MAX_RELATIVE
            )
        )
        and (
            gene_high.count == 0
            or (
                gene_high.max_relative_difference is not None
                and gene_high.max_relative_difference <= TPM_HIGH_MAX_RELATIVE
            )
        )
        and transcript.tpm_spearman >= TPM_SPEARMAN_MINIMUM
        and gene.tpm_spearman >= TPM_SPEARMAN_MINIMUM
        and not transcript.zero_nonzero_transition_ids
        and not gene.zero_nonzero_transition_ids
        and gene.num_reads_max_absolute_difference <= COUNT_ESTIMATE_SERIALIZATION_QUANTUM
    )
    return (
        ReproducibilityClass.BOUNDED_NUMERICAL
        if bounded
        else ReproducibilityClass.MATERIAL_VARIABILITY
    )
