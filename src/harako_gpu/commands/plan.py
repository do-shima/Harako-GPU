"""Non-executing plan command group."""

import json
from pathlib import Path

import typer

from harako_gpu.core.contracts import BamRetention, MemoryMode, QualificationDebugMode
from harako_gpu.core.capabilities import BamOutputMode
from harako_gpu.services.planning import create_plan, validate_plan_file
from harako_gpu.services.alignment_profiles import TWO_PASS_PROFILE_ID
from harako_gpu.adapters.process import ProcessRunner
from harako_gpu.services.host_profiles import (
    WINDOWS_HOST_PROFILE_ID, HostQualificationReceipt,
    inspect_provenance_image, load_offline_provenance,
)


plan_app = typer.Typer(help="Create or validate an immutable execution plan.", add_completion=False)


@plan_app.command("create")
def create(
    samplesheet: Path = typer.Option(..., exists=True, dir_okay=False),
    plan_dir: Path = typer.Option(...),
    output_root: Path = typer.Option(...),
    work_root: Path = typer.Option(...),
    fasta: Path = typer.Option(..., exists=True, dir_okay=False),
    gtf: Path = typer.Option(..., exists=True, dir_okay=False),
    transcript_fasta: Path | None = typer.Option(None, exists=True, dir_okay=False),
    salmon_index_manifest: Path | None = typer.Option(
        None, help="Deprecated historical Salmon 1.10.3 index manifest; ignored by new plans",
    ),
    salmon_2_5_1_index_manifest: Path | None = typer.Option(None),
    salmon_1_10_3_index_manifest: Path | None = typer.Option(None),
    star_index: Path | None = typer.Option(None, exists=True, file_okay=False),
    alignment_profile_id: str = typer.Option(TWO_PASS_PROFILE_ID, "--alignment-profile"),
    quantification_mode: str = typer.Option("recommended-only", "--quantification-mode"),
    primary_quantification_profile: str | None = typer.Option(None, "--primary-quantification-profile"),
    bam_retention: BamRetention | None = typer.Option(None),
    bam_output_mode: BamOutputMode | None = typer.Option(None, "--bam-output-mode"),
    gpu_selection: str = typer.Option("all"),
    memory_mode: MemoryMode = typer.Option(MemoryMode.LOW_MEMORY_CANDIDATE),
    qualification_debug_mode: QualificationDebugMode = typer.Option(QualificationDebugMode.DISABLED),
    save_reference: bool = typer.Option(False),
    skip_pseudo_alignment: bool = typer.Option(False),
    species: str = typer.Option(...),
    assembly: str = typer.Option(...),
    annotation_provider: str = typer.Option(...),
    annotation_release: str = typer.Option(...),
    project_slug: str = typer.Option(...),
    target: str = typer.Option("windows" if __import__("os").name == "nt" else "linux"),
    wsl_distribution: str | None = typer.Option(None),
    host_profile: str = typer.Option(WINDOWS_HOST_PROFILE_ID, "--host-profile"),
    host_receipt: Path | None = typer.Option(None, "--host-receipt", exists=True, dir_okay=False),
    provenance_receipt: Path | None = typer.Option(None, "--parabricks-provenance-receipt", exists=True, dir_okay=False),
    workflow_backend: str | None = typer.Option(
        None,
        "--workflow-backend",
        help=(
            "harako-native-v1 or nfcore-rnaseq-3-26-reference; omit for the "
            "receipt- and evidence-gated host default"
        ),
    ),
) -> None:
    """Create a plan without executing Nextflow."""
    try:
        requested_bam_mode = bam_output_mode or BamOutputMode(
            (bam_retention or BamRetention.KEEP).value
        )
        if bam_retention is not None and bam_output_mode is not None and bam_retention.value != bam_output_mode.value:
            raise ValueError("--bam-retention and --bam-output-mode must agree when both are supplied")
        effective_bam_retention = BamRetention(requested_bam_mode.value)
        installed_host_receipt = HostQualificationReceipt.load(host_receipt) if host_receipt else None
        provenance = load_offline_provenance(provenance_receipt) if provenance_receipt else None
        observed_parabricks = (
            inspect_provenance_image(ProcessRunner(), provenance) if provenance else None
        )
        plan = create_plan(
            samplesheet=samplesheet, plan_dir=plan_dir, output_root=output_root, work_root=work_root,
            fasta=fasta, gtf=gtf, bam_retention=effective_bam_retention, gpu_selection=gpu_selection,
            memory_mode=memory_mode, species=species, assembly=assembly,
            annotation_provider=annotation_provider, annotation_release=annotation_release,
            project_slug=project_slug, target=target, transcript_fasta=transcript_fasta,
            qualification_debug_mode=qualification_debug_mode, save_reference=save_reference,
            skip_pseudo_alignment=skip_pseudo_alignment, salmon_index_manifest=salmon_index_manifest,
            quantification_mode=quantification_mode,
            primary_quantification_profile=primary_quantification_profile,
            salmon_2_5_1_index_manifest=salmon_2_5_1_index_manifest,
            salmon_1_10_3_index_manifest=salmon_1_10_3_index_manifest,
            star_index=star_index,
            alignment_profile_id=alignment_profile_id,
            bam_output_mode=requested_bam_mode,
            wsl_distribution=wsl_distribution,
            host_profile_id=host_profile,
            host_qualification_receipt=installed_host_receipt,
            parabricks_provenance=provenance,
            observed_parabricks_image=observed_parabricks,
            workflow_backend=workflow_backend,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps({"schema_version": 1, "plan_id": plan.plan_id, "plan_dir": str(plan_dir.resolve()), "executed": False}, indent=2))


@plan_app.command("validate")
def validate(plan: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    """Validate a previously created plan."""
    try:
        result = validate_plan_file(plan)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
