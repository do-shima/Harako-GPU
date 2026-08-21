"""Read-only input inspection command."""

import json
from pathlib import Path

import typer

from harako_gpu.services.input_inspection import inspect_input


def inspect_command(path: Path = typer.Argument(Path("."), exists=True, file_okay=False)) -> None:
    """Inspect FASTQ names without opening biological content."""
    typer.echo(json.dumps(inspect_input(path), ensure_ascii=False, indent=2, sort_keys=True))
