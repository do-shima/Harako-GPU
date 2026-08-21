"""Color-independent semantic messages for the GUI presentation layer."""

from __future__ import annotations

from enum import Enum
from typing import Any

from harako_gpu.ui.labels import text


class MessageLevel(str, Enum):
    INFO = "info"
    LIMITATION = "limitation"
    WARNING = "warning"
    BLOCKER = "blocker"
    FAILURE = "failure"


_ICON = {
    MessageLevel.INFO: "ℹ️",
    MessageLevel.LIMITATION: "◇",
    MessageLevel.WARNING: "⚠️",
    MessageLevel.BLOCKER: "⛔",
    MessageLevel.FAILURE: "✖",
}


def render(st: Any, level: MessageLevel, heading: str, explanation: str,
           *, language: str, next_action: str = "") -> None:
    body = f"{_ICON[level]} **{text(f'level.{level.value}', language)} — {heading}**\n\n{explanation}"
    if next_action:
        body += f"\n\n**{text('next_action', language)}:** {next_action}"
    renderer = {
        MessageLevel.INFO: st.info,
        MessageLevel.LIMITATION: st.warning,
        MessageLevel.WARNING: st.warning,
        MessageLevel.BLOCKER: st.error,
        MessageLevel.FAILURE: st.error,
    }[level]
    renderer(body)


def error_summary(st: Any, errors: list[str], *, language: str, next_action: str = "") -> None:
    if not errors:
        return
    explanation = "\n".join(f"- {value}" for value in errors)
    render(st, MessageLevel.BLOCKER, f"{text('error_summary', language)} ({len(errors)})",
           explanation, language=language, next_action=next_action)
