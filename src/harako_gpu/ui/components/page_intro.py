"""Consistent page purpose, completion condition, and blocker presentation."""

from __future__ import annotations

from typing import Any

from harako_gpu.ui.labels import text


def render(st: Any, page_key: str, language: str, *, blocker: str = "") -> None:
    st.caption(f"**{text('purpose', language)}:** {text(f'page.{page_key}.purpose', language)}")
    st.caption(f"**{text('completion', language)}:** {text(f'page.{page_key}.complete', language)}")
    if blocker:
        st.warning(f"⛔ **{text('current_blocker', language)}:** {blocker}")
