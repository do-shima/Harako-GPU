"""Independent decoy identifiability and corrected leakage gates."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import Enum
from typing import Iterable, Mapping, Sequence


ORACLE_SCHEMA_VERSION = "decoy_identifiability_v1"
LEAKAGE_THRESHOLD = Decimal("0.01")
RELATIVE_REDUCTION_THRESHOLD = Decimal("0.90")
DOMINANT_MARGIN = 4
UNIQUE_TRANSCRIPT_DISTANCE = 12
MAPPABLE_DISTANCE = 12
SEED_LENGTH = 15
FRAGMENT_LENGTH_MIN = 200
FRAGMENT_LENGTH_MAX = 280


class IdentifiabilityClass(str, Enum):
    DECOY_UNIQUE = "DECOY_UNIQUE"
    DECOY_DOMINANT = "DECOY_DOMINANT"
    DECOY_AMBIGUOUS = "DECOY_AMBIGUOUS"
    DECOY_EXACT_TIE = "DECOY_EXACT_TIE"
    DECOY_UNMAPPABLE = "DECOY_UNMAPPABLE"
    NOT_DECOY_ORIGIN = "NOT_DECOY_ORIGIN"


@dataclass(frozen=True)
class PairMatch:
    target_id: str | None
    distance: int
    start: int | None
    fragment_length: int | None


@dataclass(frozen=True)
class IdentifiabilityEvidence:
    fragment_id: str
    sample: str
    source_decoy: str
    source_interval: tuple[int, int] | None
    r1_sequence: str
    r2_sequence: str
    best_decoy_id: str | None
    best_decoy_distance: int
    best_transcript_id: str | None
    best_transcript_distance: int
    score_margin: int
    identifiability_class: IdentifiabilityClass
    classification_reason: str
    schema_version: str = ORACLE_SCHEMA_VERSION

    def scientific_digest(self) -> str:
        encoded = json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


def reverse_complement(sequence: str) -> str:
    if any(base not in "ACGT" for base in sequence):
        raise ValueError("Oracle accepts only uppercase A/C/G/T sequences")
    return sequence.translate(str.maketrans("ACGT", "TGCA"))[::-1]


def hamming(left: str, right: str) -> int:
    if len(left) != len(right):
        raise ValueError("Hamming distance requires equal-length sequences")
    return sum(a != b for a, b in zip(left, right))


class PairedSequenceOracle:
    """Information oracle; this is deliberately not Salmon scoring."""

    def __init__(self, transcripts: Mapping[str, str], decoys: Mapping[str, str]) -> None:
        if not transcripts or not decoys or set(transcripts) & set(decoys):
            raise ValueError("Oracle requires distinct transcript and decoy references")
        self.transcripts = dict(transcripts)
        self.decoys = dict(decoys)
        self._transcript_seeds = self._seed_index(self.transcripts)
        self._decoy_seeds = self._seed_index(self.decoys)

    @staticmethod
    def _seed_index(sequences: Mapping[str, str]) -> dict[str, list[tuple[str, int]]]:
        result: dict[str, list[tuple[str, int]]] = {}
        for target, sequence in sequences.items():
            if any(base not in "ACGT" for base in sequence):
                raise ValueError(f"Invalid reference sequence: {target}")
            for start in range(len(sequence) - SEED_LENGTH + 1):
                result.setdefault(sequence[start:start + SEED_LENGTH], []).append((target, start))
        return result

    @staticmethod
    def _candidate_starts(r2: str, index: Mapping[str, Sequence[tuple[str, int]]]) -> set[tuple[str, int]]:
        candidates: set[tuple[str, int]] = set()
        for offset in range(0, len(r2) - SEED_LENGTH + 1, 17):
            seed = r2[offset:offset + SEED_LENGTH]
            for target, position in index.get(seed, ()):
                start = position - offset
                if start >= 0:
                    candidates.add((target, start))
        return candidates

    def _best(
        self, r1: str, r2: str, sequences: Mapping[str, str],
        index: Mapping[str, Sequence[tuple[str, int]]], fragment_length: int | None,
    ) -> PairMatch:
        best = PairMatch(None, len(r1) + len(r2) + 1, None, None)
        left_candidates = self._candidate_starts(r2, index)
        right_candidates = self._candidate_starts(reverse_complement(r1), index)
        paired_candidates: set[tuple[str, int, int]] = set()
        for target, start in left_candidates:
            for right_target, right_start in right_candidates:
                if target != right_target:
                    continue
                candidate_length = right_start + len(r1) - start
                if fragment_length is not None and candidate_length != fragment_length:
                    continue
                if FRAGMENT_LENGTH_MIN <= candidate_length <= FRAGMENT_LENGTH_MAX:
                    paired_candidates.add((target, start, candidate_length))
        # With no valid seed pair, each mate lacking a 15-mer hit contributes
        # a conservative mismatch lower bound. This avoids pretending that a
        # seedless pair has an exact edit distance while retaining deterministic
        # information-class classification.
        if not paired_candidates:
            lower_bound = (len(r2) // SEED_LENGTH if not left_candidates else 0) + (
                len(r1) // SEED_LENGTH if not right_candidates else 0
            )
            return PairMatch(None, max(1, lower_bound), None, fragment_length)
        for target, start, candidate_length in paired_candidates:
            sequence = sequences[target]
            if start + len(r2) > len(sequence):
                continue
            left_distance = hamming(r2, sequence[start:start + len(r2)])
            if left_distance >= best.distance:
                continue
            end = start + candidate_length
            if end > len(sequence):
                continue
            expected_r1 = reverse_complement(sequence[end - len(r1):end])
            distance = left_distance + hamming(r1, expected_r1)
            candidate = PairMatch(target, distance, start, candidate_length)
            if (candidate.distance, candidate.target_id or "", candidate.start or 0) < (
                best.distance, best.target_id or "", best.start or 0
            ):
                best = candidate
        return best

    def classify(
        self, *, fragment_id: str, sample: str, source_decoy: str,
        r1: str, r2: str, source_interval: tuple[int, int] | None = None,
        source_is_decoy: bool = True,
    ) -> IdentifiabilityEvidence:
        if not fragment_id or not sample or len(r1) != len(r2) or not r1:
            raise ValueError("Oracle requires a named equal-length paired fragment")
        if not source_is_decoy:
            return IdentifiabilityEvidence(
                fragment_id, sample, source_decoy, source_interval, r1, r2,
                None, len(r1) + len(r2) + 1, None, len(r1) + len(r2) + 1,
                0, IdentifiabilityClass.NOT_DECOY_ORIGIN,
                "generator source is a transcript",
            )
        fragment_length = (
            source_interval[1] - source_interval[0] if source_interval is not None else None
        )
        decoy = self._best(r1, r2, self.decoys, self._decoy_seeds, fragment_length)
        transcript = self._best(r1, r2, self.transcripts, self._transcript_seeds, fragment_length)
        margin = transcript.distance - decoy.distance
        if min(decoy.distance, transcript.distance) > MAPPABLE_DISTANCE:
            category = IdentifiabilityClass.DECOY_UNMAPPABLE
            reason = "neither reference class is sufficiently supported"
        elif decoy.distance == transcript.distance:
            category = IdentifiabilityClass.DECOY_EXACT_TIE
            reason = "observed pair has equal best decoy and transcript distance"
        elif decoy.distance <= MAPPABLE_DISTANCE and transcript.distance >= UNIQUE_TRANSCRIPT_DISTANCE:
            category = IdentifiabilityClass.DECOY_UNIQUE
            reason = "decoy match is supported and transcript distance exceeds the unique floor"
        elif margin >= DOMINANT_MARGIN:
            category = IdentifiabilityClass.DECOY_DOMINANT
            reason = "decoy has the predeclared dominant distance margin"
        else:
            category = IdentifiabilityClass.DECOY_AMBIGUOUS
            reason = "decoy/transcript evidence is neither a tie nor decisively separated"
        return IdentifiabilityEvidence(
            fragment_id, sample, source_decoy, source_interval, r1, r2,
            decoy.target_id, decoy.distance, transcript.target_id,
            transcript.distance, margin, category, reason,
        )


@dataclass(frozen=True)
class LeakageMeasurement:
    identifiability_class: IdentifiabilityClass
    generated_fragments: int
    estimated_transcript_mass: Decimal

    @property
    def fraction(self) -> Decimal:
        if self.generated_fragments <= 0:
            raise ValueError("Leakage denominator must be generated paired fragments")
        if self.estimated_transcript_mass < 0 or not self.estimated_transcript_mass.is_finite():
            raise ValueError("Leakage numerator must be finite nonnegative estimated count mass")
        return self.estimated_transcript_mass / Decimal(self.generated_fragments)

    @property
    def primary_gate(self) -> bool | None:
        if self.identifiability_class not in {
            IdentifiabilityClass.DECOY_UNIQUE, IdentifiabilityClass.DECOY_DOMINANT,
        }:
            return None
        return self.fraction <= LEAKAGE_THRESHOLD


@dataclass(frozen=True)
class IndexControlReport:
    decoy_aware: LeakageMeasurement
    transcript_only: LeakageMeasurement

    @property
    def relative_reduction(self) -> Decimal:
        baseline = self.transcript_only.fraction
        if baseline == 0:
            # A zero-leakage control cannot demonstrate the required reduction.
            return Decimal(0)
        return (baseline - self.decoy_aware.fraction) / baseline

    @property
    def passed(self) -> bool:
        return self.decoy_aware.primary_gate is True and self.relative_reduction >= RELATIVE_REDUCTION_THRESHOLD


def validate_primary_decoy_gates(reports: Iterable[IndexControlReport]) -> None:
    by_class = {report.decoy_aware.identifiability_class: report for report in reports}
    required = {IdentifiabilityClass.DECOY_UNIQUE, IdentifiabilityClass.DECOY_DOMINANT}
    if set(by_class) != required:
        raise ValueError("Unique and dominant decoy controls are both required")
    failed = [category.value for category, report in by_class.items() if not report.passed]
    if failed:
        raise ValueError("Decoy gate failed: " + ", ".join(sorted(failed)))


def old_v1_aggregate_leakage(
    *, zero_expression_mass: Decimal, total_estimated_mass: Decimal,
    transcript_origin_fragments: int, generated_decoy_fragments: int,
) -> Decimal:
    """Reproduce the v1 aggregate proxy; it cannot attribute individual reads."""

    if generated_decoy_fragments <= 0:
        raise ValueError("v1 generated-decoy denominator must be positive")
    excess = max(Decimal(0), total_estimated_mass - Decimal(transcript_origin_fragments))
    return max(zero_expression_mass, excess) / Decimal(generated_decoy_fragments)


def validate_v1_formula_limitations(*, claims_read_level_attribution: bool) -> None:
    if claims_read_level_attribution:
        raise ValueError("Aggregate quant.sf mass cannot uniquely attribute decoy-origin fragments")


@dataclass(frozen=True)
class RadDiagnosticCounters:
    total_observed_fragments: int
    num_processed: int
    num_mapped: int
    num_decoy_fragments: int
    num_dovetail_fragments: int
    score_filtered_fragments: int
    index_decoy_name_hash: str
    index_decoy_seq_hash: str
    metadata_complete: bool

    def validate(self) -> None:
        counts = (
            self.total_observed_fragments, self.num_processed, self.num_mapped,
            self.num_decoy_fragments, self.num_dovetail_fragments,
            self.score_filtered_fragments,
        )
        if any(value < 0 for value in counts) or self.num_processed != self.total_observed_fragments:
            raise ValueError("RAD diagnostic fragment accounting is incomplete")
        if self.num_mapped > self.num_processed or not self.metadata_complete:
            raise ValueError("RAD diagnostic metadata is incomplete")


def diagnostic_mapping_argv(product_argv: Sequence[str], *, keep_rad: bool) -> tuple[str, ...]:
    values = tuple(product_argv)
    if values[:2] != ("salmon", "quant") or "--deterministic" not in values:
        raise ValueError("Diagnostic argv must extend the fixed deterministic product command")
    if not keep_rad:
        return values
    if "--keepRad" in values:
        raise ValueError("Diagnostic option is already present")
    return (*values, "--keepRad")


@dataclass(frozen=True)
class AccuracySummary:
    count: int
    pearson: float
    spearman: float
    median_ape: float
    p95_ape: float


@dataclass(frozen=True)
class BiologicalTruthReportV2:
    fragment_accounting_exact: bool
    estimated_mass_accounting_exact: bool
    expressed_zero_transitions: int
    identifiable_transcripts: AccuracySummary
    expressed_genes: AccuracySummary
    ambiguous_group_max_relative_error: float
    identifiable_zero_mass_fraction: float
    high_expression_identifiable_false_positives: int
    unidentifiable_assignment_mass: Decimal
    fold_change_direction_accuracy: float
    fold_change_rmse: float
    fold_change_spearman: float

    @property
    def passed(self) -> bool:
        return all((
            self.fragment_accounting_exact,
            self.estimated_mass_accounting_exact,
            self.expressed_zero_transitions == 0,
            self.identifiable_transcripts.pearson >= 0.995,
            self.identifiable_transcripts.spearman >= 0.995,
            self.identifiable_transcripts.median_ape <= 0.05,
            self.identifiable_transcripts.p95_ape <= 0.15,
            self.expressed_genes.pearson >= 0.995,
            self.expressed_genes.spearman >= 0.995,
            self.expressed_genes.median_ape <= 0.05,
            self.expressed_genes.p95_ape <= 0.15,
            self.ambiguous_group_max_relative_error <= 0.05,
            self.identifiable_zero_mass_fraction <= 0.005,
            self.high_expression_identifiable_false_positives == 0,
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
    mean_left, mean_right = statistics.fmean(left), statistics.fmean(right)
    numerator = sum((a - mean_left) * (b - mean_right) for a, b in zip(left, right))
    denominator = math.sqrt(
        sum((a - mean_left) ** 2 for a in left) *
        sum((b - mean_right) ** 2 for b in right)
    )
    return numerator / denominator if denominator else (1.0 if list(left) == list(right) else 0.0)


def _accuracy(truth: Mapping[str, int], estimated: Mapping[str, Decimal]) -> AccuracySummary:
    names = sorted(truth)
    if not names or any(truth[name] <= 0 for name in names):
        raise ValueError("Accuracy requires positive truth values")
    expected = [float(truth[name]) for name in names]
    observed = [float(estimated.get(name, Decimal(0))) for name in names]
    ape = sorted(abs(a - b) / a for a, b in zip(expected, observed))
    position = (len(ape) - 1) * 0.95
    low, high = math.floor(position), math.ceil(position)
    p95 = ape[low] if low == high else ape[low] * (high - position) + ape[high] * (position - low)
    return AccuracySummary(
        len(names), _correlation(expected, observed),
        _correlation(_ranks(expected), _ranks(observed)), statistics.median(ape), p95,
    )


def build_truth_v2_biological_report(
    *, manifest: Mapping[str, object], quant_by_sample: Mapping[str, Mapping[str, Decimal]],
    processed_by_sample: Mapping[str, int], mapped_by_sample: Mapping[str, int],
) -> BiologicalTruthReportV2:
    """Evaluate v2 biology while excluding ambiguous/tie decoy mass from false-positive gates."""

    samples = {str(row["sample"]): row for row in manifest["main_samples"]}  # type: ignore[index]
    transcripts = {str(row["transcript_id"]): row for row in manifest["transcripts"]}  # type: ignore[index]
    if set(samples) != set(quant_by_sample) or set(samples) != set(processed_by_sample) or set(samples) != set(mapped_by_sample):
        raise ValueError("Truth-v2 biological sample identity mismatch")
    zero_identifiable = set(manifest["zero_identifiable_transcripts"])  # type: ignore[arg-type]
    exact_tie_homolog = "tx_zero_03_1"
    fragment_exact = True
    mass_exact = True
    zero_transitions = 0
    unique_truth: dict[str, int] = {}
    unique_estimated: dict[str, Decimal] = {}
    gene_truth: dict[str, int] = {}
    gene_estimated: dict[str, Decimal] = {}
    group_truth: dict[str, int] = {}
    group_estimated: dict[str, Decimal] = {}
    identifiable_zero_mass = Decimal(0)
    unidentifiable_mass = Decimal(0)
    total_estimated = Decimal(0)
    high_false_positives = 0
    condition_truth: dict[str, dict[str, list[int]]] = {}
    condition_estimated: dict[str, dict[str, list[Decimal]]] = {}
    for sample, sample_row in samples.items():
        estimates = quant_by_sample[sample]
        if not set(transcripts).issubset(estimates):
            raise ValueError(f"Missing transcript estimates: {sample}")
        expected_fragments = int(sample_row["fragments"])
        fragment_exact &= processed_by_sample[sample] == expected_fragments
        sample_mass = sum(estimates.values(), Decimal(0))
        total_estimated += sample_mass
        mass_exact &= abs(sample_mass - Decimal(mapped_by_sample[sample])) <= Decimal("0.001")
        counts = sample_row["transcript_counts"]
        condition = str(sample_row["condition"])
        condition_truth.setdefault(condition, {})
        condition_estimated.setdefault(condition, {})
        for transcript_id, row in transcripts.items():
            truth = int(counts[transcript_id])
            estimate = estimates[transcript_id]
            gene, stratum = str(row["gene_id"]), str(row["stratum"])
            if stratum == "unique_identifiable" and truth > 0:
                key = f"{sample}:{transcript_id}"
                unique_truth[key], unique_estimated[key] = truth, estimate
            if truth >= 50 and estimate == 0:
                zero_transitions += 1
            if stratum != "paralog_group":
                key = f"{sample}:{gene}"
                gene_truth[key] = gene_truth.get(key, 0) + truth
                gene_estimated[key] = gene_estimated.get(key, Decimal(0)) + estimate
            if stratum in {"ambiguous_isoform", "paralog_group"}:
                key = f"{sample}:{row['group_id']}"
                group_truth[key] = group_truth.get(key, 0) + truth
                group_estimated[key] = group_estimated.get(key, Decimal(0)) + estimate
            if transcript_id in zero_identifiable:
                identifiable_zero_mass += estimate
                high_false_positives += estimate >= 50
            if transcript_id == exact_tie_homolog:
                unidentifiable_mass += estimate
            condition_truth[condition].setdefault(gene, []).append(truth)
            condition_estimated[condition].setdefault(gene, []).append(estimate)
    gene_truth = {name: value for name, value in gene_truth.items() if value > 0}
    gene_estimated = {name: gene_estimated[name] for name in gene_truth}
    group_errors = [
        abs(float(group_estimated[name]) - truth) / truth
        for name, truth in group_truth.items() if truth > 0
    ]
    true_fc: list[float] = []
    estimated_fc: list[float] = []
    for gene in sorted(set(condition_truth["A"]) & set(condition_truth["B"])):
        truth_a = sum(condition_truth["A"][gene]) / 3
        truth_b = sum(condition_truth["B"][gene]) / 3
        if max(truth_a, truth_b) < 100 or truth_a <= 0 or truth_b <= 0:
            continue
        truth_log2 = math.log2(truth_b / truth_a)
        if abs(truth_log2) < 1:
            continue
        estimate_a = sum(condition_estimated["A"][gene], Decimal(0)) / Decimal(3)
        estimate_b = sum(condition_estimated["B"][gene], Decimal(0)) / Decimal(3)
        true_fc.append(truth_log2)
        estimated_fc.append(math.log2(max(float(estimate_b), 1e-12) / max(float(estimate_a), 1e-12)))
    directions = sum((a > 0) == (b > 0) for a, b in zip(true_fc, estimated_fc)) / len(true_fc)
    rmse = math.sqrt(statistics.fmean((a - b) ** 2 for a, b in zip(true_fc, estimated_fc)))
    return BiologicalTruthReportV2(
        fragment_exact, mass_exact, zero_transitions,
        _accuracy(unique_truth, unique_estimated), _accuracy(gene_truth, gene_estimated),
        max(group_errors, default=0.0),
        float(identifiable_zero_mass / total_estimated) if total_estimated else 1.0,
        high_false_positives, unidentifiable_mass,
        directions, rmse, _correlation(_ranks(true_fc), _ranks(estimated_fc)),
    )
