"""Reference-aware capability inspection CLI."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from harako_gpu.core.capabilities import BamOutputMode
from harako_gpu.services.capabilities import (
    FULL_HUMAN_REFERENCE_PACK_ID, FULL_HUMAN_SHA, SMALL_REFERENCE_PACK_ID, SMALL_REFERENCE_SHA,
    capability_matrix, evaluate_capability, high_memory_handoff, write_handoff,
)
from harako_gpu.adapters.process import ProcessRunner
from harako_gpu.services.host_profiles import (
    HOST_PROFILES, WINDOWS_HOST_PROFILE_ID,
    HostQualificationReceipt, OfflinePlatformImageProvenance,
    inspect_provenance_image, load_offline_provenance,
)
from harako_gpu.services.workflow_backends import NFCORE_REFERENCE_PUBLIC, parse_workflow_backend


capabilities_app = typer.Typer(help="Inspect fixed host/reference execution capabilities.", add_completion=False)


def _emit(payload: dict, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if "entries" in payload:
        for key, item in payload["entries"].items():
            typer.echo(f"{key}\t{item['status']}\tGPU={str(item['gpu_used']).lower()}\tBAM={str(item['bam_generated']).lower()}")
    else:
        typer.echo(f"Status: {payload['status']}")
        typer.echo(f"Route: {payload['requested_route']}")
        typer.echo(f"GPU used: {str(payload['gpu_used']).lower()}")
        typer.echo(f"BAM generated: {str(payload['bam_generated']).lower()}")
        typer.echo(f"Reason: {payload['explanation']}")


def _backend_payload(payload: dict, requested: str) -> dict:
    backend = parse_workflow_backend(requested)
    return {
        **payload,
        "workflow_backend": backend.workflow_backend,
        "workflow_backend_qualification_state": backend.qualification_state,
        "supported_alignment_adapters": list(backend.supported_alignment_backends),
        "workflow_backend_limitations": list(backend.limitations),
    }


@capabilities_app.command("inspect")
def inspect(json_output: bool = typer.Option(False, "--json"),
            workflow_backend: str = typer.Option(NFCORE_REFERENCE_PUBLIC, "--workflow-backend")) -> None:
    payload = capability_matrix()
    payload["host_profiles"] = {key: value.as_dict() for key, value in HOST_PROFILES.items()}
    _emit(_backend_payload(payload, workflow_backend), json_output)


def _installed_evidence(
    host_receipt: Path | None, provenance_receipt: Path | None,
) -> tuple[HostQualificationReceipt | None, OfflinePlatformImageProvenance | None, dict | None]:
    receipt = HostQualificationReceipt.load(host_receipt) if host_receipt else None
    provenance = None
    inspected = None
    if provenance_receipt:
        try:
            provenance = load_offline_provenance(provenance_receipt)
            inspected = dict(inspect_provenance_image(ProcessRunner(), provenance))
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
    return receipt, provenance, inspected


@capabilities_app.command("matrix")
def matrix(json_output: bool = typer.Option(False, "--json"),
           host_profile: str = typer.Option(WINDOWS_HOST_PROFILE_ID, "--host-profile"),
           execution_context: str = typer.Option("wsl2:Ubuntu", "--execution-context"),
           host_receipt: Path | None = typer.Option(None, "--host-receipt", exists=True, dir_okay=False),
           provenance_receipt: Path | None = typer.Option(None, "--parabricks-provenance-receipt", exists=True, dir_okay=False),
           workflow_backend: str = typer.Option(NFCORE_REFERENCE_PUBLIC, "--workflow-backend")) -> None:
    receipt, provenance, inspected = _installed_evidence(host_receipt, provenance_receipt)
    _emit(_backend_payload(capability_matrix(
        host_profile_id=host_profile, execution_context=execution_context,
        host_receipt=receipt, parabricks_provenance=provenance,
        observed_parabricks_image=inspected,
    ), workflow_backend), json_output)


@capabilities_app.command("explain")
def explain(reference_pack: str = typer.Option(..., "--reference-pack"),
            bam_mode: BamOutputMode = typer.Option(..., "--bam-mode"),
            alignment_profile: str | None = typer.Option(None, "--alignment-profile"),
            quantification_mode: str = typer.Option("recommended-only", "--quantification-mode"),
            host_profile: str = typer.Option(WINDOWS_HOST_PROFILE_ID, "--host-profile"),
            execution_context: str = typer.Option("wsl2:Ubuntu", "--execution-context"),
            host_receipt: Path | None = typer.Option(None, "--host-receipt", exists=True, dir_okay=False),
            provenance_receipt: Path | None = typer.Option(None, "--parabricks-provenance-receipt", exists=True, dir_okay=False),
            workflow_backend: str = typer.Option(NFCORE_REFERENCE_PUBLIC, "--workflow-backend"),
            json_output: bool = typer.Option(False, "--json")) -> None:
    if reference_pack == FULL_HUMAN_REFERENCE_PACK_ID:
        reference = {**FULL_HUMAN_SHA, "reference_pack_id": reference_pack}
    elif reference_pack == SMALL_REFERENCE_PACK_ID:
        reference = {**SMALL_REFERENCE_SHA, "reference_pack_id": reference_pack}
    else:
        reference = {"reference_pack_id": reference_pack}
    secondary = "salmon_1_10_3_compatibility" if quantification_mode.replace("-", "_") == "compare_both" else None
    receipt, provenance, inspected = _installed_evidence(host_receipt, provenance_receipt)
    result = evaluate_capability(reference=reference, bam_output_mode=bam_mode,
        alignment_profile_id=alignment_profile, quantification_mode=quantification_mode.replace("-", "_"),
        primary_profile_id="salmon_2_5_1_deterministic", secondary_profile_id=secondary,
        host_profile_id=host_profile, execution_context=execution_context,
        host_receipt=receipt, parabricks_provenance=provenance,
        observed_parabricks_image=inspected)
    _emit(_backend_payload(result.as_dict(), workflow_backend), json_output)


@capabilities_app.command("export-handoff")
def export_handoff(output: Path | None = typer.Option(None, "--output"),
                   json_output: bool = typer.Option(False, "--json")) -> None:
    payload = write_handoff(output) if output else high_memory_handoff()
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if json_output or not output else str(output.resolve()))
