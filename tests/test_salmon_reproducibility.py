from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from harako_gpu.services.salmon_reproducibility import (
    BamScientificIdentity,
    ReproducibilityClass,
    TpmStratum,
    aggregate_by_gene,
    bam_scientific_checksum,
    build_quantification_identity,
    canonical_numerical_digest,
    classify_reproducibility,
    compare_bam_identities,
    compare_expression_tables,
    compare_quant_tables,
    detect_deterministic_capability,
    header_normalized_sha256,
    inspect_sam_records,
    parse_quant_sf,
    parse_salmon_metadata,
    parse_transcript_gene_map,
    salmon_quant_argv,
    tpm_stratum,
    validate_bam_identity,
)


FIXTURES = Path(__file__).parent / "fixtures"


def _quant(name: str):
    return parse_quant_sf((FIXTURES / name).read_text(encoding="utf-8"))


def test_quant_parser_and_canonical_numerical_digest_ignore_float_serialization() -> None:
    baseline = _quant("salmon_quant_baseline.sf")
    same_values = parse_quant_sf(
        (FIXTURES / "salmon_quant_baseline.sf")
        .read_text(encoding="utf-8")
        .replace("80.000", "80")
        .replace("0.000000", "0")
        .replace("100.000", "100")
    )
    assert baseline.ids == ("tx_zero", "tx_low", "tx_mid", "tx_high")
    assert canonical_numerical_digest(baseline) == canonical_numerical_digest(same_values)


def test_quant_parser_rejects_malformed_missing_and_duplicate_transcripts() -> None:
    with pytest.raises(ValueError, match="header"):
        parse_quant_sf("Name\tTPM\nx\t1\n")
    with pytest.raises(ValueError, match="Duplicate"):
        parse_quant_sf(
            "Name\tLength\tEffectiveLength\tTPM\tNumReads\n"
            "x\t10\t9\t1\t1\nx\t10\t9\t1\t1\n"
        )
    with pytest.raises(ValueError, match="missing=\\['tx_missing'\\]"):
        parse_quant_sf(
            (FIXTURES / "salmon_quant_baseline.sf").read_text(encoding="utf-8"),
            expected_ids={"tx_zero", "tx_low", "tx_mid", "tx_high", "tx_missing"},
        )
    with pytest.raises(ValueError, match="Invalid TPM"):
        parse_quant_sf(
            "Name\tLength\tEffectiveLength\tTPM\tNumReads\nx\t10\t9\tNaN\t1\n"
        )


def test_tpm_strata_have_explicit_boundaries() -> None:
    assert tpm_stratum(Decimal(0)) is TpmStratum.ZERO
    assert tpm_stratum(Decimal("0.099999")) is TpmStratum.LOW
    assert tpm_stratum(Decimal("0.1")) is TpmStratum.MIDDLE
    assert tpm_stratum(Decimal("0.999999")) is TpmStratum.MIDDLE
    assert tpm_stratum(Decimal("1")) is TpmStratum.HIGH


def test_numerical_comparator_captures_strata_and_zero_transition() -> None:
    baseline = _quant("salmon_quant_baseline.sf")
    candidate = _quant("salmon_quant_candidate.sf")
    comparison = compare_quant_tables(baseline, candidate)
    assert comparison.id_set_equal
    assert comparison.row_order_equal
    assert comparison.num_reads_max_absolute_difference == 0
    assert comparison.effective_length_max_absolute_difference == Decimal("0.08")
    assert comparison.strata[TpmStratum.MIDDLE].max_absolute_difference == Decimal("0.0005")
    assert comparison.strata[TpmStratum.HIGH].max_relative_difference == Decimal("0.0005")
    assert comparison.zero_nonzero_transition_ids == ()

    transitioned = parse_quant_sf(
        (FIXTURES / "salmon_quant_candidate.sf")
        .read_text(encoding="utf-8")
        .replace("tx_zero\t100\t80\t0\t0", "tx_zero\t100\t80\t0.001\t0")
    )
    assert compare_quant_tables(baseline, transitioned).zero_nonzero_transition_ids == ("tx_zero",)


def test_gene_aggregation_and_comparison() -> None:
    mapping = parse_transcript_gene_map(
        'chr\tsrc\texon\t1\t2\t.\t+\t.\tgene_id "g1"; transcript_id "tx_zero";\n'
        'chr\tsrc\texon\t3\t4\t.\t+\t.\tgene_id "g1"; transcript_id "tx_low";\n'
        'chr\tsrc\texon\t5\t6\t.\t+\t.\tgene_id "g2"; transcript_id "tx_mid";\n'
        'chr\tsrc\texon\t7\t8\t.\t+\t.\tgene_id "g3"; transcript_id "tx_high";\n'
    )
    baseline = aggregate_by_gene(_quant("salmon_quant_baseline.sf"), mapping)
    candidate = aggregate_by_gene(_quant("salmon_quant_candidate.sf"), mapping)
    comparison = compare_expression_tables(baseline, candidate)
    assert baseline.ids == ("g1", "g2", "g3")
    assert comparison.id_set_equal
    assert comparison.num_reads_max_absolute_difference == 0
    assert comparison.strata[TpmStratum.HIGH].max_relative_difference == Decimal("0.0005")


def test_tolerance_boundaries_and_material_variability() -> None:
    baseline = _quant("salmon_quant_baseline.sf")
    candidate = _quant("salmon_quant_candidate.sf")
    mapping = {row.transcript_id: f"gene_{row.transcript_id}" for row in baseline.rows}
    transcript = compare_quant_tables(baseline, candidate)
    gene = compare_expression_tables(
        aggregate_by_gene(baseline, mapping),
        aggregate_by_gene(candidate, mapping),
    )
    assert classify_reproducibility(
        quant_byte_identical=False,
        transcript=transcript,
        gene=gene,
        metadata_exact=True,
    ) is ReproducibilityClass.BOUNDED_NUMERICAL
    assert classify_reproducibility(
        quant_byte_identical=False,
        transcript=transcript,
        gene=gene,
        metadata_exact=False,
    ) is ReproducibilityClass.MATERIAL_VARIABILITY

    too_large = parse_quant_sf(
        (FIXTURES / "salmon_quant_candidate.sf")
        .read_text(encoding="utf-8")
        .replace("380.08", "380.1001")
    )
    material = compare_quant_tables(baseline, too_large)
    assert classify_reproducibility(
        quant_byte_identical=False,
        transcript=material,
        gene=compare_expression_tables(
            aggregate_by_gene(baseline, mapping),
            aggregate_by_gene(too_large, mapping),
        ),
        metadata_exact=True,
    ) is ReproducibilityClass.MATERIAL_VARIABILITY

    exact = compare_quant_tables(baseline, baseline)
    exact_gene = compare_expression_tables(
        aggregate_by_gene(baseline, mapping),
        aggregate_by_gene(baseline, mapping),
    )
    assert classify_reproducibility(
        quant_byte_identical=True,
        transcript=exact,
        gene=exact_gene,
        metadata_exact=True,
    ) is ReproducibilityClass.EXACT

    serialization_only = parse_quant_sf(
        (FIXTURES / "salmon_quant_baseline.sf")
        .read_text(encoding="utf-8")
        .replace("10.000", "9.999")
        .replace("100.000", "100.001")
    )
    serialization_comparison = compare_quant_tables(baseline, serialization_only)
    serialization_gene = compare_expression_tables(
        aggregate_by_gene(baseline, mapping),
        aggregate_by_gene(serialization_only, mapping),
    )
    assert classify_reproducibility(
        quant_byte_identical=False,
        transcript=serialization_comparison,
        gene=serialization_gene,
        metadata_exact=True,
    ) is ReproducibilityClass.BOUNDED_NUMERICAL

    beyond_serialization = parse_quant_sf(
        (FIXTURES / "salmon_quant_baseline.sf")
        .read_text(encoding="utf-8")
        .replace("10.000", "9.998")
        .replace("100.000", "100.002")
    )
    assert classify_reproducibility(
        quant_byte_identical=False,
        transcript=compare_quant_tables(baseline, beyond_serialization),
        gene=compare_expression_tables(
            aggregate_by_gene(baseline, mapping),
            aggregate_by_gene(beyond_serialization, mapping),
        ),
        metadata_exact=True,
    ) is ReproducibilityClass.MATERIAL_VARIABILITY


def test_metadata_identity_requires_alignment_fragment_fields() -> None:
    identity = parse_salmon_metadata((FIXTURES / "salmon_meta_info.json").read_text(encoding="utf-8"))
    assert identity.salmon_version == "1.10.3"
    assert identity.mapping_type == "alignment"
    assert identity.library_types == ("ISR",)
    assert identity.num_processed == identity.num_mapped == 33024
    with pytest.raises(ValueError, match="missing fields"):
        parse_salmon_metadata('{"salmon_version": "1.10.3"}')


def test_header_normalized_identity_removes_only_volatile_command_text() -> None:
    first = (
        "@HD\tVN:1.6\tSO:coordinate\n"
        "@SQ\tSN:chr1\tLN:100\n"
        "@PG\tID:pbrun\tPN:pbrun\tVN:4.6.0-1\tCL:--out /run-a\n"
        "@CO\tuser=/home/alice at 2026-01-01\n"
    )
    second = first.replace("/run-a", "/run-b").replace("alice", "bob")
    assert header_normalized_sha256(first) == header_normalized_sha256(second)
    assert header_normalized_sha256(first) != header_normalized_sha256(
        second.replace("LN:100", "LN:101")
    )


def test_record_multiset_and_order_identity_are_distinct() -> None:
    record_a = "q1\t99\tchr1\t1\t60\t10M\t=\t20\t29\tAAAAAAAAAA\tFFFFFFFFFF\tNH:i:1\tHI:i:1\n"
    record_b = "q1\t147\tchr1\t20\t60\t10M\t=\t1\t-29\tTTTTTTTTTT\tFFFFFFFFFF\tHI:i:1\tNH:i:1\n"
    forward = inspect_sam_records([record_a, record_b])
    reversed_order = inspect_sam_records([record_b, record_a])
    assert forward.record_multiset_sha256 == reversed_order.record_multiset_sha256
    assert forward.record_order_sha256 != reversed_order.record_order_sha256
    assert forward.unique_qname_count == 1
    assert forward.qname_group_count == 1
    assert forward.tag_counts == {"HI": 2, "NH": 2}

    digest = "a" * 64
    baseline = BamScientificIdentity(digest, digest, forward.record_multiset_sha256, forward.record_order_sha256, 2)
    candidate = replace(
        baseline,
        byte_sha256="b" * 64,
        record_order_sha256=reversed_order.record_order_sha256,
    )
    comparison = compare_bam_identities(baseline, candidate)
    assert not comparison.byte_identical
    assert comparison.header_identical
    assert comparison.record_multiset_identical
    assert not comparison.record_order_identical
    assert bam_scientific_checksum(baseline) != bam_scientific_checksum(candidate)
    validate_bam_identity(candidate)


def test_quantification_identity_records_pinned_backend_and_numerical_digest() -> None:
    digest = "a" * 64
    bam = BamScientificIdentity(digest, digest, digest, digest, 73886)
    quant_path = FIXTURES / "salmon_quant_baseline.sf"
    quant_bytes = quant_path.read_bytes()
    identity = build_quantification_identity(
        bam_identity=bam,
        transcript_fasta_sha256="b" * 64,
        quant_sf_bytes=quant_bytes,
        quant_table=parse_quant_sf(quant_bytes.decode("utf-8")),
        alignments="/inputs/transcriptome.bam",
        transcript_fasta="/inputs/transcriptome.fasta",
        gene_map="/inputs/gene_map.gtf",
        output="WT_REP1",
        threads=6,
        reproducibility_class=ReproducibilityClass.BOUNDED_NUMERICAL,
    )
    assert identity.salmon_version == "1.10.3"
    assert identity.image_digest.startswith("sha256:")
    assert identity.thread_count == 6
    assert identity.command_argv[0:2] == ("salmon", "quant")
    assert identity.quant_sf_sha256 != identity.canonical_numerical_digest
    assert identity.tolerance_schema_version == 1


def test_qname_grouping_detects_split_groups() -> None:
    records = [
        "q1\t0\tchr1\t1\t60\t1M\t*\t0\t0\tA\tF\n",
        "q2\t0\tchr1\t2\t60\t1M\t*\t0\t0\tA\tF\n",
        "q1\t0\tchr1\t3\t60\t1M\t*\t0\t0\tA\tF\n",
    ]
    inventory = inspect_sam_records(records)
    assert not inventory.qname_groups_contiguous
    assert inventory.unique_qname_count == 2
    assert inventory.qname_group_count == 3
    assert inventory.split_qname_count == 1


def test_deterministic_capability_probe_does_not_invent_support() -> None:
    unavailable = detect_deterministic_capability(
        "alignment-based mode\n  --seqBias\n  --gcBias\n  --seed <int>\n"
    )
    assert unavailable.deterministic_option is None
    assert unavailable.seed_options == ("--seed",)
    assert unavailable.alignment_mode_help
    available = detect_deterministic_capability("alignment mode\n  --deterministic\n")
    assert available.deterministic_option == "--deterministic"


def test_salmon_command_is_structured_and_has_no_shell_eval_surface() -> None:
    argv = salmon_quant_argv(
        alignments="/inputs/frozen bam.bam",
        transcript_fasta="/inputs/transcripts.fa",
        gene_map="/inputs/genes.gtf",
        output="/outputs/run-1",
        threads=6,
    )
    assert argv[0:2] == ("salmon", "quant")
    assert argv[argv.index("--threads") + 1] == "6"
    assert "/inputs/frozen bam.bam" in argv
    assert "--deterministic" not in argv
    assert "eval" not in argv
    with pytest.raises(ValueError, match="Unsupported"):
        salmon_quant_argv(
            alignments="a",
            transcript_fasta="t",
            gene_map="g",
            output="o",
            threads=12,
        )
