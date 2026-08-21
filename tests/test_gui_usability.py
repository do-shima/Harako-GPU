from __future__ import annotations

import time
from pathlib import Path

from streamlit.testing.v1 import AppTest

from harako_gpu.services import gui
from harako_gpu.ui import state
from harako_gpu.ui.components.message import MessageLevel
from harako_gpu.ui.labels import LABELS, assert_complete, text
from harako_gpu.ui.navigation import PAGES
from harako_gpu.ui.view_models import result_generation_summary


ROOT = Path(__file__).resolve().parents[1]


def test_every_page_has_bilingual_purpose_and_completion_copy() -> None:
    assert_complete()
    keys = {"Project": "project", "Samples": "samples", "Reference & capability": "reference",
            "Analysis": "analysis", "Review & prepare": "review", "Run": "run",
            "Results": "results", "Recovery & support": "recovery"}
    assert tuple(keys) == PAGES
    for language in ("ja", "en"):
        for page_key in keys.values():
            assert text(f"page.{page_key}.purpose", language).strip()
            assert text(f"page.{page_key}.complete", language).strip()


def test_bilingual_catalog_has_no_placeholder_or_claim_drift() -> None:
    assert set(LABELS["ja"]) == set(LABELS["en"])
    combined = " ".join(value for catalog in LABELS.values() for value in catalog.values()).lower()
    assert "todo" not in combined and "tbd" not in combined
    for language in ("ja", "en"):
        assert "GPU" in text("quant.copy", language)
        assert "BAM" in text("quant.copy", language)
        assert text("profile.secondary", language)


def test_warning_hierarchy_is_textual_and_has_five_distinct_levels() -> None:
    assert tuple(level.value for level in MessageLevel) == (
        "info", "limitation", "warning", "blocker", "failure")
    for language in ("ja", "en"):
        assert len({text(f"level.{level.value}", language) for level in MessageLevel}) == 5


def test_quant_only_results_make_generated_and_not_generated_explicit() -> None:
    artifacts = [
        {"role": "processed_fastq_r1", "state": "VALIDATED"},
        {"role": "matrix_gene_tpm", "state": "VALIDATED"},
        {"role": "self_contained_report", "state": "VALIDATED"},
        {"role": "genomic_bam", "state": "NOT_APPLICABLE"},
    ]
    result = result_generation_summary({"execution_route": "fastq_quantification_only"}, artifacts)
    assert "artifact.processed_fastq" in result["generated"]
    assert "artifact.gene_tpm" in result["generated"]
    assert "artifact.bam_bai" in result["not_generated"]
    assert "artifact.gpu_evidence" in result["not_generated"]


def test_bam_results_do_not_claim_route_level_absence() -> None:
    result = result_generation_summary(
        {"execution_route": "gpu_bam_alignment"},
        [{"role": "genomic_bam", "state": "VALIDATED"},
         {"role": "star_reads_per_gene", "state": "VALIDATED"}],
    )
    assert result["not_generated"] == ()
    assert "artifact.bam_bai" in result["generated"]
    assert "artifact.star_counts" in result["generated"]


def test_polling_preferences_are_draft_only_and_isolated() -> None:
    first, second = {}, {}
    state.initialize(first); state.initialize(second)
    first[state.AUTO_REFRESH] = False
    first[state.REFRESH_INTERVAL] = 5
    assert second[state.AUTO_REFRESH] is True
    assert second[state.REFRESH_INTERVAL] == 2
    assert state.AUTO_REFRESH not in state.draft_snapshot(first)
    assert state.REFRESH_INTERVAL not in state.draft_snapshot(first)


def test_app_initial_page_exposes_hierarchy_and_page_guidance() -> None:
    tested = AppTest.from_file(str(ROOT / "src/harako_gpu/ui/app.py")).run(timeout=10)
    assert not tested.exception
    assert any("reference-aware GUI" in value.value for value in tested.title)
    captions = " ".join(item.value for item in tested.caption)
    assert "Purpose of this page" in captions
    assert "Completion condition" in captions
    assert any("Current blocker" in item.value for item in tested.warning)


def test_japanese_initial_page_has_same_information_hierarchy() -> None:
    tested = AppTest.from_file(str(ROOT / "src/harako_gpu/ui/app.py")).run(timeout=10)
    tested.sidebar.selectbox[0].set_value("ja")
    tested.run(timeout=10)
    captions = " ".join(item.value for item in tested.caption)
    assert "このページの目的" in captions
    assert "完了条件" in captions
    assert any("現在のblocker" in item.value for item in tested.warning)


def test_fastq_scan_remains_bounded_for_1000_synthetic_files(tmp_path: Path) -> None:
    for number in range(500):
        for side in (1, 2):
            (tmp_path / f"sample{number:04d}_R{side}.fastq.gz").write_bytes(b"fixture")
    started = time.perf_counter()
    result = gui.scan_fastqs(str(tmp_path), layout="paired", library_type="U")
    elapsed = time.perf_counter() - started
    assert result["valid"] and result["file_count"] == 1000 and len(result["rows"]) == 500
    assert elapsed < 2.0


def test_acceptance_template_is_pending_and_contains_no_participants() -> None:
    import json
    path = ROOT / "docs/acceptance/local-user-acceptance-results-template.json"
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "PENDING_EXTERNAL_USERS"
    assert payload["participants"] == []
    assert payload["results"] == []
