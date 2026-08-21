"""Pure cause-isolation contracts for the external SIRV/ERCC failures."""

from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Iterable, Mapping, Sequence


SIRV_EQUIVALENCE_MEDIAN_LIMIT = 0.25
SIRV_EQUIVALENCE_P90_LIMIT = 0.50
ERCC_AGGREGATE_CROSSMAPPING_LIMIT = 0.001


def validate_preserved_failure_thresholds(
    *, sirv_median: float, sirv_p90: float, ercc_crossmapping: float,
) -> None:
    """Reject post-result mutation of the historical preregistered limits."""
    observed = (sirv_median, sirv_p90, ercc_crossmapping)
    expected = (
        SIRV_EQUIVALENCE_MEDIAN_LIMIT,
        SIRV_EQUIVALENCE_P90_LIMIT,
        ERCC_AGGREGATE_CROSSMAPPING_LIMIT,
    )
    if observed != expected:
        raise ValueError("Historical external-truth thresholds are immutable")


class GateCoherence(str, Enum):
    COHERENT = "COHERENT"
    INTERNALLY_INCONSISTENT = "INTERNALLY_INCONSISTENT"
    INCOMPARABLE_METRICS = "INCOMPARABLE_METRICS"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class ThresholdScale:
    metric: str
    threshold: float
    over_relative: float
    under_relative: float
    over_log2: float
    under_log2: float
    symmetric_on_input_scale: bool


def log2_threshold_scale(threshold: float, *, metric: str) -> ThresholdScale:
    if not math.isfinite(threshold) or threshold < 0:
        raise ValueError("Log2 threshold must be finite and nonnegative")
    return ThresholdScale(
        metric, threshold, (2**threshold) - 1, 1 - (2 ** (-threshold)),
        threshold, threshold, True,
    )


def relative_threshold_scale(threshold: float, *, metric: str) -> ThresholdScale:
    if not math.isfinite(threshold) or not 0 <= threshold < 1:
        raise ValueError("Relative threshold must be finite and in [0, 1)")
    return ThresholdScale(
        metric, threshold, threshold, threshold, math.log2(1 + threshold),
        -math.log2(1 - threshold), False,
    )


def classify_gate_coherence(
    transcript_log2: ThresholdScale, group_relative: ThresholdScale,
) -> GateCoherence:
    if transcript_log2.metric == group_relative.metric:
        return GateCoherence.COHERENT
    if group_relative.over_log2 > transcript_log2.over_log2 or group_relative.under_log2 > transcript_log2.under_log2:
        return GateCoherence.INTERNALLY_INCONSISTENT
    return GateCoherence.INCOMPARABLE_METRICS


@dataclass(frozen=True)
class EquivalenceMember:
    transcript_id: str
    group_id: str
    gene_id: str
    expected_fraction: Decimal
    estimated_fraction: Decimal
    identifiable: bool
    length: int
    gc_fraction: float
    detected: bool
    sirv502: bool = False


@dataclass(frozen=True)
class EquivalenceGroupAudit:
    group_id: str
    members: tuple[str, ...]
    genes: tuple[str, ...]
    expected_fraction: Decimal
    estimated_fraction: Decimal
    relative_error: float
    absolute_log2_error: float
    identifiable: bool
    sirv502: bool
    mean_length: float
    mean_gc: float


def audit_equivalence_partition(
    members: Sequence[EquivalenceMember], *, expected_transcripts: int = 69,
) -> tuple[EquivalenceGroupAudit, ...]:
    if len(members) != expected_transcripts or len({row.transcript_id for row in members}) != len(members):
        raise ValueError("Equivalence groups must cover every transcript exactly once")
    if any(row.expected_fraction <= 0 or row.estimated_fraction < 0 for row in members):
        raise ValueError("Equivalence fractions require positive truth and nonnegative estimates")
    expected_total = sum((row.expected_fraction for row in members), Decimal(0))
    estimated_total = sum((row.estimated_fraction for row in members), Decimal(0))
    tolerance = Decimal("1e-18")
    if abs(expected_total - Decimal(1)) > tolerance or abs(estimated_total - Decimal(1)) > tolerance:
        raise ValueError("Partition fractions must sum to one over the same feature universe")
    by_group: dict[str, list[EquivalenceMember]] = {}
    for row in members:
        if not row.group_id:
            raise ValueError("Equivalence group ID cannot be empty")
        by_group.setdefault(row.group_id, []).append(row)
    result = []
    for group, rows in sorted(by_group.items()):
        expected = sum((row.expected_fraction for row in rows), Decimal(0))
        estimated = sum((row.estimated_fraction for row in rows), Decimal(0))
        ratio = estimated / expected
        result.append(EquivalenceGroupAudit(
            group, tuple(sorted(row.transcript_id for row in rows)),
            tuple(sorted({row.gene_id for row in rows})), expected, estimated,
            abs(float(estimated - expected) / float(expected)),
            math.inf if estimated == 0 else abs(math.log2(float(ratio))),
            all(row.identifiable for row in rows), any(row.sirv502 for row in rows),
            statistics.fmean(row.length for row in rows),
            statistics.fmean(row.gc_fraction for row in rows),
        ))
    return tuple(result)


class OffTargetClass(str, Enum):
    HUMAN_MT_UNIQUE = "HUMAN_MT_UNIQUE"
    ERCC_UNIQUE_MISASSIGNED = "ERCC_UNIQUE_MISASSIGNED"
    EXACT_TIE = "EXACT_TIE"
    AMBIGUOUS = "AMBIGUOUS"
    LOW_COMPLEXITY_OR_ADAPTER = "LOW_COMPLEXITY_OR_ADAPTER"
    UNRESOLVED = "UNRESOLVED"


def reverse_complement(sequence: str) -> str:
    try:
        return sequence.upper().translate(str.maketrans("ACGTN", "TGCAN"))[::-1]
    except KeyError as error:  # pragma: no cover - translate does not raise for unknown chars
        raise ValueError("Invalid DNA sequence") from error


def shannon_entropy(sequence: str) -> float:
    if not sequence:
        return 0.0
    counts = Counter(sequence.upper())
    return -sum((count / len(sequence)) * math.log2(count / len(sequence)) for count in counts.values())


ILLUMINA_ADAPTERS = (
    "AGATCGGAAGAGCACACGTCTGAACTCCAGTCA",
    "AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT",
)


def low_complexity_or_adapter(reads: Sequence[str]) -> bool:
    for sequence in reads:
        upper = sequence.upper()
        if not upper or shannon_entropy(upper) <= 1.0:
            return True
        if max(Counter(upper).values()) / len(upper) >= 0.80:
            return True
        if any(adapter[:12] in upper or reverse_complement(adapter[:12]) in upper for adapter in ILLUMINA_ADAPTERS):
            return True
    return False


def exact_reference_support(reads: Sequence[str], references: Mapping[str, str]) -> frozenset[str]:
    support = set()
    for reference_class, reference in references.items():
        upper = reference.upper()
        if all(read.upper() in upper or reverse_complement(read) in upper for read in reads):
            support.add(reference_class)
    return frozenset(support)


def classify_offtarget_pair(
    reads: Sequence[str], *, human_score: int | None, ercc_score: int | None,
    exact_support: Iterable[str] = (), unique_margin: int = 10,
) -> OffTargetClass:
    if low_complexity_or_adapter(reads):
        return OffTargetClass.LOW_COMPLEXITY_OR_ADAPTER
    exact = frozenset(exact_support)
    if exact == {"human_mt"}:
        return OffTargetClass.HUMAN_MT_UNIQUE
    if exact == {"ercc"}:
        return OffTargetClass.ERCC_UNIQUE_MISASSIGNED
    if exact == {"human_mt", "ercc"}:
        return OffTargetClass.EXACT_TIE
    if human_score is None and ercc_score is None:
        return OffTargetClass.UNRESOLVED
    if human_score is None:
        return OffTargetClass.ERCC_UNIQUE_MISASSIGNED
    if ercc_score is None:
        return OffTargetClass.HUMAN_MT_UNIQUE
    margin = human_score - ercc_score
    if margin == 0:
        return OffTargetClass.EXACT_TIE
    if abs(margin) < unique_margin:
        return OffTargetClass.AMBIGUOUS
    return OffTargetClass.HUMAN_MT_UNIQUE if margin > 0 else OffTargetClass.ERCC_UNIQUE_MISASSIGNED


class PreprocessingCause(str, Enum):
    PREEXISTING_IN_RAW = "PREEXISTING_IN_RAW"
    INTRODUCED_OR_EXPOSED_BY_TRIMMING = "INTRODUCED_OR_EXPOSED_BY_TRIMMING"
    LOW_COMPLEXITY_ARTIFACT = "LOW_COMPLEXITY_ARTIFACT"
    UNRESOLVED = "UNRESOLVED"


def classify_preprocessing_effect(
    raw_reads: Sequence[str] | None, processed_reads: Sequence[str],
    *, raw_supported: bool, processed_supported: bool,
) -> PreprocessingCause:
    if low_complexity_or_adapter(processed_reads):
        return PreprocessingCause.LOW_COMPLEXITY_ARTIFACT
    if raw_reads is None:
        return PreprocessingCause.UNRESOLVED
    if raw_supported and processed_supported:
        return PreprocessingCause.PREEXISTING_IN_RAW
    if not raw_supported and processed_supported:
        return PreprocessingCause.INTRODUCED_OR_EXPOSED_BY_TRIMMING
    return PreprocessingCause.UNRESOLVED


@dataclass(frozen=True)
class OffTargetRates:
    processed_fragments: int
    classified_fragments: int
    human_mt_unique: int
    ercc_unique_misassigned: int
    ercc_identifiable: int
    exact_tie: int
    ambiguous: int

    @property
    def sample_purity_rate(self) -> float:
        return self.human_mt_unique / self.processed_fragments

    @property
    def algorithmic_misassignment_rate(self) -> float:
        if self.ercc_identifiable <= 0:
            raise ValueError("ERCC-identifiable denominator must be positive")
        return self.ercc_unique_misassigned / self.ercc_identifiable

    @property
    def ambiguous_rate(self) -> float:
        return (self.exact_tie + self.ambiguous) / self.processed_fragments

    def validate(self) -> None:
        values = (
            self.processed_fragments, self.classified_fragments, self.human_mt_unique,
            self.ercc_unique_misassigned, self.ercc_identifiable, self.exact_tie, self.ambiguous,
        )
        if any(value < 0 for value in values) or self.processed_fragments <= 0:
            raise ValueError("Off-target counts must be nonnegative with processed fragments")
        if self.classified_fragments > self.processed_fragments:
            raise ValueError("Classified fragments cannot exceed processed fragments")


def select_holdout_runs(
    candidates: Sequence[object], *, training_runs: frozenset[str], per_mix: int = 2,
) -> tuple[object, ...]:
    eligible = [
        row for row in candidates
        if getattr(row, "run_accession") not in training_runs
        and getattr(row, "site") == "BGI"
        and getattr(row, "platform") == "Illumina HiSeq 2000"
        and getattr(row, "library_id") == "1"
        and getattr(row, "flowcell") == "AC0AYTACXX"
        and getattr(row, "layout") == "PAIRED"
        and getattr(row, "read_length") == 100
    ]
    result = []
    for mix in ("Mix1", "Mix2"):
        rows = sorted((row for row in eligible if getattr(row, "mix") == mix), key=lambda row: getattr(row, "run_accession"))
        if len(rows) < per_mix:
            raise ValueError("Insufficient metadata-matched unused holdout lanes")
        result.extend(rows[:per_mix])
    return tuple(result)
