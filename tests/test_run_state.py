from __future__ import annotations

import json

import pytest

from harako_gpu.core.run_lifecycle import RunState, RunStatus, StageId, TaskRecord, TaskState
from harako_gpu.services.run_state import RunStateStore


SHA = "a" * 64


def store(tmp_path) -> RunStateStore:
    (tmp_path / "tasks").mkdir()
    value = RunStateStore(tmp_path)
    value.write_status(RunStatus("run", RunState.PREPARED, None, None, None, "now"))
    value.write_tasks((TaskRecord("t", StageId.PREFLIGHT.value, None, None, SHA, SHA, None),))
    return value


def test_single_state_store_transitions_and_updates_tasks(tmp_path) -> None:
    state = store(tmp_path)
    status = state.transition(RunState.RUNNING, attempt_id="0001", current_stage=StageId.PREFLIGHT.value)
    assert status.state is RunState.RUNNING
    task = state.read_tasks()[0]
    state.replace_task(TaskRecord(**{**task.__dict__, "state": TaskState.SUCCEEDED}))
    assert state.read_tasks()[0].state is TaskState.SUCCEEDED
    with pytest.raises(ValueError):
        state.transition(RunState.PREPARED)


def test_lock_is_exclusive_and_stale_is_archived(tmp_path, monkeypatch) -> None:
    state = store(tmp_path)
    state.create_lock(attempt_id="0001", execution_context="native", command_identity=SHA)
    with pytest.raises(ValueError, match="already exists"):
        state.create_lock(attempt_id="0001", execution_context="native", command_identity=SHA)
    monkeypatch.setattr("harako_gpu.services.run_state.local_pid_alive", lambda pid: False)
    assert state.inspect_lock() == "STALE"
    archived = state.archive_stale_lock()
    assert archived.is_file() and not state.lock_path.exists()
    assert json.loads(archived.read_text())["attempt_id"] == "0001"


def test_native_lock_checks_local_controller_and_child_without_wsl(tmp_path, monkeypatch) -> None:
    state = store(tmp_path)
    state.create_lock(attempt_id="0001", execution_context="native_linux", command_identity=SHA)
    controller = json.loads(state.lock_path.read_text())["controller_pid"]
    monkeypatch.setattr("harako_gpu.services.run_state.local_pid_alive", lambda pid: pid == controller)
    assert state.inspect_lock() == "LIVE"
    state.update_lock_pids(linux_pid=222)
    monkeypatch.setattr("harako_gpu.services.run_state.local_pid_alive", lambda pid: pid == 222)
    monkeypatch.setattr(
        "harako_gpu.services.run_state.wsl_pid_alive",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("WSL probe used for native lock")),
    )
    assert state.inspect_lock() == "LIVE"
    monkeypatch.setattr("harako_gpu.services.run_state.local_pid_alive", lambda _pid: False)
    assert state.inspect_lock() == "STALE"


def test_wsl_lock_checks_wrapper_and_internal_child(tmp_path, monkeypatch) -> None:
    state = store(tmp_path)
    state.create_lock(attempt_id="0001", execution_context="wsl2:Ubuntu", command_identity=SHA)
    state.update_lock_pids(wsl_pid=111, linux_pid=222)
    monkeypatch.setattr("harako_gpu.services.run_state.local_pid_alive", lambda pid: pid == 111)
    monkeypatch.setattr("harako_gpu.services.run_state.wsl_pid_alive", lambda *_args, **_kwargs: False)
    assert state.inspect_lock(distribution="Ubuntu") == "LIVE"
    monkeypatch.setattr("harako_gpu.services.run_state.local_pid_alive", lambda _pid: False)
    monkeypatch.setattr("harako_gpu.services.run_state.wsl_pid_alive", lambda pid, **_kwargs: pid == 222)
    assert state.inspect_lock(distribution="Ubuntu") == "LIVE"
    with pytest.raises(ValueError, match="distribution"):
        state.inspect_lock(distribution="Debian")


def test_malformed_lock_pids_are_stale_and_absent_is_explicit(tmp_path, monkeypatch) -> None:
    state = store(tmp_path)
    assert state.inspect_lock() == "ABSENT"
    state.create_lock(attempt_id="0001", execution_context="native_linux", command_identity=SHA)
    payload = json.loads(state.lock_path.read_text())
    payload.update({"controller_pid": "bad", "linux_pid": -10, "wsl_pid": {"bad": True}})
    state.lock_path.write_text(json.dumps(payload))
    monkeypatch.setattr("harako_gpu.services.run_state.local_pid_alive", lambda pid: pid > 0)
    assert state.inspect_lock() == "STALE"
