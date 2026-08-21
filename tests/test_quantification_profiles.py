from __future__ import annotations

from dataclasses import replace

import pytest

from harako_gpu.services.quantification_profiles import (
    AnalysisMode, AnalysisSeries, ModeSelection, ProcessedFastqPair, ProfileIndex,
    SALMON_1103_ID, SALMON_1121_ID, SALMON_251_ID, artifact_names,
    get_profile, salmon_argv, salmon_library_type_for_product,
    validate_comparable_indices, visible_profiles,
)


SHA = "a" * 64


def index(profile: str, version: str, image: str) -> ProfileIndex:
    return ProfileIndex(profile, f"{profile}-index", "/index", version, image, SHA, SHA, SHA, SHA, SHA)


def test_catalog_has_two_visible_profiles_and_hides_rejected_candidate() -> None:
    profiles = visible_profiles()
    assert [item.profile_id for item in profiles] == [SALMON_251_ID, SALMON_1103_ID]
    assert profiles[0].product_status == "recommended_internal_research_profile"
    assert profiles[0].display_name_ja == "再現性優先・推奨"
    assert profiles[1].product_status == "available_compatibility_profile"
    assert profiles[1].reproducibility_class == "bounded_numerical"
    with pytest.raises(ValueError, match="Hidden/rejected"):
        get_profile(SALMON_1121_ID)


def test_analysis_modes_fix_primary_secondary_and_downstream_boundary() -> None:
    assert ModeSelection.create(AnalysisMode.RECOMMENDED_ONLY).primary_profile_id == SALMON_251_ID
    assert ModeSelection.create(AnalysisMode.COMPATIBILITY_ONLY).primary_profile_id == SALMON_1103_ID
    with pytest.raises(ValueError, match="explicit primary"):
        ModeSelection.create(AnalysisMode.COMPARE_BOTH)
    selected = ModeSelection.create(AnalysisMode.COMPARE_BOTH, SALMON_1103_ID)
    assert selected.secondary_profile_id == SALMON_251_ID
    assert selected.downstream_primary_profile_id == SALMON_1103_ID


def test_version_specific_indices_require_same_biological_source() -> None:
    p25, p10 = get_profile(SALMON_251_ID), get_profile(SALMON_1103_ID)
    indices = (index(SALMON_251_ID, p25.version, p25.image_identity), index(SALMON_1103_ID, p10.version, p10.image_identity))
    validate_comparable_indices(indices)
    with pytest.raises(ValueError, match="biological reference"):
        validate_comparable_indices((indices[0], replace(indices[1], gtf_sha256="b" * 64)))
    with pytest.raises(ValueError, match="mismatch"):
        replace(indices[0], builder_version="1.10.3").validate()


def test_profile_argv_is_structured_and_deterministic_only_for_251() -> None:
    argv25 = salmon_argv(SALMON_251_ID, index="/i", gene_map="/g", r1="/r1", r2="/r2", output="/o", library_type="ISR")
    argv10 = salmon_argv(SALMON_1103_ID, index="/i", gene_map="/g", r1="/r1", r2="/r2", output="/o", library_type="ISR")
    assert argv25[:6] == ("salmon", "quant", "--deterministic", "--decoder", "serial", "--geneMap")
    assert "--deterministic" not in argv10
    assert "--threads" in argv25 and "6" in argv25
    with pytest.raises(ValueError, match="library type"):
        salmon_argv(SALMON_251_ID, index="/i", gene_map="/g", r1="/r1", r2="/r2", output="/o", library_type="A")


def test_paired_unstranded_profile_uses_salmon_iu_encoding() -> None:
    argv = salmon_argv(
        SALMON_251_ID, index="/i", gene_map="/g", r1="/r1", r2="/r2", output="/o", library_type="U",
    )
    assert argv[argv.index("--libType") + 1] == "IU"
    assert salmon_library_type_for_product("U") == "IU"
    assert salmon_library_type_for_product("ISF") == "ISF"
    with pytest.raises(ValueError, match="explicit"):
        salmon_library_type_for_product("A")


def test_fastq_identity_and_artifact_names_are_profile_specific() -> None:
    pair = ProcessedFastqPair("S1", "/r1", "/r2", SHA, SHA, 10, "fastp-v1", "1.0.1", ("fastp", "-i", "/r1"), "ISR")
    pair.validate()
    left, right = artifact_names(SALMON_251_ID), artifact_names(SALMON_1103_ID)
    assert left["transcript_tpm"] != right["transcript_tpm"]
    assert not any(value.endswith("/counts.tsv") or value.endswith("/tpm.tsv") for value in (*left.values(), *right.values()))


def test_analysis_series_identity_changes_with_profile_and_rejects_mixing() -> None:
    p25, p10 = get_profile(SALMON_251_ID), get_profile(SALMON_1103_ID)
    pair = ProcessedFastqPair("S1", "/r1", "/r2", SHA, SHA, 10, "fastp-v1", "1.0.1", ("fastp",), "ISR")
    idx25, idx10 = index(SALMON_251_ID, p25.version, p25.image_identity), index(SALMON_1103_ID, p10.version, p10.image_identity)
    series = AnalysisSeries("project", ModeSelection.create(AnalysisMode.COMPARE_BOTH, SALMON_251_ID), "ref", SHA, SHA, SHA,
        "ISR", "fastp-v1", (pair,), (idx25, idx10), {SALMON_251_ID: ("salmon",), SALMON_1103_ID: ("salmon",)},
        "UNAVAILABLE_NOT_GENERATED", "2026-08-17T00:00:00Z")
    first = series.analysis_series_id
    assert first == series.analysis_series_id
    changed = replace(series, selection=ModeSelection.create(AnalysisMode.COMPARE_BOTH, SALMON_1103_ID), parent_series_id=first)
    assert changed.analysis_series_id != first
    with pytest.raises(ValueError, match="Mixed library"):
        replace(series, samples=(replace(pair, library_type="ISF"),)).validate()
