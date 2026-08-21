from __future__ import annotations

from typing import Any


def render(st: Any, message: str) -> None:
    st.info(message)
