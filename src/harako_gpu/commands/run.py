"""Thin CLI adapters for immutable foreground runs."""

from __future__ import annotations

import json
import time
from pathlib import Path

import typer

from harako_gpu.adapters.execution_context import parse_execution_context
from harako_gpu.services.run_execution import execute_run
from harako_gpu.services.run_preparation import (
    build_native_linux_preparation_context, build_wsl_preparation_context, prepare_run,
    runtime_requirements_for_plan_file,
)
from harako_gpu.services.run_status import human_status, inspect_run, resolve_validated_run_path, status_payload


run_app = typer.Typer(help="Prepare, start, inspect, status, or resume an immutable local run.", add_completion=False)


@run_app.command("prepare")
def prepare(plan: Path = typer.Option(..., exists=True, dir_okay=False),
            runtime_root: str = typer.Option(...), distribution: str = typer.Option("Ubuntu"),
            execution_context: str = typer.Option("wsl2", "--execution-context")) -> None:
    try:
        selected = parse_execution_context(execution_context, distribution=distribution)
        requirements = runtime_requirements_for_plan_file(plan)
        context = (build_native_linux_preparation_context(
                       runtime_root=runtime_root, requirements=requirements,
                   )
                   if selected.is_native_linux else
                   build_wsl_preparation_context(
                       runtime_root=runtime_root,
                       distribution=str(selected.distribution),
                       requirements=requirements,
                   ))
        result = prepare_run(plan_path=plan, runtime_root=runtime_root, context=context)
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    next_context = "native-linux" if context.execution.is_native_linux else "wsl2"
    typer.echo(json.dumps({"schema_version": 1, "state": "PREPARED", "run_id": result.run_id,
        "run_directory": result.run_dir_linux, "approval_hash": result.approval_hash,
        "primary_profile_id": result.primary_profile_id, "secondary_profile_id": result.secondary_profile_id,
        "next_command": (f"harako-gpu run start --run-dir {result.run_dir_linux} "
                         f"--approval-hash {result.approval_hash} --execution-context {next_context}")}, indent=2))


def _execute(run_dir: str, approval_hash: str, distribution: str,
             execution_context: str, resume: bool) -> None:
    try:
        path, _ = resolve_validated_run_path(
            run_dir, requested=execution_context, distribution=distribution,
        )
        result = execute_run(run_dir=path, approval_hash=approval_hash,
                             resume=resume, distribution=distribution,
                             execution_context=execution_context)
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(human_status(status_payload(path)))
    if result.state.value not in {"COMPLETED", "COMPLETED_WITH_LIMITATION", "RETENTION_PENDING"}:
        raise typer.Exit(1)


@run_app.command("start")
def start(run_dir: str = typer.Option(...), approval_hash: str = typer.Option(...),
          distribution: str = typer.Option("Ubuntu"),
          execution_context: str = typer.Option("wsl2", "--execution-context")) -> None:
    _execute(run_dir, approval_hash, distribution, execution_context, False)


@run_app.command("resume")
def resume(run_dir: str = typer.Option(...), approval_hash: str = typer.Option(...),
           distribution: str = typer.Option("Ubuntu"),
           execution_context: str = typer.Option("wsl2", "--execution-context")) -> None:
    _execute(run_dir, approval_hash, distribution, execution_context, True)


@run_app.command("inspect")
def inspect(run_dir: str = typer.Argument(...), json_output: bool = typer.Option(False, "--json"),
            distribution: str = typer.Option("Ubuntu"),
            execution_context: str = typer.Option("wsl2", "--execution-context")) -> None:
    try:
        path, _ = resolve_validated_run_path(
            run_dir, requested=execution_context, distribution=distribution,
        )
        payload = inspect_run(path)
    except (OSError, ValueError) as exc: raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if json_output else
               human_status(status_payload(path)))


@run_app.command("status")
def status(run_dir: str = typer.Argument(...), json_output: bool = typer.Option(False, "--json"),
           watch: bool = typer.Option(False, "--watch"), distribution: str = typer.Option("Ubuntu"),
           execution_context: str = typer.Option("wsl2", "--execution-context")) -> None:
    try:
        path, _ = resolve_validated_run_path(
            run_dir, requested=execution_context, distribution=distribution,
        )
        while True:
            payload = status_payload(path)
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if json_output else human_status(payload))
            if not watch or payload["state"] != "RUNNING": break
            time.sleep(1)
    except KeyboardInterrupt:
        return
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
