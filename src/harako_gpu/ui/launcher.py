"""UI launch contract; process creation remains in the adapter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harako_gpu.adapters.gui_launcher import run_streamlit, streamlit_argv


@dataclass(frozen=True)
class UiLaunchRequest:
    host: str = "127.0.0.1"
    port: int = 8501
    no_browser: bool = False
    output_root: str | None = None

    @property
    def loopback_only(self) -> bool:
        return self.host in {"127.0.0.1", "localhost"}


def app_path() -> Path:
    return Path(__file__).with_name("app.py")


def launch(request: UiLaunchRequest) -> int:
    argv = streamlit_argv(app_path=app_path(), host=request.host, port=request.port,
                          no_browser=request.no_browser, output_root=request.output_root)
    return run_streamlit(argv)
