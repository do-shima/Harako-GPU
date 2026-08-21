"""Hardware/runtime doctor command."""

import sys

import typer

from harako_gpu.core.capabilities import BamOutputMode
from harako_gpu.services.capabilities import (
    FULL_HUMAN_REFERENCE_PACK_ID, FULL_HUMAN_SHA, SMALL_REFERENCE_PACK_ID, SMALL_REFERENCE_SHA,
    evaluate_capability,
)
from harako_gpu.services.preflight import collect_preflight, human_summary, report_json


def doctor_command(
    json_output: bool = typer.Option(False, "--json", help="Emit the versioned machine-readable report."),
    wsl_work_root: str = typer.Option("/", "--wsl-work-root", help="Absolute WSL path planned for Nextflow work data."),
    reference_pack: str | None = typer.Option(None, "--reference-pack"),
    bam_mode: BamOutputMode | None = typer.Option(None, "--bam-mode"),
) -> None:
    """Inspect host, GPU, and workflow runtime prerequisites."""
    try:
        report = collect_preflight(wsl_work_root=wsl_work_root)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    capability = None
    if reference_pack or bam_mode:
        if not reference_pack or bam_mode is None:
            raise typer.BadParameter("--reference-pack and --bam-mode must be provided together")
        if reference_pack == FULL_HUMAN_REFERENCE_PACK_ID:
            reference = {**FULL_HUMAN_SHA, "reference_pack_id": reference_pack}
        elif reference_pack == SMALL_REFERENCE_PACK_ID:
            reference = {**SMALL_REFERENCE_SHA, "reference_pack_id": reference_pack}
        else:
            reference = {"reference_pack_id": reference_pack}
        capability = evaluate_capability(reference=reference, bam_output_mode=bam_mode,
            alignment_profile_id=None if bam_mode is BamOutputMode.NONE else "parabricks_star_one_pass_workstation",
            quantification_mode="recommended_only", primary_profile_id="salmon_2_5_1_deterministic",
            secondary_profile_id=None)
    if json_output:
        import json
        raw = json.loads(report_json(report))
        if capability:
            raw["requested_capability"] = capability.as_dict()
        payload = (json.dumps(raw, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        stream = getattr(sys.stdout, "buffer", None)
        if stream is None:
            typer.echo(payload.decode("utf-8"), nl=False)
        else:
            stream.write(payload)
            stream.flush()
        return
    typer.echo(human_summary(report))
    if capability:
        typer.echo(f"\nRequested analysis: {capability.requested_route.value}")
        typer.echo(f"Status: {capability.status.value}")
        typer.echo(f"GPU used: {str(capability.gpu_used).lower()}")
        typer.echo(f"BAM generated: {str(capability.bam_generated).lower()}")
        typer.echo(f"Reason: {capability.explanation}")
