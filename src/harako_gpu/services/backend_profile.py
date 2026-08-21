"""Fixed nf-core/rnaseq 3.26.0 parameter and config generation."""

from __future__ import annotations

import re
from typing import Any

from harako_gpu.core.contracts import (
    MINIMAL_FEASIBILITY_RESOURCE_CPUS,
    MINIMAL_FEASIBILITY_RESOURCE_MEMORY,
    MINIMAL_FEASIBILITY_RESOURCE_TIME,
    BackendProfile,
    BamRetention,
    MemoryMode,
    QualificationDebugMode,
)


NF_PARAM_KEYS = frozenset({
    "input", "outdir", "fasta", "gtf", "aligner", "use_parabricks_star", "save_align_intermeds",
    "extra_star_align_args", "skip_markduplicates", "transcript_fasta", "save_reference",
    "skip_pseudo_alignment", "pseudo_aligner", "salmon_index", "salmon_quant_libtype",
    "trimmer", "save_trimmed",
    "star_index",
    "featurecounts_feature_type", "featurecounts_group_type",
})
REQUIRED_NF_PARAM_KEYS = frozenset({
    "input", "outdir", "fasta", "gtf", "aligner", "use_parabricks_star", "save_align_intermeds",
    "skip_markduplicates",
})
GPU_SELECTION_RE = re.compile(r"^(?:all|(?:[0-9]+|GPU-[A-Za-z0-9-]+)(?:,(?:[0-9]+|GPU-[A-Za-z0-9-]+))*)$")


def validate_gpu_selection(value: str) -> str:
    selection = value.strip()
    if not GPU_SELECTION_RE.fullmatch(selection):
        raise ValueError("gpu_selection must be 'all' or a comma-separated list of GPU indices/UUIDs")
    return selection


def build_nf_params(
    profile: BackendProfile,
    *,
    samplesheet: str,
    outdir: str,
    fasta: str,
    gtf: str,
    transcript_fasta: str | None = None,
    save_reference: bool = False,
    skip_pseudo_alignment: bool = False,
    star_index: str | None = None,
) -> dict[str, Any]:
    profile.validate()
    if not fasta:
        raise ValueError("FASTA is required")
    if not gtf:
        raise ValueError("GTF is required")
    params: dict[str, Any] = {
        "aligner": "star_salmon",
        "fasta": fasta,
        "gtf": gtf,
        "input": samplesheet,
        "outdir": outdir,
        "save_align_intermeds": True,
        "save_reference": save_reference,
        "skip_markduplicates": profile.memory_mode is MemoryMode.LOW_MEMORY_CANDIDATE,
        "skip_pseudo_alignment": skip_pseudo_alignment,
        "use_parabricks_star": True,
    }
    if transcript_fasta:
        params["transcript_fasta"] = transcript_fasta
    if star_index:
        params["star_index"] = star_index
    if profile.memory_mode is MemoryMode.LOW_MEMORY_CANDIDATE:
        params["extra_star_align_args"] = (
            "--low-memory --x3"
            if profile.qualification_debug_mode is QualificationDebugMode.X3
            else "--low-memory"
        )
    return params


def validate_nf_params(params: dict[str, Any]) -> None:
    extras = sorted(set(params) - NF_PARAM_KEYS)
    if extras:
        raise ValueError("Arbitrary nf-core parameters are forbidden: " + ", ".join(extras))
    if "genome" in params:
        raise ValueError("--genome is forbidden for the Parabricks profile")
    required = REQUIRED_NF_PARAM_KEYS
    missing = sorted(key for key in required if key not in params or params[key] in (None, ""))
    if missing:
        raise ValueError("Missing required nf-core parameters: " + ", ".join(missing))
    if params["aligner"] != "star_salmon" or params["use_parabricks_star"] is not True:
        raise ValueError("Silent CPU fallback is forbidden")
    if params["save_align_intermeds"] is not True:
        raise ValueError("Alignment BAM generation must remain enabled for both retention policies")
    if not isinstance(params["skip_markduplicates"], bool):
        raise ValueError("skip_markduplicates must be a fixed boolean")
    for key in ("save_reference", "skip_pseudo_alignment"):
        if key in params and not isinstance(params[key], bool):
            raise ValueError(f"{key} must be a fixed boolean")
    independent = params.get("pseudo_aligner") == "salmon"
    if independent:
        expected = {
            "skip_pseudo_alignment": False,
            "salmon_quant_libtype": "ISR",
            "trimmer": "fastp",
            "save_trimmed": True,
        }
        for key, value in expected.items():
            if params.get(key) != value:
                raise ValueError(f"Independent FASTQ Salmon requires {key}={value!r}")
        if not str(params.get("salmon_index") or "").strip():
            raise ValueError("Independent FASTQ Salmon requires a pinned Salmon index")
    if "extra_star_align_args" in params and params["extra_star_align_args"] not in {
        "--low-memory", "--low-memory --x3",
        "--low-memory --quantMode TranscriptomeSAM GeneCounts",
        "--low-memory --x3 --quantMode TranscriptomeSAM GeneCounts",
        "--low-memory --quantMode TranscriptomeSAM GeneCounts --sjdb-overhang 74",
        "--low-memory --x3 --quantMode TranscriptomeSAM GeneCounts --sjdb-overhang 74",
        "--low-memory --quantMode TranscriptomeSAM GeneCounts --sjdb-overhang 74 --two-pass-mode None",
        "--low-memory --quantMode TranscriptomeSAM GeneCounts --sjdb-overhang 74 --two-pass-mode Basic",
        "--low-memory --x3 --quantMode TranscriptomeSAM GeneCounts --sjdb-overhang 74 --two-pass-mode None",
        "--low-memory --x3 --quantMode TranscriptomeSAM GeneCounts --sjdb-overhang 74 --two-pass-mode Basic",
        "--low-memory --quantMode TranscriptomeSAM GeneCounts --sjdb-overhang 100 --two-pass-mode None",
        "--low-memory --quantMode TranscriptomeSAM GeneCounts --sjdb-overhang 100 --two-pass-mode Basic",
        "--low-memory --x3 --quantMode TranscriptomeSAM GeneCounts --sjdb-overhang 100 --two-pass-mode None",
        "--low-memory --x3 --quantMode TranscriptomeSAM GeneCounts --sjdb-overhang 100 --two-pass-mode Basic",
    }:
        raise ValueError("extra_star_align_args is restricted to qualified fixed mappings")


def config_fragment(profile: BackendProfile, *, independent_fastq_salmon: bool = False) -> str:
    selection = validate_gpu_selection(profile.gpu_selection)
    gpu_options = "--gpus all" if selection == "all" else f'--gpus "device={selection}"'
    memory_comment = (
        "// low_memory_candidate uses the fixed --low-memory mapping in nf-params.json; it remains unqualified."
        if profile.memory_mode is MemoryMode.LOW_MEMORY_CANDIDATE
        else "// standard memory plan; actual resources remain subject to preflight."
    )
    resource_limits = ""
    if profile.qualification_debug_mode is QualificationDebugMode.X3:
        resource_limits = (
            "process {\n"
            "    // Mirrors the bounded nf-core test_gpu scheduling envelope; not a host qualification claim.\n"
            "    resourceLimits = [\n"
            f"        cpus: {MINIMAL_FEASIBILITY_RESOURCE_CPUS},\n"
            f"        memory: '{MINIMAL_FEASIBILITY_RESOURCE_MEMORY}',\n"
            f"        time: '{MINIMAL_FEASIBILITY_RESOURCE_TIME}'\n"
            "    ]\n"
            "}\n"
        )
    quantification = ""
    if independent_fastq_salmon:
        from harako_gpu.services.independent_fastq_salmon import independent_fastq_salmon_config

        quantification = independent_fastq_salmon_config()
    return (
        "// Generated by Harako-GPU. Do not treat this as scientific qualification.\n"
        f"{memory_comment}\n"
        f"params.gpu_container_options = '{gpu_options}'\n"
        f"{resource_limits}"
        "docker {\n"
        "    enabled = true\n"
        "}\n"
        f"{quantification}"
    )


def retention_warnings(retention: BamRetention) -> list[str]:
    if retention is BamRetention.NONE:
        return ["BAM/BAI, junction, STAR GeneCounts, and alignment QC are NOT_APPLICABLE in FASTQ quantification-only mode."]
    if retention is BamRetention.DISCARD_AFTER_VALIDATION:
        return [
            "BAM discard is contract-only in this foundation; no deletion will be performed.",
            "Published genomic BAM/BAI must remain until all eleven validation gates and terminal success are recorded.",
        ]
    return ["Genomic BAM/BAI and verification results are planned as retained final artifacts."]
