from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harako_gpu.services.run_preparation import _execution_config

from harako_gpu.commands.root import app
from harako_gpu.services.artifacts import discover_artifacts, verify_artifacts
from harako_gpu.services.nextflow_evidence import collect_failed_task_evidence
from harako_gpu.services.progress import user_stage
from harako_gpu.services.run_execution import _salmon_timing, verify_frozen


@pytest.mark.parametrize(("process", "stage"), [
    ("X:PARABRICKS_RNA_FQ2BAM", "GPU alignment"), ("X:FASTP", "preprocessing"),
    ("X:PREPARE_GENOME", "reference preparation"), ("X:MULTIQC", "report generation"),
    ("X:OTHER", "validation"),
])
def test_nextflow_process_progress_mapping(process: str, stage: str) -> None:
    assert user_stage(process) == stage


def test_failed_task_evidence_is_bounded_and_role_mapped(tmp_path: Path) -> None:
    work = tmp_path / "work"; task = work / "ab" / "cdef123"; task.mkdir(parents=True)
    for name in (".command.sh", ".command.err", ".exitcode"):
        (task / name).write_text("safe\n", encoding="utf-8")
    trace = tmp_path / "trace.tsv"
    trace.write_text("task_id\thash\tname\tstatus\texit\n1\tab/cdef\tPIPE:FAIL\tFAILED\t42\n", encoding="utf-8")
    records = collect_failed_task_evidence(trace=trace, work_root=work, destination=tmp_path / "tasks")
    assert records[0]["process"] == "PIPE:FAIL"
    assert records[0]["work_path_role"].startswith("<WORK_DIR>")
    assert not any(str(task) in json.dumps(record) for record in records)


def test_failed_task_evidence_rejects_ambiguous_hash(tmp_path: Path) -> None:
    work = tmp_path / "work"; (work / "ab/cdef1").mkdir(parents=True); (work / "ab/cdef2").mkdir()
    trace = tmp_path / "trace.tsv"
    trace.write_text("task_id\thash\tname\tstatus\texit\n1\tab/cdef\tP\tFAILED\t1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ambiguous"):
        collect_failed_task_evidence(trace=trace, work_root=work, destination=tmp_path / "tasks")


def test_artifact_contract_is_profile_and_mode_specific(tmp_path: Path) -> None:
    (tmp_path / "frozen").mkdir(); (tmp_path / "execution/attempts").mkdir(parents=True)
    plan = {"samples": [{"sample": "S1"}], "quantification": {
        "primary_profile_id": "salmon_2_5_1_deterministic",
        "secondary_profile_id": "salmon_1_10_3_compatibility"}}
    (tmp_path / "frozen/plan.json").write_text(json.dumps(plan), encoding="utf-8")
    records = discover_artifacts(tmp_path)
    paths = {item.relative_path for item in records}
    assert "results/quantification/salmon_2_5_1_deterministic/S1/quant.sf" in paths
    assert "results/quantification/salmon_1_10_3_compatibility/S1/quant.sf" in paths
    assert "results/concordance/manifest.json" in paths
    assert all(item.state.value == "MISSING" for item in records if item.role != "plan")


def test_artifact_command_validation_does_not_shadow_record_position(tmp_path: Path) -> None:
    (tmp_path / "frozen").mkdir()
    (tmp_path / "execution/attempts").mkdir(parents=True)
    command_dir = tmp_path / "results/quantification/profile/S1"
    command_dir.mkdir(parents=True)
    plan = {"samples": [{"sample": "S1"}], "quantification": {
        "primary_profile_id": "profile", "secondary_profile_id": None,
        "explicit_library_type": "ISR", "profiles": {"profile": {
            "version": "2.5.1", "image_identity": "sha256:image",
            "deterministic": True, "index": {"index_id": "index-v2"},
        }}}}
    (tmp_path / "frozen/plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (command_dir / "command.json").write_text(json.dumps({
        "profile_id": "profile", "image_identity": "sha256:image",
        "index_id": "index-v2",
        "structured_argv": ["salmon", "quant", "--deterministic", "--libType", "ISR"],
    }), encoding="utf-8")
    result = verify_artifacts(tmp_path)
    record = next(item for item in result["artifacts"] if item["role"] == "salmon_command")
    assert record["state"] == "VALIDATED"


def test_salmon_meta_detected_library_does_not_replace_frozen_requested_library(tmp_path: Path) -> None:
    (tmp_path / "frozen").mkdir()
    (tmp_path / "execution/attempts").mkdir(parents=True)
    quant = tmp_path / "results/quantification/profile/S1"
    (quant / "aux_info").mkdir(parents=True)
    plan = {"samples": [{"sample": "S1"}], "quantification": {
        "primary_profile_id": "profile", "secondary_profile_id": None,
        "explicit_library_type": "ISR", "profiles": {"profile": {
            "version": "2.5.1", "image_identity": "sha256:image",
            "deterministic": True, "index": {"index_id": "index-v2"},
        }},
    }}
    (tmp_path / "frozen/plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (quant / "aux_info/meta_info.json").write_text(json.dumps({
        "salmon_version": "2.5.1", "library_types": ["IU"],
        "detected_library_type": "IU", "num_processed": 100,
        "num_mapped": 50, "quant_errors": [],
    }), encoding="utf-8")
    (quant / "command.json").write_text(json.dumps({
        "profile_id": "profile", "image_identity": "sha256:image",
        "index_id": "index-v2",
        "structured_argv": ["salmon", "quant", "--deterministic", "--libType", "ISR"],
    }), encoding="utf-8")

    result = verify_artifacts(tmp_path)

    meta = next(item for item in result["artifacts"] if item["role"] == "salmon_meta")
    command = next(item for item in result["artifacts"] if item["role"] == "salmon_command")
    assert meta["state"] == "VALIDATED"
    assert command["state"] == "VALIDATED"


def test_salmon_timing_metadata_is_positive_calculated_and_ordered() -> None:
    payload = _salmon_timing(
        started_at="2026-08-19T00:00:00Z", ended_at="2026-08-19T00:00:04Z",
        wall_seconds=4.0, paired_fragments=1_000, execution_order=2,
    )
    assert payload["fragments_per_second"] == 250.0
    assert payload["execution_order"] == 2
    with pytest.raises(ValueError, match="positive"):
        _salmon_timing(started_at="a", ended_at="b", wall_seconds=0,
                       paired_fragments=1_000, execution_order=1)


def test_frozen_inventory_detects_tampering(tmp_path: Path) -> None:
    from harako_gpu.adapters.filesystem import tree_inventory
    frozen = tmp_path / "frozen"; frozen.mkdir(); (frozen / "plan.json").write_text("{}\n")
    inventory, digest = tree_inventory(frozen, exclude_names=frozenset({"manifest.json"}))
    (frozen / "manifest.json").write_text(json.dumps({"inventory": inventory, "inventory_sha256": digest}))
    verify_frozen(tmp_path)
    (frozen / "plan.json").write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        verify_frozen(tmp_path)


@pytest.mark.parametrize("group", ("run", "artifacts", "support-bundle"))
def test_execution_cli_groups_expose_help(group: str) -> None:
    result = CliRunner().invoke(app, [group, "--help"])
    assert result.exit_code == 0


def test_support_bundle_cli_maps_linux_output_before_path_resolution(monkeypatch) -> None:
    import harako_gpu.commands.support_bundle as command

    observed: dict[str, Path] = {}

    def fake_create(root: Path, *, output: Path | None = None) -> Path:
        observed["root"] = root
        assert output is not None
        observed["output"] = output
        return output

    monkeypatch.setattr(command, "create_support_bundle", fake_create)
    class Context:
        def host_path(self, value: str) -> Path:
            return Path(f"X:\\mapped{value.replace('/', chr(92))}")
    monkeypatch.setattr(
        command, "resolve_validated_run_path",
        lambda *_args, **_kwargs: (Path(r"X:\mapped\runtime\run"), Context()),
    )
    result = CliRunner().invoke(app, ["support-bundle", "create", "/runtime/run", "--output", "/runtime/run/support/final.zip"])
    assert result.exit_code == 0
    assert observed["root"] == Path(r"X:\mapped\runtime\run")
    assert observed["output"] == Path(r"X:\mapped\runtime\run\support\final.zip")


def test_low_memory_execution_config_fits_47_gib_wsl_envelope() -> None:
    text = _execution_config({
        "backend_profile": {"gpu_selection": "all", "qualification_debug_mode": "disabled"},
        "quantification": {"qualification_resource_contract": "full_human_47gib_probe_v1"},
    })
    assert "memory = 42.GB" in text
    assert "cpus = 12" in text
    assert "PARABRICKS_RNA_FQ2BAM" in text


def test_capacity_scheduler_override_is_not_a_product_default() -> None:
    text = _execution_config({
        "backend_profile": {"gpu_selection": "all", "qualification_debug_mode": "disabled"},
        "quantification": {},
    })
    assert "memory = 42.GB" not in text
