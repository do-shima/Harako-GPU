"""Thin artifact discovery and verification CLI."""

import json

import typer

from harako_gpu.services.artifacts import list_artifacts, verify_artifacts
from harako_gpu.services.run_status import resolve_validated_run_path


artifacts_app = typer.Typer(help="List or verify fixed run artifacts.", add_completion=False)


@artifacts_app.command("list")
def list_command(run_dir: str = typer.Argument(...), json_output: bool = typer.Option(False, "--json"),
                 distribution: str = typer.Option("Ubuntu"),
                 execution_context: str = typer.Option("wsl2", "--execution-context")) -> None:
    try:
        path, _ = resolve_validated_run_path(
            run_dir, requested=execution_context, distribution=distribution,
        )
        payload = list_artifacts(path)
    except (OSError, ValueError) as exc: raise typer.BadParameter(str(exc)) from exc
    if json_output: typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for item in payload["artifacts"]: typer.echo(f"{item['state']}\t{item['role']}\t{item['relative_path']}")


@artifacts_app.command("verify")
def verify(run_dir: str = typer.Argument(...), deep: bool = typer.Option(False, "--deep"),
           json_output: bool = typer.Option(False, "--json"), distribution: str = typer.Option("Ubuntu"),
           execution_context: str = typer.Option("wsl2", "--execution-context")) -> None:
    try:
        path, _ = resolve_validated_run_path(
            run_dir, requested=execution_context, distribution=distribution,
        )
        payload = verify_artifacts(path, deep=deep, distribution=distribution,
                                   progress=None if json_output else typer.echo)
    except (OSError, ValueError) as exc: raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(payload, indent=2, sort_keys=True) if json_output else
               f"complete: {str(payload['complete']).lower()}\nfailures: {', '.join(payload['failures']) or 'none'}")
    if not payload["complete"]: raise typer.Exit(1)
