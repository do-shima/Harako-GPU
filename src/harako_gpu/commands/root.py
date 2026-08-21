"""Restricted Harako-GPU command surface."""

from __future__ import annotations

import typer

from harako_gpu.version import VERSION


app = typer.Typer(
    name="harako-gpu",
    help="Harako-GPU foundation, planning, and runtime preflight.",
    no_args_is_help=True,
    add_completion=False,
)


def version_callback(value: bool) -> None:
    if value:
        typer.echo(VERSION)
        raise typer.Exit()


@app.callback()
def root(
    version: bool = typer.Option(
        False,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Show the Harako-GPU package version.",
    ),
) -> None:
    """Compose the documented command groups only."""


def register_commands() -> None:
    """Register subcommands lazily so the root remains composition-only."""
    from harako_gpu.commands.contract import contract_app
    from harako_gpu.commands.concordance import concordance_app
    from harako_gpu.commands.doctor import doctor_command
    from harako_gpu.commands.inspect import inspect_command
    from harako_gpu.commands.plan import plan_app
    from harako_gpu.commands.profiles import profiles_app
    from harako_gpu.commands.star_counts import star_counts_app
    from harako_gpu.commands.run import run_app
    from harako_gpu.commands.artifacts import artifacts_app
    from harako_gpu.commands.support_bundle import support_app
    from harako_gpu.commands.capabilities import capabilities_app
    from harako_gpu.commands.host_profile import host_profile_app
    from harako_gpu.commands.ui import ui_command

    app.command("doctor")(doctor_command)
    app.command("inspect")(inspect_command)
    app.add_typer(plan_app, name="plan")
    app.add_typer(contract_app, name="contract")
    app.add_typer(profiles_app, name="profiles")
    app.add_typer(concordance_app, name="concordance")
    app.add_typer(star_counts_app, name="star-counts")
    app.add_typer(run_app, name="run")
    app.add_typer(artifacts_app, name="artifacts")
    app.add_typer(support_app, name="support-bundle")
    app.add_typer(capabilities_app, name="capabilities")
    app.add_typer(host_profile_app, name="host-profile")
    app.command("ui")(ui_command)


register_commands()
