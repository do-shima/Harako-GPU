"""Read-only run inspection and user-facing status projection."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harako_gpu.adapters.execution_context import (
    ExecutionContext, parse_execution_context, require_native_linux_host,
)
from harako_gpu.services.run_state import RunStateStore


def resolve_validated_run_path(value: str, *, requested: str,
                               distribution: str) -> tuple[Path, ExecutionContext]:
    """Project one existing run path and validate its frozen transport once."""
    context = parse_execution_context(requested, distribution=distribution)
    if context.is_native_linux:
        require_native_linux_host()
    if value.startswith("/"):
        root = Path(value) if context.is_native_linux else context.host_path(value)
    else:
        root = Path(value).expanduser()
    root = root.resolve(strict=True)
    payload = json.loads((root / "run.json").read_text(encoding="utf-8"))
    frozen = parse_execution_context(str(payload["identity"]["execution_context"]))
    if context.identity != frozen.identity:
        raise ValueError(
            f"Requested execution context {context.identity} does not match frozen {frozen.identity}"
        )
    return root, frozen


def inspect_run(run_dir: Path) -> dict[str, Any]:
    root = run_dir.resolve(strict=True)
    run = json.loads((root / "run.json").read_text(encoding="utf-8"))
    status = RunStateStore(root).status().as_dict()
    return {"schema_version": 1, "run": run, "status": status,
            "run_directory": str(root)}


def status_payload(run_dir: Path) -> dict[str, Any]:
    root = run_dir.resolve(strict=True)
    store = RunStateStore(root)
    identity = json.loads((root / "run.json").read_text(encoding="utf-8"))["identity"]
    status = store.status().as_dict()
    tasks = [task.__dict__ for task in store.read_tasks()]
    started = status.get("started_at")
    elapsed = None
    if started:
        try:
            elapsed = max(0, int((datetime.now(UTC) - datetime.fromisoformat(started.replace("Z", "+00:00"))).total_seconds()))
        except ValueError:
            pass
    return {
        "schema_version": 1, "run_id": identity["run_id"], "project": identity["project_slug"],
        "analysis_series_id": identity["analysis_series_id"], "primary_profile_id": identity["primary_profile_id"],
        "secondary_profile_id": identity.get("secondary_profile_id"), "state": status["state"],
        "current_stage": status.get("current_stage"), "current_task": status.get("current_task"),
        "attempt_id": status.get("attempt_id"), "elapsed_seconds": elapsed,
        "task_counts": status.get("task_counts", {}), "process_counts": status.get("process_counts", {}),
        "resource_snapshot": status.get("resource_snapshot", {}), "artifact_status": status.get("artifact_status", {}),
        "last_update": status["updated_at"], "resumable": status.get("resumable", False),
        "failure": status.get("failure"), "warnings": status.get("warnings", []),
        "next_actions": status.get("next_actions", []), "tasks": tasks,
    }


def human_status(payload: dict[str, Any]) -> str:
    secondary = payload.get("secondary_profile_id") or "none"
    resources = payload.get("resource_snapshot") or {}
    return "\n".join((
        f"run ID: {payload['run_id']}", f"project: {payload['project']}", f"state: {payload['state']}",
        f"stage: {payload.get('current_stage') or '-'}", f"task: {payload.get('current_task') or '-'}",
        f"primary: {payload['primary_profile_id']}", f"secondary: {secondary}",
        f"elapsed: {payload.get('elapsed_seconds') if payload.get('elapsed_seconds') is not None else '-'} s",
        f"tasks: {json.dumps(payload.get('task_counts', {}), sort_keys=True)}",
        f"Nextflow: {json.dumps(payload.get('process_counts', {}), sort_keys=True)}",
        f"GPU/RAM: {json.dumps(resources, sort_keys=True)}", f"last update: {payload['last_update']}",
        f"resumable: {str(payload.get('resumable', False)).lower()}",
        f"next action: {', '.join(payload.get('next_actions') or ()) or '-'}",
    ))
