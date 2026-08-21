from __future__ import annotations

import importlib.util
import random
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from harako_gpu.services.decoy_accounting import (
    DOMINANT_MARGIN,
    IdentifiabilityClass,
    IndexControlReport,
    LeakageMeasurement,
    PairedSequenceOracle,
    build_truth_v2_biological_report,
    diagnostic_mapping_argv,
    old_v1_aggregate_leakage,
    reverse_complement,
    validate_primary_decoy_gates,
    validate_v1_formula_limitations,
)


ROOT = Path(__file__).resolve().parents[1]


def _dna(seed: int, length: int) -> str:
    rng = random.Random(seed)
    return "".join(rng.choice("ACGT") for _ in range(length))


def _pair(sequence: str, start: int = 120, length: int = 220) -> tuple[str, str]:
    fragment = sequence[start:start + length]
    return reverse_complement(fragment[-100:]), fragment[:100]


def _oracle(transcript: str, decoy: str) -> PairedSequenceOracle:
    return PairedSequenceOracle({"tx": transcript}, {"decoy": decoy})


def _classify(transcript: str, decoy: str, *, start: int = 120):
    r1, r2 = _pair(decoy, start=start)
    return _oracle(transcript, decoy).classify(
        fragment_id="opaque", sample="sample", source_decoy="decoy",
        source_interval=(start, start + 220), r1=r1, r2=r2,
    )


def test_v1_aggregate_formula_reproduces_19_4_percent_without_read_attribution() -> None:
    assert old_v1_aggregate_leakage(
        zero_expression_mass=Decimal("582"), total_estimated_mass=Decimal("297582"),
        transcript_origin_fragments=297_000, generated_decoy_fragments=3_000,
    ) == Decimal("0.194")
    with pytest.raises(ValueError, match="cannot uniquely attribute"):
        validate_v1_formula_limitations(claims_read_level_attribution=True)


def test_oracle_distinguishes_exact_tie_unique_dominant_and_ambiguous() -> None:
    transcript = _dna(31, 700)
    exact = _classify(transcript, transcript)
    assert exact.identifiability_class is IdentifiabilityClass.DECOY_EXACT_TIE

    unique_decoy = list(transcript)
    for position in list(range(120, 136)) + list(range(240, 256)):
        unique_decoy[position] = "A" if unique_decoy[position] != "A" else "C"
    unique = _classify(transcript, "".join(unique_decoy))
    assert unique.identifiability_class is IdentifiabilityClass.DECOY_UNIQUE

    dominant_decoy = list(transcript)
    for position in range(125, 125 + DOMINANT_MARGIN + 1):
        dominant_decoy[position] = "A" if dominant_decoy[position] != "A" else "C"
    dominant = _classify(transcript, "".join(dominant_decoy))
    assert dominant.identifiability_class is IdentifiabilityClass.DECOY_DOMINANT

    ambiguous_decoy = list(transcript)
    ambiguous_decoy[125] = "A" if ambiguous_decoy[125] != "A" else "C"
    ambiguous = _classify(transcript, "".join(ambiguous_decoy))
    assert ambiguous.identifiability_class is IdentifiabilityClass.DECOY_AMBIGUOUS


def test_oracle_handles_isr_orientation_error_and_transcript_origin() -> None:
    transcript = _dna(43, 700)
    decoy = _dna(44, 700)
    r1, r2 = _pair(decoy)
    errored = list(r2)
    errored[7] = "A" if errored[7] != "A" else "C"
    evidence = _oracle(transcript, decoy).classify(
        fragment_id="opaque", sample="sample", source_decoy="decoy",
        source_interval=(120, 340), r1=r1, r2="".join(errored),
    )
    assert evidence.identifiability_class is IdentifiabilityClass.DECOY_UNIQUE
    transcript_evidence = _oracle(transcript, decoy).classify(
        fragment_id="opaque2", sample="sample", source_decoy="",
        source_interval=(120, 340), r1=r1, r2=r2, source_is_decoy=False,
    )
    assert transcript_evidence.identifiability_class is IdentifiabilityClass.NOT_DECOY_ORIGIN


def _measurement(category: IdentifiabilityClass, mass: str) -> LeakageMeasurement:
    return LeakageMeasurement(category, 20_000, Decimal(mass))


def test_primary_gate_keeps_absolute_one_percent_and_relative_ninety_percent() -> None:
    reports = [
        IndexControlReport(_measurement(category, "200"), _measurement(category, "2000"))
        for category in (IdentifiabilityClass.DECOY_UNIQUE, IdentifiabilityClass.DECOY_DOMINANT)
    ]
    validate_primary_decoy_gates(reports)
    assert reports[0].relative_reduction == Decimal("0.9")
    with pytest.raises(ValueError, match="DECOY_UNIQUE"):
        validate_primary_decoy_gates([
            replace(reports[0], decoy_aware=_measurement(IdentifiabilityClass.DECOY_UNIQUE, "200.0001")),
            reports[1],
        ])
    zero_control = IndexControlReport(
        _measurement(IdentifiabilityClass.DECOY_UNIQUE, "0"),
        _measurement(IdentifiabilityClass.DECOY_UNIQUE, "0"),
    )
    assert zero_control.relative_reduction == 0
    assert not zero_control.passed


def test_ambiguous_and_exact_tie_are_reported_but_never_gated() -> None:
    for category in (IdentifiabilityClass.DECOY_AMBIGUOUS, IdentifiabilityClass.DECOY_EXACT_TIE):
        assert _measurement(category, "20000").primary_gate is None


def test_keep_rad_is_diagnostic_only_and_product_argv_is_unchanged() -> None:
    product = (
        "salmon", "quant", "--deterministic", "--decoder", "serial", "--threads", "6",
        "--libType", "ISR", "--index", "/index", "-1", "/r1", "-2", "/r2", "-o", "/out",
    )
    assert diagnostic_mapping_argv(product, keep_rad=False) == product
    assert diagnostic_mapping_argv(product, keep_rad=True) == (*product, "--keepRad")
    assert "-a" not in product and all(";" not in value for value in product)


def test_truth_v2_design_is_versioned_and_does_not_write_v1(tmp_path: Path) -> None:
    script = ROOT / "scripts/generate_harako_truth_bulk_v2.py"
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("truth_v2", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.FIXTURE_ID == "harako_truth_bulk_v2_decoy_stratified"
    assert module.GENERATOR_VERSION == 2
    assert module.DIAGNOSTIC_FRAGMENTS >= 20_000
    decoys = module.stratified_decoys(module.transcriptome())
    assert decoys["decoy_exact_tie"] != next(
        row.sequence for row in module.transcriptome() if row.transcript_id == "tx_zero_03_1"
    )
    assert list(tmp_path.iterdir()) == []


def test_truth_v2_biology_excludes_exact_tie_mass_from_identifiable_zero_gate() -> None:
    transcripts = [
        {"transcript_id": "tx", "gene_id": "gene", "stratum": "unique_identifiable", "group_id": "gene"},
        {"transcript_id": "tx_zero_03_1", "gene_id": "zero_tie", "stratum": "zero_expression", "group_id": "zero_tie"},
        {"transcript_id": "zero_identifiable", "gene_id": "zero", "stratum": "zero_expression", "group_id": "zero"},
    ]
    samples = []
    quant = {}
    processed = {}
    mapped = {}
    for condition, truth in (("A", 100), ("B", 200)):
        for replicate in range(1, 4):
            sample = f"{condition}{replicate}"
            samples.append({
                "sample": sample, "condition": condition, "fragments": truth + 10,
                "transcript_counts": {"tx": truth, "tx_zero_03_1": 0, "zero_identifiable": 0},
            })
            quant[sample] = {
                "tx": Decimal(truth), "tx_zero_03_1": Decimal(10),
                "zero_identifiable": Decimal(0),
            }
            processed[sample] = truth + 10
            mapped[sample] = truth + 10
    report = build_truth_v2_biological_report(
        manifest={
            "main_samples": samples, "transcripts": transcripts,
            "zero_identifiable_transcripts": ["zero_identifiable"],
        },
        quant_by_sample=quant, processed_by_sample=processed, mapped_by_sample=mapped,
    )
    assert report.identifiable_zero_mass_fraction == 0
    assert report.unidentifiable_assignment_mass == 60
    assert report.passed
