"""Versioned contract display command."""

import json

import typer

from harako_gpu.core.artifacts import ArtifactType, BamState, DISCARD_GATES
from harako_gpu.adapters.nextflow import build_nextflow_environment
from harako_gpu.core.contracts import (
    BamRetention, MemoryMode, MINIMUM_JAVA_MAJOR, MINIMUM_NEXTFLOW_VERSION,
    PARABRICKS_CONTAINER_VERSION, QUALIFIED_NEXTFLOW_VERSION,
    minimal_feasibility_profile, qualified_backend_profile,
)


contract_app = typer.Typer(help="Show versioned product contracts.", add_completion=False)


@contract_app.command("show")
def show() -> None:
    """Show the fixed backend and artifact contracts."""
    profiles = [
        qualified_backend_profile(bam_retention=retention, gpu_selection="all", memory_mode=MemoryMode.STANDARD).as_dict()
        for retention in BamRetention
    ]
    typer.echo(json.dumps({
        "schema_version": 1,
        "profiles": profiles,
        "initial_feasibility_profile": minimal_feasibility_profile().as_dict(),
        "minimum_java_major": MINIMUM_JAVA_MAJOR,
        "minimum_nextflow_version": MINIMUM_NEXTFLOW_VERSION,
        "qualified_nextflow_version": QUALIFIED_NEXTFLOW_VERSION,
        "nextflow_environment": build_nextflow_environment(),
        "parabricks_container_version": PARABRICKS_CONTAINER_VERSION,
        "artifact_types": [item.value for item in ArtifactType],
        "bam_states": [item.value for item in BamState],
        "discard_gates": list(DISCARD_GATES),
        "bam_deletion_implemented": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
