from __future__ import annotations

from typing import Any, Mapping

from harako_gpu.ui.labels import text
from harako_gpu.ui.view_models import capability_view
from harako_gpu.ui.components.message import MessageLevel, render as message


def render(st: Any, result: Mapping[str, Any], language: str) -> None:
    view = capability_view(result)
    if view["available"]:
        st.success(f"✓ **{text(view['label_key'], language)}** — {view['reason']}")
    else:
        message(st, MessageLevel.BLOCKER, text(view["label_key"], language), view["reason"],
                language=language, next_action="; ".join(view["allowed_next_actions"]))
    st.caption(f"GPU: {view['gpu_used']} · BAM: {view['bam_generated']} · {view['status']}")
