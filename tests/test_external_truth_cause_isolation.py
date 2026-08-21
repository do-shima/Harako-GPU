from __future__ import annotations

import math
from dataclasses import replace
from decimal import Decimal

import pytest

from harako_gpu.services.external_truth_cause_isolation import (
    EquivalenceMember,
    GateCoherence,
    OffTargetClass,
    OffTargetRates,
    PreprocessingCause,
    audit_equivalence_partition,
    classify_gate_coherence,
    classify_offtarget_pair,
    classify_preprocessing_effect,
    exact_reference_support,
    log2_threshold_scale,
    low_complexity_or_adapter,
    relative_threshold_scale,
    reverse_complement,
    select_holdout_runs,
    validate_preserved_failure_thresholds,
)
from harako_gpu.services.external_truth_validation import ExternalRunCandidate


def _members() -> list[EquivalenceMember]:
    unit = Decimal(1) / Decimal(69)
    return [
        EquivalenceMember(
            f"SIRV{index:03d}", f"g{index // 2}", f"SIRV{(index - 1) % 7 + 1}",
            unit, unit, index % 5 != 0, 500 + index, 0.45, True,
            sirv502=index == 50,
        )
        for index in range(1, 70)
    ]


def test_gate_scale_conversion_exposes_asymmetry_and_incomparability() -> None:
    transcript = log2_threshold_scale(0.75, metric="absolute_log2")
    group = relative_threshold_scale(0.25, metric="relative")
    assert transcript.over_relative == pytest.approx(0.6817928305)
    assert transcript.under_relative == pytest.approx(0.4053964425)
    assert group.over_log2 == pytest.approx(math.log2(1.25))
    assert group.under_log2 == pytest.approx(-math.log2(0.75))
    assert not group.symmetric_on_input_scale
    assert classify_gate_coherence(transcript, group) is GateCoherence.INCOMPARABLE_METRICS


def test_equivalence_groups_form_an_exhaustive_nonoverlapping_partition() -> None:
    rows = audit_equivalence_partition(_members())
    assert sum(len(row.members) for row in rows) == 69
    assert sum((row.expected_fraction for row in rows), Decimal(0)) == pytest.approx(Decimal(1))
    assert any(row.sirv502 for row in rows)
    broken = _members()
    broken[-1] = replace(broken[-1], transcript_id=broken[0].transcript_id)
    with pytest.raises(ValueError, match="exactly once"):
        audit_equivalence_partition(broken)
    with pytest.raises(ValueError, match="sum to one"):
        audit_equivalence_partition([replace(row, estimated_fraction=Decimal(0)) for row in _members()])


def test_exact_sequence_oracle_handles_human_ercc_tie_and_reverse_complement() -> None:
    human = "ACGTTGCA" * 20
    ercc = "TTGGAACC" * 20
    assert reverse_complement("ACGTN") == "NACGT"
    refs = {"human_mt": human, "ercc": ercc}
    reads = (human[10:50], reverse_complement(human[70:110]))
    support = exact_reference_support(reads, refs)
    assert support == {"human_mt"}
    assert classify_offtarget_pair(reads, human_score=80, ercc_score=50, exact_support=support) is OffTargetClass.HUMAN_MT_UNIQUE
    assert classify_offtarget_pair(("ACGT" * 20,), human_score=80, ercc_score=80) is OffTargetClass.EXACT_TIE
    assert classify_offtarget_pair(("ACGT" * 20,), human_score=80, ercc_score=75) is OffTargetClass.AMBIGUOUS
    assert classify_offtarget_pair(("ACGT" * 20,), human_score=50, ercc_score=80) is OffTargetClass.ERCC_UNIQUE_MISASSIGNED


def test_low_complexity_and_raw_processed_classification() -> None:
    assert low_complexity_or_adapter(("A" * 100, "CG" * 50))
    assert not low_complexity_or_adapter(("ACGTGTCAGTCA" * 8, "TGCACAGTCAGT" * 8))
    normal = ("ACGTGTCAGTCA" * 8, "TGCACAGTCAGT" * 8)
    assert classify_preprocessing_effect(normal, normal, raw_supported=True, processed_supported=True) is PreprocessingCause.PREEXISTING_IN_RAW
    assert classify_preprocessing_effect(normal, normal, raw_supported=False, processed_supported=True) is PreprocessingCause.INTRODUCED_OR_EXPOSED_BY_TRIMMING
    assert classify_preprocessing_effect(None, normal, raw_supported=False, processed_supported=True) is PreprocessingCause.UNRESOLVED


def test_sample_purity_and_algorithmic_rates_have_separate_denominators() -> None:
    report = OffTargetRates(1_000_000, 1500, 1200, 20, 990_000, 100, 180)
    report.validate()
    assert report.sample_purity_rate == pytest.approx(0.0012)
    assert report.algorithmic_misassignment_rate == pytest.approx(20 / 990_000)
    assert report.ambiguous_rate == pytest.approx(0.00028)
    with pytest.raises(ValueError):
        replace(report, classified_fragments=1_000_001).validate()


def _candidate(run: str, mix: str, lane: str, *, flowcell: str = "AC0AYTACXX") -> ExternalRunCandidate:
    return ExternalRunCandidate(run, run, mix, "BGI", "Illumina HiSeq 2000", "1", lane, flowcell, "PAIRED", 100)


def test_holdout_selection_is_metadata_only_and_lexicographic() -> None:
    candidates = [
        _candidate("SRR4", "Mix2", "L04"), _candidate("SRR1", "Mix1", "L03"),
        _candidate("SRR3", "Mix2", "L03"), _candidate("SRR2", "Mix1", "L04"),
        _candidate("SRR0", "Mix1", "L00", flowcell="other"),
    ]
    selected = select_holdout_runs(candidates, training_runs=frozenset())
    assert [row.run_accession for row in selected] == ["SRR1", "SRR2", "SRR3", "SRR4"]


def test_historical_threshold_mutation_is_rejected() -> None:
    validate_preserved_failure_thresholds(
        sirv_median=0.25, sirv_p90=0.50, ercc_crossmapping=0.001,
    )
    with pytest.raises(ValueError, match="immutable"):
        validate_preserved_failure_thresholds(
            sirv_median=0.30, sirv_p90=0.50, ercc_crossmapping=0.001,
        )


def test_historical_preregistration_and_result_hashes_are_unchanged() -> None:
    import hashlib
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    expected = {
        "external-truth-preregistration.json": "5ba814f25ce1bb1ab872a3649761f87bcb593af7797458b378933d8015c22077",
        "external-truth-preregistration-v2.json": "d65570ad5d47bb99ad185e792ef1e1c9616016262189b1e24e84e43c59124794",
        "salmon-2.5.1-external-truth-validation-v2.json": "e89cf368d2f90d475fc0325469ef803ce04cfd5041fac56a9a6aa800b094a8bc",
        "ercc-crossmapping-holdout-preregistration.json": "baac95911880339535178da9d148344911438a58f51597a3ba4b4ca5febb0cf9",
    }
    for name, digest in expected.items():
        path = root / "docs" / "qualification" / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
