from __future__ import annotations

import ast
import json
import threading
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from typer.testing import CliRunner

from harako_gpu.adapters.filesystem import atomic_write_json
from harako_gpu.adapters.gui_launcher import controller_argv, streamlit_argv
from harako_gpu.commands.root import app
from harako_gpu.services import gui
from harako_gpu.core.contracts import QualificationDebugMode
from harako_gpu.ui import state
from harako_gpu.ui.labels import LABELS, assert_complete, page_label, text
from harako_gpu.ui.navigation import PAGES, access_map
from harako_gpu.ui.view_models import capability_view, stage_progress


ROOT = Path(__file__).resolve().parents[1]


def test_streamlit_dependency_is_exactly_pinned() -> None:
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"streamlit==1.60.0"' in project
    assert "streamlit>=\"" not in project


def test_label_catalog_is_complete_and_claims_match() -> None:
    assert_complete()
    assert set(LABELS["ja"]) == set(LABELS["en"])
    assert "GPUは使用しません" in text("quant.copy", "ja")
    assert "GPU was not used" in text("quant.copy", "en")
    assert "誤り" in text("compare.copy", "ja")
    assert "wrong" in text("compare.copy", "en")
    assert page_label("Samples", "ja") == "サンプル"
    combined = " ".join(value for catalog in LABELS.values() for value in catalog.values()).lower()
    for forbidden in ("fully gpu", "gpu quantification", "scientifically guaranteed", "clinical grade"):
        assert forbidden not in combined


def test_session_defaults_are_isolated_and_contain_no_user_identity() -> None:
    first, second = {}, {}
    state.initialize(first); state.initialize(second)
    first[state.SAMPLES].append({"sample": "changed"})
    assert second[state.SAMPLES] == []
    assert "/home/do" not in repr(state.DEFAULTS)
    assert "approval_hash" not in state.DEFAULTS


def test_navigation_is_fixed_and_gated() -> None:
    assert PAGES == ("Project", "Samples", "Reference & capability", "Analysis",
                     "Review & prepare", "Run", "Results", "Recovery & support")
    gates = access_map({})
    assert gates["Project"].enabled and not gates["Samples"].enabled
    gates = access_map({"project_slug": "p", "current_run_directory": "/run"},
                       capability_available=True, samples_valid=True)
    assert all(item.enabled for item in gates.values())


def test_capability_view_does_not_recalculate_science() -> None:
    source = {"status": "UNSUPPORTED_HOST_MEMORY", "gpu_used": True,
              "bam_generated": True, "explanation": "observed host RAM envelope"}
    value = capability_view(source)
    assert not value["available"] and value["label_key"] == "unavailable"
    assert value["gpu_used"] and value["bam_generated"]


def test_small_bam_reuses_exact_qualified_debug_mode_without_human_leakage() -> None:
    assert gui.fixed_gui_debug_mode(
        "403ab9e9e9877b6ff27d78344113d5bc3cf11ddf92280817e930482b147f40b8", "keep",
    ) is QualificationDebugMode.X3
    assert gui.fixed_gui_debug_mode("human_grch38p14_gencode49_harako_gpu_v1", "keep") is QualificationDebugMode.DISABLED
    assert gui.fixed_gui_debug_mode(
        "403ab9e9e9877b6ff27d78344113d5bc3cf11ddf92280817e930482b147f40b8", "none",
    ) is QualificationDebugMode.DISABLED


def test_descriptive_stage_progress_never_claims_completion_without_stages() -> None:
    assert stage_progress({"state": "RUNNING"}) == 0
    assert stage_progress({"state": "COMPLETED"}) == 1
    assert stage_progress({"state": "RUNNING", "stages": [
        {"state": "SUCCEEDED"}, {"state": "RUNNING"}]}) == 0.5


def test_streamlit_launch_is_loopback_structured_and_headless(tmp_path: Path) -> None:
    app_file = tmp_path / "app.py"; app_file.write_text("pass\n", encoding="utf-8")
    argv = streamlit_argv(app_path=app_file, host="127.0.0.1", port=8501,
                          no_browser=True, python_executable="python-fixed")
    assert argv[:4] == ("python-fixed", "-m", "streamlit", "run")
    assert argv[argv.index("--server.address") + 1] == "127.0.0.1"
    assert argv[argv.index("--server.headless") + 1] == "true"
    assert argv[argv.index("--client.showSidebarNavigation") + 1] == "false"
    with pytest.raises(ValueError):
        streamlit_argv(app_path=app_file, host="192.0.2.1", port=8501, no_browser=True)


def test_controller_argv_has_exact_action_hash_and_no_command_string() -> None:
    argv = controller_argv(action="start", run_dir="/runtime/run", approval_hash="a" * 64,
                           python_executable="python-fixed")
    assert argv == ("python-fixed", "-m", "harako_gpu", "run", "start", "--run-dir",
                    "/runtime/run", "--approval-hash", "a" * 64, "--distribution", "Ubuntu")
    with pytest.raises(ValueError):
        controller_argv(action="delete", run_dir="/runtime/run", approval_hash="a" * 64)


def test_ui_cli_warns_for_unqualified_public_bind(monkeypatch) -> None:
    monkeypatch.setattr("harako_gpu.commands.ui.launch", lambda request: 0)
    local = CliRunner().invoke(app, ["ui", "--no-browser"])
    assert local.exit_code == 0 and "Warning" not in local.stdout
    public = CliRunner().invoke(app, ["ui", "--host", "0.0.0.0", "--no-browser"])
    assert public.exit_code == 0 and "outside the qualified local-only MVP" in public.stdout


def test_fastq_scan_pairs_and_rejects_orphan(tmp_path: Path) -> None:
    for name in ("S1_R1.fastq.gz", "S1_R2.fastq.gz"):
        (tmp_path / name).write_bytes(b"fixture")
    paired = gui.scan_fastqs(str(tmp_path), layout="paired", library_type="ISR")
    assert paired["valid"] and paired["rows"][0]["strandedness"] == "reverse"
    (tmp_path / "S1_R2.fastq.gz").unlink()
    orphan = gui.scan_fastqs(str(tmp_path), layout="paired", library_type="ISR")
    assert not orphan["valid"] and "orphan" in " ".join(orphan["errors"]).lower()


def test_project_slug_and_edited_sample_validation_use_services() -> None:
    assert gui.project_slug_valid("safe-project-2")
    assert not gui.project_slug_valid("Unsafe Project")
    rows = [{"sample": "same", "condition": "A", "fastq_1": "a", "fastq_2": "b",
             "strandedness": "unstranded", "library_protocol": "explicit"}] * 2
    assert not gui.validate_gui_samples(rows)["valid"]


def test_handoff_export_returns_path_not_payload(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(gui, "_host", lambda value, distribution: tmp_path / "handoff.json")
    monkeypatch.setattr(gui, "write_handoff", lambda destination: {"contains_biological_data": False})
    assert gui.export_gui_handoff("/runtime/handoff.json") == "/runtime/handoff.json"


def test_status_poll_retries_sharing_denial_and_recovers(monkeypatch, tmp_path: Path) -> None:
    calls = {"count": 0}
    payload = {"last_update": "2026-08-17T00:00:01Z", "state": "RUNNING"}
    def flaky(_path):
        calls["count"] += 1
        if calls["count"] < 3:
            raise PermissionError("UNC sharing denial")
        return payload
    monkeypatch.setattr(gui, "status_payload", flaky)
    result = gui.poll_run_status(str(tmp_path), sleep=lambda _seconds: None)
    assert result == {"snapshot": payload, "stale": False, "error": "", "attempts": 3}


def test_status_poll_uses_last_valid_without_regression(monkeypatch, tmp_path: Path) -> None:
    last = {"last_update": "2026-08-17T00:00:02Z", "state": "RUNNING"}
    monkeypatch.setattr(gui, "status_payload", lambda _path: {
        "last_update": "2026-08-17T00:00:01Z", "state": "PREPARED"})
    result = gui.poll_run_status(str(tmp_path), last_valid=last, sleep=lambda _seconds: None)
    assert result["stale"] and result["snapshot"] == last


def test_status_poll_never_returns_corrupt_json(monkeypatch, tmp_path: Path) -> None:
    last = {"last_update": "2026-08-17T00:00:02Z", "state": "RUNNING"}
    monkeypatch.setattr(gui, "status_payload", lambda _path: (_ for _ in ()).throw(ValueError("corrupt JSON")))
    result = gui.poll_run_status(str(tmp_path), last_valid=last, sleep=lambda _seconds: None)
    assert result["stale"] and result["snapshot"] == last and result["attempts"] == 6


def test_reconnection_retries_transient_sharing_denial(monkeypatch, tmp_path: Path) -> None:
    attempts = {"count": 0}
    def inspect(_path):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise PermissionError("sharing denial")
        return {"run": {}, "status": {}, "run_directory": str(tmp_path)}
    class Store:
        def __init__(self, _path): pass
        def inspect_lock(self, **_kwargs): return "ABSENT"
    monkeypatch.setattr(gui, "inspect_run", inspect)
    monkeypatch.setattr(gui, "RunStateStore", Store)
    monkeypatch.setattr(gui, "list_artifacts", lambda _path: {"artifacts": []})
    monkeypatch.setattr(gui.time, "sleep", lambda _seconds: None)
    assert gui.reconnect_run(str(tmp_path))["lock_state"] == "ABSENT"
    assert attempts["count"] == 2


def test_atomic_status_writer_reader_stress_1000_updates(tmp_path: Path) -> None:
    target = tmp_path / "status.json"
    atomic_write_json(target, {"sequence": 0})
    errors: list[BaseException] = []
    seen: list[int] = []
    def writer() -> None:
        try:
            for sequence in range(1, 1001):
                atomic_write_json(target, {"sequence": sequence})
        except BaseException as exc:  # pragma: no cover - diagnostic capture
            errors.append(exc)
    thread = threading.Thread(target=writer)
    thread.start()
    while thread.is_alive():
        try:
            seen.append(json.loads(target.read_text(encoding="utf-8"))["sequence"])
        except (PermissionError, FileNotFoundError):
            pass
        except json.JSONDecodeError as exc:
            errors.append(exc)
        time.sleep(0.01)
    thread.join()
    assert not errors
    assert json.loads(target.read_text(encoding="utf-8"))["sequence"] == 1000
    assert seen == sorted(seen)


def test_app_start_smoke_has_fixed_initial_page() -> None:
    tested = AppTest.from_file(str(ROOT / "src/harako_gpu/ui/app.py")).run(timeout=10)
    assert not tested.exception
    assert tested.sidebar.radio[0].value == "Project"
    assert tested.sidebar.selectbox[0].value == "en"
    assert any("Harako-GPU" in item.value for item in tested.caption)


def test_app_page_rerun_preserves_draft_and_changes_navigation() -> None:
    tested = AppTest.from_file(str(ROOT / "src/harako_gpu/ui/app.py")).run(timeout=10)
    tested.sidebar.selectbox[0].set_value("ja")
    tested.session_state[state.PROJECT_SLUG] = "app-test-project"
    tested.sidebar.radio[0].set_value("Samples")
    tested.run(timeout=10)
    assert not tested.exception
    assert tested.sidebar.radio[0].value == "Samples"
    assert tested.session_state[state.PROJECT_SLUG] == "app-test-project"
    assert any(item.value == "サンプル" for item in tested.header)


def test_ui_modules_parse_and_only_launcher_adapter_uses_process_creation() -> None:
    ui_root = ROOT / "src/harako_gpu/ui"
    for path in ui_root.rglob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"))
        assert "Popen(" not in path.read_text(encoding="utf-8")
    assert "subprocess.Popen(" in (ROOT / "src/harako_gpu/adapters/gui_launcher.py").read_text(encoding="utf-8")
