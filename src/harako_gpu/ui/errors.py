"""Presentation-safe error handling for Streamlit pages."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def user_error(exc: BaseException) -> str:
    message = str(exc).strip()
    return message or exc.__class__.__name__


def capture(action: Callable[[], Any]) -> tuple[Any | None, str | None]:
    try:
        return action(), None
    except (OSError, ValueError) as exc:
        return None, user_error(exc)
