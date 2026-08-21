"""Pinned Nextflow command construction."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import PureWindowsPath
from typing import Mapping, Sequence

from harako_gpu.core.contracts import QUALIFIED_NEXTFLOW_VERSION


def build_nextflow_argv(*, samplesheet: str, outdir: str, fasta: str, gtf: str,
                        params_file: str, work_dir: str) -> list[str]:
    if any(not value for value in (samplesheet, outdir, fasta, gtf, params_file, work_dir)):
        raise ValueError("samplesheet, outdir, fasta, gtf, params_file, and work_dir are required")
    return [
        "nextflow", "run", "nf-core/rnaseq", "-r", "3.26.0", "-profile", "docker",
        "--aligner", "star_salmon", "--use_parabricks_star", "--input", samplesheet,
        "--outdir", outdir, "--fasta", fasta, "--gtf", gtf, "-params-file", params_file,
        "-work-dir", work_dir,
    ]


def build_nextflow_environment() -> dict[str, str]:
    """Return the qualified launcher environment without creating a shell command."""
    return {"NXF_VER": QUALIFIED_NEXTFLOW_VERSION}


def quote_argv(argv: Sequence[str], *, target: str) -> str:
    if target == "windows":
        return subprocess.list2cmdline(list(argv))
    if target in {"linux", "wsl"}:
        return shlex.join(argv)
    raise ValueError("target must be windows, linux, or wsl")


def is_windows_path(value: str) -> bool:
    return bool(PureWindowsPath(value).drive)


def reject_mixed_path_context(paths: Mapping[str, str], *, target: str) -> None:
    windows = [name for name, value in paths.items() if is_windows_path(value)]
    if target in {"linux", "wsl"} and windows:
        raise ValueError("Windows paths require explicit WSL conversion before Linux/WSL planning: " + ", ".join(windows))
