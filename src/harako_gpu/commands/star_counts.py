"""STAR GeneCounts artifact inspection and column selection CLI."""

import json
from pathlib import Path

import typer

from harako_gpu.adapters.filesystem import sha256_path, write_new_text
from harako_gpu.services.star_gene_counts import (
    column_manifest, metadata_counts_tsv, parse_reads_per_gene, selected_counts_tsv,
)


star_counts_app = typer.Typer(help="Inspect and validate STAR GeneCounts artifacts.", add_completion=False)


def _load(path: Path):
    try:
        return parse_reads_per_gene(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc


@star_counts_app.command("inspect")
def inspect_counts(path: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    table = _load(path)
    typer.echo(json.dumps({"schema_version": 1, "genes": len(table.genes), "metadata": table.metadata}, indent=2))


@star_counts_app.command("validate")
def validate_counts(path: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    table = _load(path)
    typer.echo(json.dumps({"schema_version": 1, "valid": True, "genes": len(table.genes)}, indent=2))


@star_counts_app.command("select-column")
def select_column(
    path: Path = typer.Argument(..., exists=True, dir_okay=False),
    output_dir: Path = typer.Option(...), sample: str = typer.Option(...),
    library_type: str = typer.Option(...), gtf_sha256: str = typer.Option(...),
    reference_pack_id: str = typer.Option(...), processed_fastq_sha256: str = typer.Option(...),
    run_identity: str = typer.Option(...),
) -> None:
    table = _load(path)
    column, counts = table.selected(library_type)
    destination = output_dir.resolve()
    if destination.exists():
        raise typer.BadParameter("Output directory must be new")
    manifest = column_manifest(
        sample=sample, source_file=str(path.resolve()), source_sha256=sha256_path(path),
        library_type=library_type, gtf_sha256=gtf_sha256, reference_pack_id=reference_pack_id,
        processed_fastq_sha256=processed_fastq_sha256, run_identity=run_identity,
    )
    write_new_text(destination / f"{sample}.selected_gene_counts.tsv", selected_counts_tsv(counts))
    write_new_text(destination / f"{sample}.metadata_counts.tsv", metadata_counts_tsv(table.metadata, column))
    write_new_text(destination / f"{sample}.column_manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    typer.echo(json.dumps({"schema_version": 1, "output_dir": str(destination), "selected_column": column}, indent=2))
