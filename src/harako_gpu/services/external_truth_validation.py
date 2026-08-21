"""Pure contracts and metrics for public SIRV/ERCC qualification data."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import statistics
from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import Enum
from typing import Iterable, Mapping, Sequence


SIRV_ACCESSION = "SRR3497201"
SIRV_BATCH = "216652830"
SIRV_MIX = "E0"
SIRV_TRANSCRIPT_COUNT = 69
SIRV_GENE_COUNT = 7
V1_PREREGISTRATION_SHA256 = "5ba814f25ce1bb1ab872a3649761f87bcb593af7797458b378933d8015c22077"
ERCC_PROJECT = "PRJNA208369"
ERCC_GEO_SERIES = "GSE47792"
ERCC_DATA_SERIES = "GSE47774"
ALLOWED_DOWNLOAD_HOSTS = frozenset({
    "ftp.sra.ebi.ac.uk",
    "ftp.ncbi.nlm.nih.gov",
    "www.ebi.ac.uk",
    "www.lexogen.com",
    "assets.thermofisher.com",
})


class ExternalArm(str, Enum):
    SIRV = "SIRV"
    ERCC = "ERCC"


class GateState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNDEFINED_ZERO_VARIANCE = "UNDEFINED_ZERO_VARIANCE"
    NOT_APPLICABLE_ZERO_VARIANCE = "NOT_APPLICABLE_ZERO_VARIANCE"


class ExternalIndexRole(str, Enum):
    SIRV_COMBINED_PRIMARY = "combined_human_sirv_decoy_aware"
    SIRV_ONLY_DIAGNOSTIC = "sirv_only"
    ERCC_PRIMARY = "ercc_92"


@dataclass(frozen=True)
class ExternalIndexIdentity:
    role: ExternalIndexRole
    salmon_version: str
    kmer: int
    target_count: int
    source_sha256: str
    inventory_sha256: str
    human_release: str | None = None
    decoy_aware: bool = False

    def validate(self) -> None:
        digests = (self.source_sha256, self.inventory_sha256)
        if self.salmon_version != "2.5.1" or self.kmer != 31:
            raise ValueError("External index must be a Salmon 2.5.1 k=31 identity")
        if any(len(value) != 64 or any(c not in "0123456789abcdef" for c in value) for value in digests):
            raise ValueError("External index checksums must be lowercase SHA-256")
        if self.role is ExternalIndexRole.SIRV_COMBINED_PRIMARY:
            if not self.human_release or not self.decoy_aware or self.target_count <= SIRV_TRANSCRIPT_COUNT:
                raise ValueError("Primary SIRV index must combine fixed human targets, 69 SIRVs, and decoys")
        elif self.role is ExternalIndexRole.SIRV_ONLY_DIAGNOSTIC:
            if self.human_release is not None or self.decoy_aware or self.target_count != SIRV_TRANSCRIPT_COUNT:
                raise ValueError("SIRV-only index is diagnostic and must contain exactly 69 targets")
        elif self.target_count != 92 or self.human_release is not None or self.decoy_aware:
            raise ValueError("ERCC index must contain exactly the official 92 targets")

    @property
    def primary_truth_eligible(self) -> bool:
        return self.role is not ExternalIndexRole.SIRV_ONLY_DIAGNOSTIC


@dataclass(frozen=True)
class ExternalRunCandidate:
    run_accession: str
    sample: str
    mix: str
    site: str
    platform: str
    library_id: str
    lane: str
    flowcell: str
    layout: str
    read_length: int

    def validate(self) -> None:
        if not self.run_accession.startswith("SRR"):
            raise ValueError("External run must use an SRR accession")
        if self.layout != "PAIRED" or self.read_length <= 0:
            raise ValueError("External validation requires paired reads with known length")
        if self.mix not in {"Mix1", "Mix2"}:
            raise ValueError("ERCC candidate must identify Mix1 or Mix2")


def select_ercc_runs(
    candidates: Iterable[ExternalRunCandidate], *, lanes_per_mix: int = 2,
) -> tuple[ExternalRunCandidate, ...]:
    """Select the lexicographically first matched BGI pair before results exist."""

    values = tuple(candidates)
    if lanes_per_mix < 2:
        raise ValueError("At least two technical lanes per ERCC mix are required")
    for value in values:
        value.validate()
    eligible = tuple(
        value for value in values
        if value.site == "BGI" and value.platform == "Illumina HiSeq 2000"
        and value.layout == "PAIRED"
    )
    keys1 = {
        (v.library_id, v.flowcell, v.read_length) for v in eligible if v.mix == "Mix1"
    }
    keys2 = {
        (v.library_id, v.flowcell, v.read_length) for v in eligible if v.mix == "Mix2"
    }
    for key in sorted(keys1 & keys2):
        chosen: list[ExternalRunCandidate] = []
        for mix in ("Mix1", "Mix2"):
            group = sorted(
                (v for v in eligible if v.mix == mix and (v.library_id, v.flowcell, v.read_length) == key),
                key=lambda v: v.run_accession,
            )
            if len(group) < lanes_per_mix:
                break
            chosen.extend(group[:lanes_per_mix])
        if len(chosen) == lanes_per_mix * 2:
            return tuple(chosen)
    raise ValueError("No same-library, same-flowcell matched ERCC lane set")


@dataclass(frozen=True)
class ErccTruthRow:
    ercc_id: str
    subgroup: str
    mix1: Decimal
    mix2: Decimal
    expected_ratio: Decimal
    expected_log2_ratio: Decimal


def parse_ercc_truth(text: str) -> tuple[ErccTruthRow, ...]:
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    expected = {
        "ERCC ID", "subgroup", "concentration in Mix 1 (attomoles/ul)",
        "concentration in Mix 2 (attomoles/ul)", "expected fold-change ratio",
        "log2(Mix 1/Mix 2)",
    }
    if reader.fieldnames is None or not expected.issubset(reader.fieldnames):
        raise ValueError("Unrecognized official ERCC truth-table schema")
    rows = tuple(
        ErccTruthRow(
            row["ERCC ID"], row["subgroup"],
            Decimal(row["concentration in Mix 1 (attomoles/ul)"]),
            Decimal(row["concentration in Mix 2 (attomoles/ul)"]),
            Decimal(row["expected fold-change ratio"]),
            Decimal(row["log2(Mix 1/Mix 2)"]),
        )
        for row in reader
    )
    if len(rows) != 92 or len({row.ercc_id for row in rows}) != 92:
        raise ValueError("Official ERCC truth must contain exactly 92 unique IDs")
    expected_ratios = {Decimal("4"), Decimal("1"), Decimal("0.67"), Decimal("0.5")}
    if {row.expected_ratio for row in rows} != expected_ratios:
        raise ValueError("ERCC ratio groups do not match the official four-group design")
    if any(row.mix1 <= 0 or row.mix2 <= 0 for row in rows):
        raise ValueError("ERCC truth concentrations must be positive")
    return rows


def validate_secondary_ercc_truth(
    official: Sequence[ErccTruthRow], secondary: Sequence[ErccTruthRow],
) -> None:
    if tuple(official) != tuple(secondary):
        raise ValueError("Secondary ERCC table is not an exact 92-row official-table match")


def upper_fraction_ids(values: Mapping[str, Decimal], fraction: Decimal) -> tuple[str, ...]:
    if not Decimal(0) < fraction <= Decimal(1) or not values:
        raise ValueError("Concentration subset fraction must be in (0, 1]")
    ordered = sorted(values, key=lambda name: (-values[name], name))
    count = math.ceil(len(ordered) * float(fraction))
    return tuple(ordered[:count])


def _ranks(values: Sequence[float]) -> tuple[float, ...]:
    order = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and order[end][1] == order[cursor][1]:
            end += 1
        rank = (cursor + 1 + end) / 2
        for original, _ in order[cursor:end]:
            ranks[original] = rank
        cursor = end
    return tuple(ranks)


def correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("Correlation requires equal vectors with at least two values")
    left_mean, right_mean = statistics.fmean(left), statistics.fmean(right)
    left_ss = sum((value - left_mean) ** 2 for value in left)
    right_ss = sum((value - right_mean) ** 2 for value in right)
    if left_ss == 0 or right_ss == 0:
        return None
    return sum(
        (a - left_mean) * (b - right_mean) for a, b in zip(left, right)
    ) / math.sqrt(left_ss * right_ss)


def spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    return correlation(_ranks(left), _ranks(right))


def percentile(values: Sequence[float], probability: float) -> float:
    if not values or not 0 <= probability <= 1:
        raise ValueError("Percentile requires values and a probability in [0, 1]")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def validate_v1_preregistration(content: bytes) -> None:
    if hashlib.sha256(content).hexdigest() != V1_PREREGISTRATION_SHA256:
        raise ValueError("Historical external-truth preregistration v1 was modified")


def sirv_expected_fractions(
    transcript_to_gene: Mapping[str, str],
) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    if len(transcript_to_gene) != SIRV_TRANSCRIPT_COUNT:
        raise ValueError("SIRV E0 truth requires exactly 69 unique transcripts")
    if len(set(transcript_to_gene.values())) != SIRV_GENE_COUNT:
        raise ValueError("SIRV E0 truth requires exactly seven genes")
    unit = Decimal(1) / Decimal(SIRV_TRANSCRIPT_COUNT)
    transcripts = {name: unit for name in sorted(transcript_to_gene)}
    gene_counts: dict[str, int] = {}
    for gene in transcript_to_gene.values():
        gene_counts[gene] = gene_counts.get(gene, 0) + 1
    genes = {gene: Decimal(count) / Decimal(SIRV_TRANSCRIPT_COUNT) for gene, count in gene_counts.items()}
    return transcripts, dict(sorted(genes.items()))


def normalized_mole_fractions(
    feature_ids: Sequence[str], observed_tpm: Mapping[str, Decimal],
) -> dict[str, Decimal]:
    if len(set(feature_ids)) != len(feature_ids) or set(feature_ids) - set(observed_tpm):
        raise ValueError("Mole-fraction features must be unique and present in observed TPM")
    values = {name: observed_tpm[name] for name in feature_ids}
    if any(value < 0 or not value.is_finite() for value in values.values()):
        raise ValueError("Observed TPM must be finite and nonnegative")
    total = sum(values.values(), Decimal(0))
    if total <= 0:
        return {name: Decimal(0) for name in feature_ids}
    return {name: values[name] / total for name in feature_ids}


@dataclass(frozen=True)
class EquimolarMetrics:
    evaluated_features: int
    detected_features: int
    detection_rate: float
    median_absolute_log2_error: float
    p90_absolute_log2_error: float
    correlation_state: GateState = GateState.NOT_APPLICABLE_ZERO_VARIANCE

    def transcript_passed(self) -> bool:
        return (
            self.detection_rate >= 0.90
            and self.median_absolute_log2_error <= 0.75
            and self.p90_absolute_log2_error <= 1.50
        )

    def gene_passed(self) -> bool:
        return (
            self.detection_rate == 1.0
            and self.evaluated_features == SIRV_GENE_COUNT
            and self.median_absolute_log2_error <= 0.50
            and self.p90_absolute_log2_error <= 1.00
        )


def equimolar_metrics(
    expected_fractions: Mapping[str, Decimal],
    estimated_fractions: Mapping[str, Decimal],
    *,
    evaluated_ids: Sequence[str] | None = None,
) -> EquimolarMetrics:
    names = tuple(evaluated_ids) if evaluated_ids is not None else tuple(sorted(expected_fractions))
    if not names or len(set(names)) != len(names):
        raise ValueError("Equimolar evaluation requires a nonempty unique feature subset")
    if set(names) - (set(expected_fractions) & set(estimated_fractions)):
        raise ValueError("Equimolar feature identity mismatch")
    errors: list[float] = []
    detected = 0
    for name in names:
        expected, estimated = expected_fractions[name], estimated_fractions[name]
        if expected <= 0 or not expected.is_finite() or estimated < 0 or not estimated.is_finite():
            raise ValueError("Equimolar fractions must be finite with positive truth")
        if estimated == 0:
            errors.append(math.inf)
        else:
            detected += 1
            errors.append(abs(math.log2(float(estimated / expected))))
    return EquimolarMetrics(
        len(names), detected, detected / len(names), statistics.median(errors),
        percentile(errors, 0.90),
    )


@dataclass(frozen=True)
class AggregateRelativeErrorMetrics:
    groups: int
    median_relative_error: float
    p90_relative_error: float

    @property
    def passed(self) -> bool:
        return self.median_relative_error <= 0.25 and self.p90_relative_error <= 0.50


def aggregate_relative_error_metrics(
    expected_fractions: Mapping[str, Decimal],
    estimated_fractions: Mapping[str, Decimal],
    feature_to_group: Mapping[str, str],
) -> AggregateRelativeErrorMetrics:
    if set(expected_fractions) != set(estimated_fractions) or set(expected_fractions) != set(feature_to_group):
        raise ValueError("Equivalence aggregation requires exact feature identity")
    expected_groups: dict[str, Decimal] = {}
    estimated_groups: dict[str, Decimal] = {}
    for name, group in feature_to_group.items():
        expected_groups[group] = expected_groups.get(group, Decimal(0)) + expected_fractions[name]
        estimated_groups[group] = estimated_groups.get(group, Decimal(0)) + estimated_fractions[name]
    errors = [
        abs(float(estimated_groups[group] - expected) / float(expected))
        for group, expected in expected_groups.items()
    ]
    return AggregateRelativeErrorMetrics(len(errors), statistics.median(errors), percentile(errors, 0.90))


@dataclass(frozen=True)
class ConcentrationMetrics:
    features: int
    detected: int
    detection_rate: float
    pearson: float | None
    spearman: float | None

    @property
    def passed(self) -> bool:
        return (
            self.detection_rate >= 0.95 and self.pearson is not None and self.pearson >= 0.95
            and self.spearman is not None and self.spearman >= 0.95
        )


def concentration_metrics(
    truth: Mapping[str, Decimal], observed_tpm: Mapping[str, Decimal], subset: Sequence[str],
) -> ConcentrationMetrics:
    names = tuple(subset)
    if not names or len(set(names)) != len(names) or set(names) - (set(truth) & set(observed_tpm)):
        raise ValueError("Concentration subset identity mismatch")
    if any(truth[name] <= 0 or not truth[name].is_finite() for name in names):
        raise ValueError("Concentration truth must be finite and positive")
    if any(observed_tpm[name] < 0 or not observed_tpm[name].is_finite() for name in names):
        raise ValueError("Observed concentration TPM must be finite and nonnegative")
    detected_names = tuple(name for name in names if observed_tpm[name] > 0)
    left = [math.log10(float(truth[name])) for name in detected_names]
    right = [math.log10(float(observed_tpm[name])) for name in detected_names]
    if len(detected_names) < 2:
        pearson = rank = None
    else:
        pearson, rank = correlation(left, right), spearman(left, right)
    return ConcentrationMetrics(len(names), len(detected_names), len(detected_names) / len(names), pearson, rank)


@dataclass(frozen=True)
class AbundanceMetrics:
    features: int
    detection_rate: float
    upper_half_detection_rate: float
    pearson: float | None
    spearman: float | None
    median_absolute_log2_error: float
    p90_absolute_log2_error: float

    @property
    def transcript_gate(self) -> GateState:
        if self.pearson is None or self.spearman is None:
            return GateState.UNDEFINED_ZERO_VARIANCE
        passed = (
            self.detection_rate >= 0.90 and self.upper_half_detection_rate >= 0.95
            and self.pearson >= 0.90 and self.spearman >= 0.90
            and self.median_absolute_log2_error <= 0.75
            and self.p90_absolute_log2_error <= 1.50
        )
        return GateState.PASS if passed else GateState.FAIL


def abundance_metrics(
    expected: Mapping[str, Decimal], observed: Mapping[str, Decimal],
) -> AbundanceMetrics:
    names = sorted(expected)
    if len(names) < 2 or set(names) - set(observed):
        raise ValueError("Abundance vectors require the same feature identity")
    if any(expected[name] <= 0 or observed[name] < 0 for name in names):
        raise ValueError("Abundance values must be finite nonnegative with positive truth")
    truth = [float(expected[name]) for name in names]
    estimate = [float(observed[name]) for name in names]
    if any(not math.isfinite(value) for value in truth + estimate):
        raise ValueError("Abundance values must be finite")
    detected = [observed[name] > 0 for name in names]
    upper = upper_fraction_ids(expected, Decimal("0.5"))
    positive_pairs = [(truth[i], estimate[i]) for i in range(len(names)) if estimate[i] > 0]
    if not positive_pairs:
        errors = [math.inf]
    else:
        offsets = [math.log2(b) - math.log2(a) for a, b in positive_pairs]
        scale = statistics.median(offsets)
        errors = [abs(math.log2(b) - math.log2(a) - scale) for a, b in positive_pairs]
        errors.extend([math.inf] * (len(names) - len(positive_pairs)))
    return AbundanceMetrics(
        features=len(names), detection_rate=sum(detected) / len(names),
        upper_half_detection_rate=sum(observed[name] > 0 for name in upper) / len(upper),
        pearson=correlation([math.log2(value) for value in truth], [math.log2(value + 1e-300) for value in estimate]),
        spearman=spearman(truth, estimate),
        median_absolute_log2_error=statistics.median(errors),
        p90_absolute_log2_error=percentile(errors, 0.90),
    )


@dataclass(frozen=True)
class ErccFoldChangeMetrics:
    spearman: float | None
    rmse: float
    median_absolute_error: float
    direction_accuracy_by_group: Mapping[str, float]
    group_median_error: Mapping[str, float]

    @property
    def passed(self) -> bool:
        if self.spearman is None or self.spearman < 0.95:
            return False
        if self.rmse > 0.50 or self.median_absolute_error > 0.35:
            return False
        for group in ("A", "C", "D"):
            if self.direction_accuracy_by_group[group] < 0.95 or abs(self.group_median_error[group]) > 0.35:
                return False
        return abs(self.group_median_error["B"]) <= 0.25


def ercc_fold_change_metrics(
    truth: Sequence[ErccTruthRow], mix1: Mapping[str, Decimal],
    mix2: Mapping[str, Decimal], subset: Sequence[str],
) -> ErccFoldChangeMetrics:
    by_id = {row.ercc_id: row for row in truth}
    if set(subset) - (set(by_id) & set(mix1) & set(mix2)):
        raise ValueError("ERCC fold-change subset identity mismatch")
    expected: list[float] = []
    observed: list[float] = []
    grouped: dict[str, list[tuple[float, float]]] = {key: [] for key in "ABCD"}
    for name in subset:
        if mix1[name] <= 0 or mix2[name] <= 0:
            raise ValueError("Primary ERCC fold-change subset must be detected in both mixes")
        row = by_id[name]
        left = float(row.expected_log2_ratio)
        right = math.log2(float(mix1[name] / mix2[name]))
        expected.append(left)
        observed.append(right)
        grouped[row.subgroup].append((left, right))
    errors = [right - left for left, right in zip(expected, observed)]
    direction: dict[str, float] = {}
    medians: dict[str, float] = {}
    for group, pairs in grouped.items():
        if not pairs:
            raise ValueError(f"Missing ERCC subgroup {group}")
        direction[group] = sum(
            (left == 0 and abs(right) <= 0.25) or (left > 0) == (right > 0)
            for left, right in pairs
        ) / len(pairs)
        medians[group] = statistics.median(right - left for left, right in pairs)
    return ErccFoldChangeMetrics(
        spearman(expected, observed),
        math.sqrt(statistics.fmean(error * error for error in errors)),
        statistics.median(abs(error) for error in errors), direction, medians,
    )


@dataclass(frozen=True)
class CrossMappingResult:
    processed: int
    mapped: int
    highest_target: str | None
    highest_target_mass: Decimal

    @property
    def mapped_fraction(self) -> Decimal:
        if self.processed <= 0 or self.mapped < 0 or self.mapped > self.processed:
            raise ValueError("Invalid cross-mapping fragment accounting")
        return Decimal(self.mapped) / Decimal(self.processed)

    @property
    def blocked(self) -> bool:
        return self.mapped_fraction > Decimal("0.001")

    @property
    def warning(self) -> bool:
        return self.mapped_fraction > Decimal("0.0005")


@dataclass(frozen=True)
class ExternalRepeatIdentity:
    quant_sha256: str
    gene_quant_sha256: str | None
    scientific_metadata_sha256: str
    processed: int
    mapped: int
    feature_order: tuple[str, ...]
    zero_status: tuple[bool, ...]


def validate_external_repeats(
    runs: Sequence[ExternalRepeatIdentity], *, expected_fragments: int,
) -> None:
    if not runs or expected_fragments <= 0:
        raise ValueError("External repeat gate requires runs and an input fragment count")
    first = runs[0]
    if any(run.processed != expected_fragments for run in runs):
        raise ValueError("External fragment accounting is not exact")
    if any(run != first for run in runs[1:]):
        raise ValueError("External deterministic output is not byte/scientifically exact")


def validate_download_url(url: str) -> None:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_DOWNLOAD_HOSTS:
        raise ValueError("External qualification download URL is not allowlisted")
    if parsed.username or parsed.password or parsed.query:
        raise ValueError("Credentialed or query-parameter download URLs are forbidden")


def canonical_preregistration_sha256(document: Mapping[str, object]) -> str:
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def as_jsonable(value: object) -> object:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)  # type: ignore[arg-type]
    raise TypeError("Unsupported qualification value")
