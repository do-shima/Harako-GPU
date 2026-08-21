from __future__ import annotations

import math
from pathlib import Path
from dataclasses import replace
from decimal import Decimal

import pytest

from harako_gpu.services.external_truth_validation import (
    AggregateRelativeErrorMetrics,
    AbundanceMetrics,
    ExternalIndexIdentity,
    ExternalIndexRole,
    CrossMappingResult,
    ErccTruthRow,
    ExternalRepeatIdentity,
    ExternalRunCandidate,
    GateState,
    V1_PREREGISTRATION_SHA256,
    aggregate_relative_error_metrics,
    abundance_metrics,
    canonical_preregistration_sha256,
    concentration_metrics,
    equimolar_metrics,
    ercc_fold_change_metrics,
    normalized_mole_fractions,
    parse_ercc_truth,
    select_ercc_runs,
    sirv_expected_fractions,
    upper_fraction_ids,
    validate_download_url,
    validate_external_repeats,
    validate_secondary_ercc_truth,
    validate_v1_preregistration,
)


SHA = "a" * 64


def _candidate(run: str, mix: str, lane: str, *, library: str = "1", flowcell: str = "AC0") -> ExternalRunCandidate:
    return ExternalRunCandidate(run, run, mix, "BGI", "Illumina HiSeq 2000", library, lane, flowcell, "PAIRED", 100)


def test_ercc_selection_is_metadata_only_matched_and_lexicographic() -> None:
    candidates = [
        _candidate("SRR000004", "Mix2", "L02"), _candidate("SRR000001", "Mix1", "L01"),
        _candidate("SRR000003", "Mix2", "L01"), _candidate("SRR000002", "Mix1", "L02"),
        _candidate("SRR000000", "Mix1", "L00", library="2"),
    ]
    assert [row.run_accession for row in select_ercc_runs(candidates)] == [
        "SRR000001", "SRR000002", "SRR000003", "SRR000004",
    ]
    with pytest.raises(ValueError, match="matched"):
        select_ercc_runs(candidates[:2])


def _truth_text() -> str:
    header = "\t".join((
        "Re-sort ID", "ERCC ID", "subgroup", "concentration in Mix 1 (attomoles/ul)",
        "concentration in Mix 2 (attomoles/ul)", "expected fold-change ratio",
        "log2(Mix 1/Mix 2)",
    ))
    rows = []
    groups = (("A", "4", "2"), ("B", "1", "0"), ("C", "0.67", "-0.5849625"), ("D", "0.5", "-1"))
    for i in range(92):
        group, ratio, log2 = groups[i % 4]
        mix2 = Decimal(i + 1)
        mix1 = mix2 * Decimal(ratio)
        rows.append(f"{i+1}\tERCC-{i:05d}\t{group}\t{mix1}\t{mix2}\t{ratio}\t{log2}")
    return header + "\n" + "\n".join(rows) + "\n"


def test_official_ercc_parser_requires_all_92_ids_and_ratio_groups() -> None:
    rows = parse_ercc_truth(_truth_text())
    assert len(rows) == 92 and len({row.ercc_id for row in rows}) == 92
    with pytest.raises(ValueError, match="92"):
        parse_ercc_truth("\n".join(_truth_text().splitlines()[:-1]))
    validate_secondary_ercc_truth(rows, rows)
    with pytest.raises(ValueError, match="exact"):
        validate_secondary_ercc_truth(rows, rows[::-1])


def test_upper_75_percent_subset_is_frozen_by_truth_then_id() -> None:
    values = {f"x{i}": Decimal(i // 2) for i in range(8)}
    assert upper_fraction_ids(values, Decimal("0.75")) == ("x6", "x7", "x4", "x5", "x2", "x3")


def test_sirv_e0_zero_variance_is_undefined_not_pass() -> None:
    expected = {f"SIRV{i}": Decimal(1) for i in range(1, 69)}
    observed = {name: Decimal(index + 1) for index, name in enumerate(expected)}
    metrics = abundance_metrics(expected, observed)
    assert metrics.pearson is None and metrics.spearman is None
    assert metrics.transcript_gate is GateState.UNDEFINED_ZERO_VARIANCE


def test_sirv_abundance_gate_boundaries() -> None:
    passing = AbundanceMetrics(10, 0.90, 0.95, 0.90, 0.90, 0.75, 1.50)
    assert passing.transcript_gate is GateState.PASS
    assert replace(passing, p90_absolute_log2_error=1.5001).transcript_gate is GateState.FAIL


def _truth_rows() -> tuple[ErccTruthRow, ...]:
    groups = (("A", Decimal(2)), ("B", Decimal(0)), ("C", Decimal("-0.584962500721156")), ("D", Decimal(-1)))
    result = []
    for index in range(40):
        group, log2 = groups[index % 4]
        mix2 = Decimal(index + 10)
        mix1 = mix2 * (Decimal(2) ** log2)
        result.append(ErccTruthRow(f"ERCC-{index:05d}", group, mix1, mix2, mix1 / mix2, log2))
    return tuple(result)


def test_ercc_fold_change_gate_and_group_medians() -> None:
    truth = _truth_rows()
    mix1 = {row.ercc_id: row.mix1 for row in truth}
    mix2 = {row.ercc_id: row.mix2 for row in truth}
    report = ercc_fold_change_metrics(truth, mix1, mix2, tuple(mix1))
    assert report.passed and report.rmse < 1e-12
    mix1[truth[0].ercc_id] = mix2[truth[0].ercc_id] / 4
    assert not ercc_fold_change_metrics(truth, mix1, mix2, tuple(mix1)).passed


def _identity(**changes: object) -> ExternalRepeatIdentity:
    values: dict[str, object] = {
        "quant_sha256": SHA, "gene_quant_sha256": SHA,
        "scientific_metadata_sha256": SHA, "processed": 100, "mapped": 90,
        "feature_order": ("a", "b"), "zero_status": (False, True),
    }
    values.update(changes)
    return ExternalRepeatIdentity(**values)  # type: ignore[arg-type]


def test_external_repeat_gate_requires_byte_and_thread_identity() -> None:
    validate_external_repeats([_identity()] * 7, expected_fragments=100)
    with pytest.raises(ValueError, match="accounting"):
        validate_external_repeats([_identity(processed=99)], expected_fragments=100)
    with pytest.raises(ValueError, match="not byte"):
        validate_external_repeats([_identity(), _identity(quant_sha256="b" * 64)], expected_fragments=100)


def test_cross_mapping_warning_and_blocker_boundaries() -> None:
    assert not CrossMappingResult(10_000, 5, None, Decimal(0)).warning
    assert CrossMappingResult(10_000, 6, "x", Decimal(1)).warning
    assert not CrossMappingResult(10_000, 10, "x", Decimal(1)).blocked
    assert CrossMappingResult(10_000, 11, "x", Decimal(1)).blocked


def test_download_allowlist_rejects_credentials_queries_and_unknown_hosts() -> None:
    validate_download_url("https://ftp.sra.ebi.ac.uk/vol1/fastq/example.fastq.gz")
    for url in (
        "http://ftp.sra.ebi.ac.uk/file", "https://example.org/file",
        "https://user:secret@ftp.sra.ebi.ac.uk/file", "https://www.lexogen.com/file?token=x",
    ):
        with pytest.raises(ValueError):
            validate_download_url(url)


def test_preregistration_digest_is_canonical_and_result_independent() -> None:
    left = {"accessions": ["SRR1"], "threshold": 0.95}
    right = {"threshold": 0.95, "accessions": ["SRR1"]}
    assert canonical_preregistration_sha256(left) == canonical_preregistration_sha256(right)


def _sirv_mapping() -> dict[str, str]:
    return {f"SIRV{index:03d}": f"SIRV{(index - 1) % 7 + 1}" for index in range(1, 70)}


def test_v1_preregistration_is_immutable_by_raw_file_hash() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    validate_v1_preregistration(
        (repository_root / "docs/qualification/external-truth-preregistration.json").read_bytes()
    )
    original = b"historical-v1"
    # The production constant is asserted independently; monkeypatch-free validation
    # must reject every altered byte sequence used by this unit fixture.
    assert len(V1_PREREGISTRATION_SHA256) == 64
    with pytest.raises(ValueError, match="v1 was modified"):
        validate_v1_preregistration(original)


def test_sirv_e0_expected_transcript_and_gene_fractions() -> None:
    mapping = _sirv_mapping()
    transcripts, genes = sirv_expected_fractions(mapping)
    assert len(transcripts) == 69 and set(transcripts.values()) == {Decimal(1) / Decimal(69)}
    assert len(genes) == 7 and abs(sum(genes.values()) - Decimal(1)) < Decimal("1e-26")
    for gene, expected in genes.items():
        assert expected == Decimal(sum(value == gene for value in mapping.values())) / Decimal(69)
    with pytest.raises(ValueError, match="69"):
        sirv_expected_fractions(dict(list(mapping.items())[:-1]))


def test_sirv_e0_uses_tpm_mole_fractions_and_zero_is_infinite_error() -> None:
    expected, _ = sirv_expected_fractions(_sirv_mapping())
    observed = {name: Decimal(100) for name in expected}
    fractions = normalized_mole_fractions(tuple(expected), observed)
    report = equimolar_metrics(expected, fractions)
    assert report.transcript_passed()
    assert report.correlation_state is GateState.NOT_APPLICABLE_ZERO_VARIANCE
    missing = dict(fractions)
    missing[next(iter(missing))] = Decimal(0)
    missing = normalized_mole_fractions(tuple(expected), missing)
    report = equimolar_metrics(expected, missing)
    assert report.detected_features == 68
    assert math.isinf(max(
        abs(math.log2(float(missing[name] / expected[name]))) if missing[name] else math.inf
        for name in expected
    ))


def test_sirv_gene_and_equivalence_group_gate_boundaries() -> None:
    expected, genes = sirv_expected_fractions(_sirv_mapping())
    gene_report = equimolar_metrics(genes, genes)
    assert gene_report.gene_passed()
    groups = {name: f"eq-{index // 3}" for index, name in enumerate(expected)}
    aggregate = aggregate_relative_error_metrics(expected, expected, groups)
    assert aggregate == AggregateRelativeErrorMetrics(23, 0.0, 0.0)
    assert aggregate.passed


def test_external_index_roles_prevent_sirv_diagnostic_promotion() -> None:
    primary = ExternalIndexIdentity(
        ExternalIndexRole.SIRV_COMBINED_PRIMARY, "2.5.1", 31, 500_069, SHA, SHA,
        human_release="GENCODE 49 GRCh38.p14", decoy_aware=True,
    )
    primary.validate()
    assert primary.primary_truth_eligible
    diagnostic = ExternalIndexIdentity(
        ExternalIndexRole.SIRV_ONLY_DIAGNOSTIC, "2.5.1", 31, 69, SHA, SHA,
    )
    diagnostic.validate()
    assert not diagnostic.primary_truth_eligible
    with pytest.raises(ValueError, match="diagnostic"):
        replace(diagnostic, target_count=68).validate()


def test_ercc_concentration_gate_uses_frozen_subset_and_detected_values() -> None:
    truth = {f"ERCC-{index:05d}": Decimal(index + 1) for index in range(69)}
    observed = {name: value * Decimal(100) for name, value in truth.items()}
    report = concentration_metrics(truth, observed, tuple(truth))
    assert report.passed and report.detection_rate == 1.0
    observed[next(iter(observed))] = Decimal(0)
    assert concentration_metrics(truth, observed, tuple(truth)).passed
    for name in tuple(observed)[:4]:
        observed[name] = Decimal(0)
    assert not concentration_metrics(truth, observed, tuple(truth)).passed
