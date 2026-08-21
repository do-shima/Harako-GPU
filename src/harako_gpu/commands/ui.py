"""Thin local Streamlit launcher command."""

from __future__ import annotations

import typer

from harako_gpu.ui.launcher import UiLaunchRequest, launch


def ui_command(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8501, "--port", min=1024, max=65535),
    no_browser: bool = typer.Option(False, "--no-browser"),
    output_root: str | None = typer.Option(None, "--output-root"),
) -> None:
    """Launch the local single-user reference-aware GUI."""
    request = UiLaunchRequest(host=host, port=port, no_browser=no_browser, output_root=output_root)
    if not request.loopback_only:
        typer.secho("Warning: non-loopback binding is outside the qualified local-only MVP.", fg=typer.colors.YELLOW)
    try:
        code = launch(request)
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    if code:
        raise typer.Exit(code)
