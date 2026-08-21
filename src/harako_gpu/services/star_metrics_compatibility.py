"""Validate genuine STAR summaries without inventing missing metrics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


STAR_METRIC_SCHEMA_VERSION = 1


class StarLogKind(str, Enum):
    STANDARD_FINAL = "STANDARD_STAR_LOG_FINAL"
    PARABRICKS_GENERIC = "PARABRICKS_GENERIC_LOG"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class AlignmentQcStatus(str, Enum):
    PASS = "QC_PASS"
    FAIL = "QC_FAIL"
    NOT_EVALUABLE = "QC_NOT_EVALUABLE"


@dataclass(frozen=True)
class StarAlignmentMetrics:
    input_reads: int
    uniquely_mapped_reads: int
    uniquely_mapped_percent: float
    multimapped_reads: int
    multimapped_percent: float
    too_many_loci_reads: int
    too_many_loci_percent: float
    unmapped_mismatches_percent: float
    unmapped_too_short_percent: float
    unmapped_other_percent: float
    counting_unit: str
    source: str = "standard_star_log_final"
    metric_schema_version: int = STAR_METRIC_SCHEMA_VERSION


@dataclass(frozen=True)
class StarLogAssessment:
    kind: StarLogKind
    metrics: StarAlignmentMetrics | None
    missing_fields: tuple[str, ...]
    source: str


@dataclass(frozen=True)
class AlignmentQcDecision:
    status: AlignmentQcStatus
    observed_percent: float | None
    threshold_percent: float
    metric: str = "star_uniquely_mapped_reads_percent"


_FIELDS: dict[str, tuple[re.Pattern[str], type[int] | type[float]]] = {
    "input_reads": (re.compile(r"Number of input reads\s*\|\s*(\d+)"), int),
    "uniquely_mapped_reads": (re.compile(r"Uniquely mapped reads number\s*\|\s*(\d+)"), int),
    "uniquely_mapped_percent": (re.compile(r"Uniquely mapped reads %\s*\|\s*([\d.]+)%"), float),
    "multimapped_reads": (re.compile(r"Number of reads mapped to multiple loci\s*\|\s*(\d+)"), int),
    "multimapped_percent": (re.compile(r"% of reads mapped to multiple loci\s*\|\s*([\d.]+)%"), float),
    "too_many_loci_reads": (re.compile(r"Number of reads mapped to too many loci\s*\|\s*(\d+)"), int),
    "too_many_loci_percent": (re.compile(r"% of reads mapped to too many loci\s*\|\s*([\d.]+)%"), float),
    "unmapped_mismatches_percent": (
        re.compile(r"% of reads unmapped: too many mismatches\s*\|\s*([\d.]+)%"),
        float,
    ),
    "unmapped_too_short_percent": (
        re.compile(r"% of reads unmapped: too short\s*\|\s*([\d.]+)%"),
        float,
    ),
    "unmapped_other_percent": (re.compile(r"% of reads unmapped: other\s*\|\s*([\d.]+)%"), float),
}


def parse_star_final_summary(text: str, *, paired_end: bool) -> StarLogAssessment:
    """Parse a complete standard STAR final summary or return a non-numeric state."""

    values: dict[str, int | float] = {}
    for name, (pattern, value_type) in _FIELDS.items():
        match = pattern.search(text)
        if match:
            values[name] = value_type(match.group(1))
    missing = tuple(name for name in _FIELDS if name not in values)
    if missing:
        kind = StarLogKind.PARABRICKS_GENERIC if "[PB Info" in text else StarLogKind.NOT_EVALUABLE
        return StarLogAssessment(kind, None, missing, "parabricks_generic_log" if kind is StarLogKind.PARABRICKS_GENERIC else "unknown")
    metrics = StarAlignmentMetrics(
        **values,
        counting_unit="paired_fragments" if paired_end else "reads",
    )
    return StarLogAssessment(StarLogKind.STANDARD_FINAL, metrics, (), metrics.source)


def evaluate_unique_mapping(
    assessment: StarLogAssessment,
    *,
    threshold_percent: float,
) -> AlignmentQcDecision:
    """Evaluate the nf-core mapping gate without coercing absent metrics to zero."""

    if assessment.metrics is None:
        return AlignmentQcDecision(AlignmentQcStatus.NOT_EVALUABLE, None, threshold_percent)
    observed = assessment.metrics.uniquely_mapped_percent
    status = AlignmentQcStatus.PASS if observed >= threshold_percent else AlignmentQcStatus.FAIL
    return AlignmentQcDecision(status, observed, threshold_percent)
