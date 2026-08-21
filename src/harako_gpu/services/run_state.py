"""The single application-service writer for mutable run state and locks."""

from __future__ import annotations

import json
import os
import socket
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harako_gpu.adapters.filesystem import atomic_write_json, create_exclusive_json
from harako_gpu.adapters.liveness import local_pid_alive, wsl_pid_alive
from harako_gpu.adapters.process import ProcessRunner
from harako_gpu.core.run_lifecycle import RunState, RunStatus, TaskRecord, TaskState, transition_run


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class RunStateStore:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir.resolve()
        self.status_path = self.run_dir / "status.json"
        self.tasks_path = self.run_dir / "tasks" / "tasks.json"
        self.lock_path = self.run_dir / "lock.json"

    def read_json(self, path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Cannot read run state {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"Run state must be an object: {path}")
        return value

    def status(self) -> RunStatus:
        raw = self.read_json(self.status_path)
        return RunStatus(
            run_id=str(raw["run_id"]), state=RunState(raw["state"]),
            current_stage=raw.get("current_stage"), current_task=raw.get("current_task"),
            attempt_id=raw.get("attempt_id"), updated_at=str(raw["updated_at"]),
            started_at=raw.get("started_at"), ended_at=raw.get("ended_at"),
            task_counts=dict(raw.get("task_counts") or {}), process_counts=dict(raw.get("process_counts") or {}),
            resource_snapshot=dict(raw.get("resource_snapshot") or {}), artifact_status=dict(raw.get("artifact_status") or {}),
            resumable=bool(raw.get("resumable")), failure=raw.get("failure"),
            warnings=tuple(raw.get("warnings") or ()), next_actions=tuple(raw.get("next_actions") or ()),
            schema_version=int(raw.get("schema_version", 1)),
        )

    def write_status(self, status: RunStatus) -> None:
        atomic_write_json(self.status_path, status.as_dict())

    def transition(self, target: RunState, *, resume: bool = False, **changes: Any) -> RunStatus:
        current = self.status()
        transition_run(current.state, target, resume=resume)
        status = replace(current, state=target, updated_at=utc_now(), **changes)
        self.write_status(status)
        return status

    def read_tasks(self) -> tuple[TaskRecord, ...]:
        raw = self.read_json(self.tasks_path)
        return tuple(TaskRecord(**{**item, "state": TaskState(item["state"])}) for item in raw.get("tasks", []))

    def write_tasks(self, tasks: tuple[TaskRecord, ...]) -> None:
        for task in tasks:
            task.validate()
        atomic_write_json(self.tasks_path, {"schema_version": 1, "tasks": [asdict(task) for task in tasks]})

    def replace_task(self, task: TaskRecord) -> None:
        tasks = list(self.read_tasks())
        positions = [index for index, item in enumerate(tasks) if item.task_id == task.task_id]
        if len(positions) != 1:
            raise ValueError("Task identity is missing or ambiguous")
        task.validate()
        tasks[positions[0]] = task
        self.write_tasks(tuple(tasks))

    def create_lock(self, *, attempt_id: str, execution_context: str, command_identity: str) -> None:
        create_exclusive_json(self.lock_path, {
            "schema_version": 1, "run_id": self.status().run_id, "attempt_id": attempt_id,
            "controller_pid": os.getpid(), "wsl_pid": None, "linux_pid": None,
            "host": socket.gethostname(), "execution_context": execution_context,
            "started_at": utc_now(), "command_identity": command_identity,
        })

    def update_lock_pids(self, *, wsl_pid: int | None = None, linux_pid: int | None = None) -> None:
        lock = self.read_json(self.lock_path)
        if wsl_pid is not None:
            lock["wsl_pid"] = wsl_pid
        if linux_pid is not None:
            lock["linux_pid"] = linux_pid
        atomic_write_json(self.lock_path, lock)

    def inspect_lock(self, *, distribution: str | None = None, runner: ProcessRunner | None = None) -> str:
        if not self.lock_path.exists():
            return "ABSENT"
        lock = self.read_json(self.lock_path)
        def pid(name: str) -> int:
            try:
                value = int(lock.get(name) or 0)
            except (TypeError, ValueError):
                return 0
            return value if value > 0 else 0

        execution_context = str(lock.get("execution_context") or "")
        controller_alive = local_pid_alive(pid("controller_pid"))
        if execution_context in {"native", "native_linux"}:
            wsl_alive = False
            linux_alive = local_pid_alive(pid("linux_pid"))
        elif execution_context.startswith("wsl2:"):
            frozen_distribution = execution_context.split(":", 1)[1]
            if distribution is not None and distribution != frozen_distribution:
                raise ValueError("CLI distribution does not match frozen lock execution context")
            wsl_alive = local_pid_alive(pid("wsl_pid"))
            linux_alive = wsl_pid_alive(pid("linux_pid"), distribution=frozen_distribution, runner=runner)
        else:
            raise ValueError("Lock execution context is unsupported")
        return "LIVE" if any((controller_alive, wsl_alive, linux_alive)) else "STALE"

    def archive_stale_lock(self) -> Path:
        if not self.lock_path.exists():
            raise ValueError("No stale lock exists")
        destination = self.run_dir / "execution" / "stale-locks" / f"lock-{utc_now().replace(':', '')}.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(self.lock_path, destination)
        return destination

    def release_lock(self) -> None:
        if self.lock_path.exists():
            self.lock_path.unlink()
