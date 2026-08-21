"""Pure presentation mappings; scientific eligibility remains in services."""

from __future__ import annotations

from typing import Any, Mapping


CAPABILITY_LABEL = {
    "AVAILABLE_QUALIFIED": "available",
    "AVAILABLE_WITH_LIMITATION": "limited",
    "CANDIDATE_REQUIRES_RUNTIME_QUALIFICATION": "unqualified",
    "UNSUPPORTED_HOST_MEMORY": "unavailable",
    "UNSUPPORTED_REFERENCE_PROFILE": "unavailable",
    "NOT_QUALIFIED": "unqualified",
    "BLOCKED_IDENTITY_MISMATCH": "unavailable",
}


def capability_view(result: Mapping[str, Any]) -> dict[str, Any]:
    status = str(result.get("status", "NOT_QUALIFIED"))
    return {
        "status": status,
        "label_key": CAPABILITY_LABEL.get(status, "unqualified"),
        "available": status in {"AVAILABLE_QUALIFIED", "AVAILABLE_WITH_LIMITATION"},
        "gpu_used": bool(result.get("gpu_used")),
        "bam_generated": bool(result.get("bam_generated")),
        "reason": result.get("explanation", ""),
        "evidence": result.get("technical_evidence", ()),
        "allowed_next_actions": result.get("allowed_next_actions", ()),
    }


def human_bytes(value: int | float | None) -> str:
    if value is None:
        return "—"
    number = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(number) < 1024 or unit == "TiB":
            return f"{number:.2f} {unit}"
        number /= 1024
    return "—"


def stage_progress(status: Mapping[str, Any]) -> float:
    stages = list(status.get("stages") or [])
    if not stages:
        return 1.0 if status.get("state") in {"COMPLETED", "COMPLETED_WITH_LIMITATION"} else 0.0
    done = sum(1 for stage in stages if stage.get("state") in {"SUCCEEDED", "CACHED", "NOT_APPLICABLE"})
    return min(1.0, done / len(stages))


def result_generation_summary(identity: Mapping[str, Any],
                              artifacts: list[Mapping[str, Any]]) -> dict[str, tuple[str, ...]]:
    """Summarize route outcomes without re-evaluating scientific eligibility."""
    present_roles = {
        str(item.get("role")) for item in artifacts
        if item.get("state") in {"PRESENT", "VALIDATED"}
    }
    generated: list[str] = []
    groups = (
        (("processed_fastq_r1", "processed_fastq_r2"), "artifact.processed_fastq"),
        (("matrix_transcript_counts",), "artifact.transcript_counts"),
        (("matrix_transcript_tpm",), "artifact.transcript_tpm"),
        (("matrix_gene_counts",), "artifact.gene_counts"),
        (("matrix_gene_tpm",), "artifact.gene_tpm"),
        (("self_contained_report",), "artifact.report"),
        (("concordance_manifest", "profile_comparison"), "artifact.concordance"),
        (("genomic_bam", "genomic_bai"), "artifact.bam_bai"),
        (("star_junction",), "artifact.junctions"),
        (("star_reads_per_gene", "star_selected_counts"), "artifact.star_counts"),
        (("multiqc_report",), "artifact.multiqc"),
    )
    for roles, label in groups:
        if any(role in present_roles for role in roles):
            generated.append(label)
    route = str(identity.get("execution_route", ""))
    not_generated = ()
    if route == "fastq_quantification_only":
        not_generated = ("artifact.bam_bai", "artifact.junctions", "artifact.star_counts",
                         "artifact.multiqc", "artifact.gpu_evidence")
    return {"generated": tuple(generated), "not_generated": not_generated}
