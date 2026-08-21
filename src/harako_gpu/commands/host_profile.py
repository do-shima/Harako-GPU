"""Public explicit provisioning of the fixed Ubuntu host qualification."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from harako_gpu.services.host_provisioning import provision_ubuntu_high_memory_host


host_profile_app = typer.Typer(
    help="Provision fixed host qualification receipts from verified evidence.",
    add_completion=False,
)


@host_profile_app.command("provision")
def provision(
    bundle_root: Path = typer.Option(..., "--bundle-root", exists=True, file_okay=False),
    runtime_root: Path = typer.Option(..., "--runtime-root", exists=True, file_okay=False),
    plugin_dir: Path = typer.Option(..., "--plugin-dir", exists=True, file_okay=False),
    handoff_root: Path = typer.Option(..., "--handoff-root", exists=True, file_okay=False),
    parabricks_execution_receipt: Path = typer.Option(
        ..., "--parabricks-execution-receipt", exists=True, dir_okay=False,
    ),
    replace: bool = typer.Option(False, "--replace"),
) -> None:
    """Validate evidence, current host, offline closures, and install receipts atomically."""
    try:
        result = provision_ubuntu_high_memory_host(
            bundle_root=bundle_root,
            runtime_root=runtime_root,
            plugin_dir=plugin_dir,
            handoff_root=handoff_root,
            parabricks_execution_receipt=parabricks_execution_receipt,
            replace=replace,
        )
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
