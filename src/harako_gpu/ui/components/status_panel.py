from __future__ import annotations

from typing import Any, Mapping

from harako_gpu.ui.view_models import stage_progress
from harako_gpu.ui.labels import text


def render(st: Any, payload: Mapping[str, Any], *, stale: bool = False, language: str = "en") -> None:
    if stale:
        st.warning(f"⚠️ **{text('level.warning', language)}:** {text('stale_status', language)}")
    st.metric("State", payload.get("state", "UNKNOWN"))
    st.progress(stage_progress(payload))
    st.write({key: payload.get(key) for key in (
        "run_id", "project", "current_stage", "current_task", "elapsed_seconds",
        "started_at", "ended_at", "task_counts", "process_counts", "resource_snapshot",
        "artifact_status", "resumable", "failure", "last_update", "updated_at",
    )})
