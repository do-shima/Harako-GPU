from __future__ import annotations

from pathlib import Path

from harako_gpu.services.star_metrics_compatibility import (
    AlignmentQcStatus,
    StarLogKind,
    evaluate_unique_mapping,
    parse_star_final_summary,
)


FIXTURES = Path(__file__).parent / "fixtures"


def test_generic_parabricks_log_is_not_accepted_as_star_summary() -> None:
    assessment = parse_star_final_summary(
        (FIXTURES / "parabricks_generic_log.txt").read_text(encoding="utf-8"),
        paired_end=True,
    )
    assert assessment.kind is StarLogKind.PARABRICKS_GENERIC
    assert assessment.metrics is None
    decision = evaluate_unique_mapping(assessment, threshold_percent=5)
    assert decision.status is AlignmentQcStatus.NOT_EVALUABLE
    assert decision.observed_percent is None


def test_standard_star_summary_has_real_value_and_paired_end_policy() -> None:
    assessment = parse_star_final_summary(
        (FIXTURES / "star_final_standard.txt").read_text(encoding="utf-8"),
        paired_end=True,
    )
    assert assessment.kind is StarLogKind.STANDARD_FINAL
    assert assessment.metrics is not None
    assert assessment.metrics.uniquely_mapped_reads == 43442
    assert assessment.metrics.uniquely_mapped_percent == 87.33
    assert assessment.metrics.counting_unit == "paired_fragments"
    assert assessment.source == "standard_star_log_final"
    decision = evaluate_unique_mapping(assessment, threshold_percent=5)
    assert decision.status is AlignmentQcStatus.PASS
    assert decision.observed_percent == 87.33


def test_missing_unique_metric_is_not_evaluable_not_false_zero() -> None:
    assessment = parse_star_final_summary("Number of input reads | 49747\n", paired_end=False)
    decision = evaluate_unique_mapping(assessment, threshold_percent=5)
    assert assessment.kind is StarLogKind.NOT_EVALUABLE
    assert decision.status is AlignmentQcStatus.NOT_EVALUABLE
    assert decision.observed_percent is None
