from __future__ import annotations

import math

import pytest

from harako_gpu.services.concordance import (
    DescriptiveTier, compare_abundance, compare_profile_runtimes, compare_star_salmon_counts,
    descriptive_tier, parse_gtf_annotations, parse_quant_sf, render_summary_html,
    stratified_concordance, stratified_orthogonal_concordance,
)
from harako_gpu.services.quantification_profiles import SALMON_1103_ID, SALMON_251_ID, get_profile


QUANT = "Name\tLength\tEffectiveLength\tTPM\tNumReads\nA\t100\t80\t10\t5\nB\t200\t150\t0\t0\n"


def test_quant_parser_requires_exact_schema_unique_finite_nonnegative() -> None:
    assert [row.feature_id for row in parse_quant_sf(QUANT)] == ["A", "B"]
    with pytest.raises(ValueError, match="duplicate"):
        parse_quant_sf(QUANT + "A\t1\t1\t1\t1\n")
    with pytest.raises(ValueError, match="non-finite"):
        parse_quant_sf(QUANT.replace("10\t5", "nan\t5"))
    with pytest.raises(ValueError, match="universe"):
        parse_quant_sf(QUANT, expected_ids=("A",))


def test_concordance_reports_unmatched_detection_ranks_and_sensitive_rules() -> None:
    result = compare_abundance({"A": 10, "B": 0, "L": 2}, {"A": 4, "B": 2, "R": 3})
    assert result.left_only == ("L",) and result.right_only == ("R",)
    assert result.zero_transitions == 1
    assert result.high_priority_zero_transitions == 1
    assert result.sensitive_features[0].category == "high_priority"
    assert result.top50_overlap == pytest.approx(2 / 3)


def test_numreads_and_runtime_comparison_are_descriptive() -> None:
    counts = compare_abundance({"A": 10.25, "B": 0.0}, {"A": 10.0, "B": 0.5})
    assert counts.common_features == 2 and counts.zero_transitions == 1
    runtime = compare_profile_runtimes({
        SALMON_251_ID: {"wall_seconds": 4.0, "fragments_per_second": 250.0, "execution_order": 1},
        SALMON_1103_ID: {"wall_seconds": 6.0, "fragments_per_second": 166.6, "execution_order": 2},
    }, {SALMON_251_ID: "2.5.1", SALMON_1103_ID: "1.10.3"})
    assert runtime["salmon_1_10_3_to_2_5_1_wall_time_ratio"] == 1.5


def test_descriptive_tier_boundaries_are_not_pass_fail() -> None:
    assert descriptive_tier(gene_spearman=.99, top100_overlap=.90, high_zero_fraction=.005) is DescriptiveTier.A
    assert descriptive_tier(gene_spearman=.95, top100_overlap=.75, high_zero_fraction=.02) is DescriptiveTier.B
    assert descriptive_tier(gene_spearman=.949, top100_overlap=1, high_zero_fraction=0) is DescriptiveTier.C


def test_star_comparison_uses_cpm_count_space_not_tpm() -> None:
    result = compare_star_salmon_counts({"A": 10, "B": 20, "C": 0}, {"A": 5.0, "B": 10.0, "D": 1.0})
    assert result.common_genes == 2
    assert result.spearman == pytest.approx(1)


def test_report_is_self_contained_bilingual_and_avoids_correctness_claims() -> None:
    result = compare_abundance({"A": 10, "B": 1}, {"A": 9, "B": 1.1})
    page = render_summary_html(analysis_series_id="series", project_id="p",
        primary_profile=get_profile(SALMON_251_ID).as_dict(), secondary_profile=get_profile(SALMON_1103_ID).as_dict(),
        reference_pack_id="ref", library_type="ISR", processed_fastq_identity="fastq",
        transcript=result, gene=result, star_status="UNAVAILABLE_NOT_GENERATED")
    assert "差は必ずしもerror" in page and "do not necessarily mean error" in page
    assert "Primary profileだけ" in page and "Research use only" in page
    assert "<script" not in page and "cdn" not in page.lower() and "http://" not in page and "https://" not in page
    assert "incorrect" not in page.lower()


def test_gtf_annotation_strata_preserve_unknown_and_fixed_gene_span() -> None:
    gtf = 'chrM\tx\ttranscript\t2\t101\t.\t+\t.\tgene_id "A"; transcript_id "T1"; gene_biotype "rRNA";\n'
    annotations = parse_gtf_annotations(gtf)
    assert annotations["A"]["gene_length_span"] == 100
    assert annotations["A"]["mitochondrial"] and annotations["A"]["ribosomal"]
    rows = stratified_concordance({"A": 2, "B": 1}, {"A": 1, "B": 1}, annotations)
    assert {row["stratum"] for row in rows} == {"rRNA|single_transcript|mitochondrial|ribosomal", "unknown|unknown"}
    star_rows = stratified_orthogonal_concordance({"A": 10, "B": 5}, {"A": 5, "B": 5}, annotations)
    assert {row["stratum"] for row in star_rows} == {"rRNA|single_transcript|mitochondrial|ribosomal", "unknown|unknown"}
