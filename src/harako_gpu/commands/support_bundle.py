"""Thin sanitized support bundle CLI."""

import json
from pathlib import Path

import typer

from harako_gpu.services.support_bundle import create_support_bundle
from harako_gpu.services.run_status import resolve_validated_run_path


support_app = typer.Typer(help="Create a sanitized run support bundle.", add_completion=False)


@support_app.command("create")
def create(run_dir: str = typer.Argument(...), output: str | None = typer.Option(None),
           distribution: str = typer.Option("Ubuntu"),
           execution_context: str = typer.Option("wsl2", "--execution-context")) -> None:
    try:
        root, context = resolve_validated_run_path(
            run_dir, requested=execution_context, distribution=distribution,
        )
        destination = None if output is None else (
            context.host_path(output) if output.startswith("/") else Path(output)
        )
        result = create_support_bundle(root, output=destination)
    except (OSError, ValueError) as exc: raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps({"schema_version": 1, "bundle": str(result), "biological_data_included": False}, indent=2))
