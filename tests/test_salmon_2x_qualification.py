from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from harako_gpu.services.independent_fastq_salmon import BAM_SALMON_PROCESS, FASTQ_SALMON_PROCESS
from harako_gpu.services.salmon_2x_qualification import (
    BASE_IMAGE_DIGEST,
    CANDIDATE_ASSET_SHA256,
    CANDIDATE_LOCAL_IMAGE,
    CANDIDATE_SOURCE_ARCHIVE_SHA256,
    CANDIDATE_SOURCE_COMMIT,
    CANDIDATE_VERSION,
    SALMON_INDEX_PROCESS,
    AccuracyVector,
    CandidateImageIdentity,
    CandidateIndexIdentity,
    CandidateStatus,
    ExactRunIdentity,
    TruthAccuracyReport,
    accuracy_vector,
    build_truth_accuracy_report,
    candidate_nfcore_override,
    deterministic_mapping_argv,
    validate_asset_sha256,
    validate_deterministic_argv,
    validate_exact_repeats,
    validate_source_archive_sha256,
)
from harako_gpu.services.salmon_reproducibility import (
    QuantRow,
    QuantTable,
    SalmonMetadataIdentity,
)


SHA = "a" * 64
IMAGE_ID = "sha256:" + "b" * 64
ROOT = Path(__file__).parents[1]


def _index() -> CandidateIndexIdentity:
    blank = CandidateIndexIdentity(
        salmon_index_id="", index_builder_version=CANDIDATE_VERSION,
        index_builder_image_id=IMAGE_ID, transcript_fasta_sha256=SHA,
        genome_fasta_sha256=SHA, gentrome_sha256=SHA, decoys_sha256=SHA,
        kmer_size=31, index_inventory_sha256=SHA,
    )
    return replace(blank, salmon_index_id=blank.expected_index_id)


def _run(**overrides: object) -> ExactRunIdentity:
    values: dict[str, object] = {
        "quant_sf_sha256": SHA, "gene_quant_sha256": SHA,
        "canonical_numerical_digest": SHA, "scientific_meta_sha256": SHA,
        "num_processed": 50_000, "num_mapped": 49_000,
    }
    values.update(overrides)
    return ExactRunIdentity(**values)  # type: ignore[arg-type]


def test_supply_chain_identity_is_exactly_pinned() -> None:
    assert CANDIDATE_VERSION == "2.5.1"
    assert CANDIDATE_SOURCE_COMMIT == "c360459bbf16e649a5c10c097e59f3c72e6b2e3c"
    assert BASE_IMAGE_DIGEST.startswith("sha256:")
    validate_asset_sha256(CANDIDATE_ASSET_SHA256)
    validate_source_archive_sha256(CANDIDATE_SOURCE_ARCHIVE_SHA256)
    with pytest.raises(ValueError, match="asset SHA"):
        validate_asset_sha256(SHA)
    with pytest.raises(ValueError, match="source archive"):
        validate_source_archive_sha256(SHA)


def test_candidate_image_and_committed_manifest_are_fail_closed() -> None:
    identity = CandidateImageIdentity(CANDIDATE_LOCAL_IMAGE, IMAGE_ID, IMAGE_ID, SHA, "salmon 2.5.1")
    identity.validate()
    with pytest.raises(ValueError, match="did not report"):
        replace(identity, salmon_version_output="salmon 1.12.1").validate()
    manifest = json.loads((ROOT / "containers/salmon-2.5.1-qualification/manifest.json").read_text())
    assert manifest["candidate_version"] == CANDIDATE_VERSION
    assert manifest["binary_sha256"] == CANDIDATE_ASSET_SHA256
    assert manifest["source_archive_sha256"] == CANDIDATE_SOURCE_ARCHIVE_SHA256
    assert manifest["dockerfile_sha256"] == hashlib.sha256(
        (ROOT / "containers/salmon-2.5.1-qualification/Dockerfile").read_bytes()
    ).hexdigest()
    assert manifest["published"] is False and manifest["default_backend"] is False


def test_2x_index_rejects_every_version_mismatch() -> None:
    identity = _index()
    identity.validate()
    for version in ("1.10.3", "1.12.1", "unknown"):
        with pytest.raises(ValueError, match="requires an index"):
            identity.validate(salmon_version=version)
    with pytest.raises(ValueError, match="requires an index"):
        replace(identity, index_builder_version="1.12.1").validate()
    with pytest.raises(ValueError, match="PISCEM"):
        replace(identity, index_format="legacy-pufferfish").validate()


def test_deterministic_command_is_structured_serial_fastq_only() -> None:
    argv = deterministic_mapping_argv(index="idx", gene_map="g.gtf", r1="r1", r2="r2", output="out")
    validate_deterministic_argv(argv)
    assert argv == (
        "salmon", "quant", "--deterministic", "--decoder", "serial", "--geneMap", "g.gtf",
        "--threads", "6", "--libType=ISR", "--index", "idx", "-1", "r1", "-2", "r2",
        "-o", "out",
    )
    assert "-a" not in argv and not any("eval" in token or ";" in token for token in argv)
    for token in ("-a", "--sketch", "--seqBias"):
        with pytest.raises(ValueError):
            validate_deterministic_argv((*argv, token))
    with pytest.raises(TypeError):
        deterministic_mapping_argv(index="i", gene_map="g", r1="1", r2="2", output="o", extra="x")  # type: ignore[call-arg]


def test_exact_repeat_gate_detects_threads_partial_counts_and_rad_truncation() -> None:
    validate_exact_repeats([_run()] * 50, expected_fragments=50_000)
    with pytest.raises(ValueError, match="absolute input"):
        validate_exact_repeats([_run(num_processed=49_999)], expected_fragments=50_000)
    with pytest.raises(ValueError, match="Partial"):
        validate_exact_repeats([_run(partial_rad_signature=True)], expected_fragments=50_000)
    with pytest.raises(ValueError, match="not exact"):
        validate_exact_repeats([_run(), _run(quant_sf_sha256="c" * 64)], expected_fragments=50_000)


def test_truth_gate_boundaries_and_accuracy_calculation() -> None:
    vector = accuracy_vector({"a": 100, "b": 200, "c": 400}, {
        "a": Decimal("100"), "b": Decimal("200"), "c": Decimal("400"),
    })
    assert vector.pearson == vector.spearman == 1
    assert vector.p95_absolute_percentage_error == 0
    passing = TruthAccuracyReport(True, True, 0, vector, vector, 0.05, 0.005, 0, 0.01, 1.0, 0.25, 0.95)
    assert passing.passed
    assert not replace(passing, decoy_leakage_fraction=0.010001).passed
    assert not replace(passing, fold_change_direction_accuracy=0.99).passed


def test_truth_report_rejects_decoy_leakage_despite_exact_expression() -> None:
    transcripts = [
        {"transcript_id": "tx", "gene_id": "gene", "stratum": "unique_identifiable", "group_id": "gene"},
        {"transcript_id": "zero", "gene_id": "zero_gene", "stratum": "zero_expression", "group_id": "zero_gene"},
    ]
    samples = []
    quant = {}
    metadata = {}
    for condition, truth in (("A", 100), ("B", 200)):
        for replicate in range(1, 4):
            sample = f"{condition}{replicate}"
            samples.append({
                "sample": sample, "condition": condition, "fragments": truth + 1,
                "transcript_origin_fragments": truth, "decoy_origin_fragments": 1,
                "transcript_counts": {"tx": truth, "zero": 0},
            })
            quant[sample] = QuantTable((
                QuantRow("tx", 1000, Decimal(800), Decimal(999000), Decimal(truth)),
                QuantRow("zero", 1000, Decimal(800), Decimal(1000), Decimal(1)),
                QuantRow("decoy_01", 1000, Decimal(800), Decimal(0), Decimal(0)),
            ))
            metadata[sample] = SalmonMetadataIdentity(
                "2.5.1", "mapping", ("ISR",), truth + 1, truth + 1, 3, False, False
            )
    report = build_truth_accuracy_report(
        manifest={"transcripts": transcripts, "samples": samples, "decoy_count": 1},
        quant_by_sample=quant, metadata_by_sample=metadata,
    )
    assert report.fragment_accounting_exact
    assert report.unique_transcripts.pearson == 1
    assert report.decoy_leakage_fraction == 1
    assert not report.passed


def test_truth_generator_design_and_counts_are_deterministic() -> None:
    path = ROOT / "scripts/generate_harako_truth_bulk_v1.py"
    spec = importlib.util.spec_from_file_location("harako_truth_generator", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    left = module.transcriptome()
    right = module.transcriptome()
    assert left == right
    assert len(left) >= 40 and len({row.gene_id for row in left}) >= 20
    assert sum(row.weight_a == row.weight_b == 0 for row in left) >= 8
    assert len(module.decoys(left)) >= 4
    counts = module.sample_counts(left, "A")
    assert sum(counts.values()) == module.FRAGMENTS_PER_SAMPLE - module.DECOY_FRAGMENTS_PER_SAMPLE


def test_nfcore_override_is_precise_and_only_emitted_after_truth_gate() -> None:
    with pytest.raises(ValueError, match="forbidden"):
        candidate_nfcore_override(image_id=IMAGE_ID, status=CandidateStatus.DIRECT_GATES_PASSED)
    fragment = candidate_nfcore_override(image_id=IMAGE_ID, status=CandidateStatus.CANDIDATE_QUALIFIED)
    assert f"withName: '{SALMON_INDEX_PROCESS}'" in fragment
    assert f"withName: '{FASTQ_SALMON_PROCESS}'" in fragment
    assert BAM_SALMON_PROCESS not in fragment
    assert "--deterministic --decoder serial" in fragment
    assert fragment.count("container =") == 2
    assert "Parabricks" not in fragment and "MULTIQC" not in fragment
