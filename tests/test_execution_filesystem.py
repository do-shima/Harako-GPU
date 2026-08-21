from __future__ import annotations

import json

import pytest

from harako_gpu.adapters.filesystem import (
    atomic_write_json, create_exclusive_json, ensure_within, require_safe_linux_runtime_path,
)


def test_atomic_state_and_exclusive_lock(tmp_path) -> None:
    status = tmp_path / "status.json"
    atomic_write_json(status, {"state": "PREPARED"})
    atomic_write_json(status, {"state": "RUNNING"})
    assert json.loads(status.read_text()) == {"state": "RUNNING"}
    lock = tmp_path / "lock.json"
    create_exclusive_json(lock, {"pid": 1})
    with pytest.raises(ValueError, match="already exists"):
        create_exclusive_json(lock, {"pid": 2})


def test_path_safety_rejects_escape_and_windows_mounts(tmp_path) -> None:
    inside = tmp_path / "run" / "x"
    assert ensure_within(inside, tmp_path) == inside.resolve()
    with pytest.raises(ValueError, match="escapes"):
        ensure_within(tmp_path.parent / "outside", tmp_path)
    assert require_safe_linux_runtime_path("/home/u/runtime") == "/home/u/runtime"
    for value in ("relative", "/mnt/c/work", "/mnt/d/work", "/home/u/../x"):
        with pytest.raises(ValueError):
            require_safe_linux_runtime_path(value)
