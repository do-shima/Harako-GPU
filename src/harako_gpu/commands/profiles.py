"""Read-only fixed quantification profile catalog CLI."""

import json

import typer

from harako_gpu.services.quantification_profiles import get_profile, visible_profiles


profiles_app = typer.Typer(help="Inspect fixed quantification profiles.", add_completion=False)


@profiles_app.command("list")
def list_profiles(json_output: bool = typer.Option(False, "--json")) -> None:
    rows = [profile.as_dict() for profile in visible_profiles()]
    if json_output:
        typer.echo(json.dumps({"schema_version": 1, "profiles": rows}, ensure_ascii=True, indent=2))
        return
    for row in rows:
        typer.echo(f"{row['profile_id']}\t{row['display_name_ja']}\t{str(row['display_name_en']).replace('—', '--')}\t{row['product_status']}")


@profiles_app.command("show")
def show_profile(profile_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    try:
        row = get_profile(profile_id).as_dict()
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_output:
        typer.echo(json.dumps(row, ensure_ascii=True, indent=2, sort_keys=True))
    else:
        for key, value in row.items():
            typer.echo(f"{key}: {value}")
