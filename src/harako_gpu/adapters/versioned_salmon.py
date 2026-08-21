"""Symmetric Docker execution adapter for the two fixed Salmon profiles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from harako_gpu.adapters.process import CommandResult, ProcessRunner
from harako_gpu.services.concordance import parse_quant_sf
from harako_gpu.services.quantification_profiles import (
    ProcessedFastqPair, ProfileIndex, get_profile, salmon_argv,
)


@dataclass(frozen=True)
class VersionedSalmonRequest:
    profile_id: str
    fastq: ProcessedFastqPair
    index: ProfileIndex
    gene_map: Path
    output: Path

    def validate(self) -> None:
        self.fastq.validate()
        self.index.validate()
        if self.index.profile_id != self.profile_id:
            raise ValueError("Execution profile and index identity mismatch")
        if not self.gene_map.is_file() or self.output.exists():
            raise ValueError("Gene map must exist and output must be a new path")


def docker_argv(request: VersionedSalmonRequest) -> tuple[str, ...]:
    request.validate()
    profile = get_profile(request.profile_id)
    index_path = Path(request.index.path)
    r1, r2 = Path(request.fastq.r1_path), Path(request.fastq.r2_path)
    if not index_path.is_dir() or not r1.is_file() or not r2.is_file():
        raise ValueError("Pinned index and processed FASTQ inputs must exist")
    mounts = ((index_path, "/input/index", True), (r1, "/input/reads/R1.fastq.gz", True),
              (r2, "/input/reads/R2.fastq.gz", True), (request.gene_map, "/input/reference/tx2gene.gtf", True),
              (request.output.parent, "/output", False))
    argv = ["docker", "run", "--rm"]
    for source, target, readonly in mounts:
        option = f"type=bind,src={source.resolve()},dst={target}"
        argv += ["--mount", option + (",readonly" if readonly else "")]
    execution_image = (
        profile.image_identity if profile.image_reference.startswith("harako-gpu/")
        else f"{profile.image_reference}@{profile.image_identity}"
    )
    argv += [execution_image]
    argv += salmon_argv(
        request.profile_id, index="/input/index", gene_map="/input/reference/tx2gene.gtf",
        r1="/input/reads/R1.fastq.gz", r2="/input/reads/R2.fastq.gz",
        output=f"/output/{request.output.name}", library_type=request.fastq.library_type,
    )
    return tuple(argv)


def execution_metadata(request: VersionedSalmonRequest, argv: tuple[str, ...]) -> dict[str, object]:
    """Return the fixed profile/input identities written beside quantification output."""
    profile = get_profile(request.profile_id)
    return {
        "schema_version": 1,
        "profile_id": request.profile_id,
        "version": profile.version,
        "image_reference": profile.image_reference,
        "image_identity": profile.image_identity,
        "index_id": request.index.index_id,
        "index_manifest_sha256": request.index.manifest_sha256,
        "sample_id": request.fastq.sample_id,
        "processed_fastq": {
            "r1_sha256": request.fastq.r1_sha256,
            "r2_sha256": request.fastq.r2_sha256,
            "paired_fragments": request.fastq.paired_fragments,
            "preprocessing_contract_id": request.fastq.preprocessing_contract_id,
        },
        "library_type": request.fastq.library_type,
        "structured_argv": list(argv),
    }


def run_sequential(requests: tuple[VersionedSalmonRequest, ...], *, timeout: float,
                   runner: ProcessRunner | None = None) -> Mapping[str, CommandResult]:
    if len({request.profile_id for request in requests}) != len(requests):
        raise ValueError("Each profile may execute at most once per sample")
    executor = runner or ProcessRunner()
    results: dict[str, CommandResult] = {}
    for request in requests:
        argv = docker_argv(request)
        result = executor.run(argv, timeout=timeout)
        results[request.profile_id] = result
        quant = request.output / "quant.sf"
        if not result.ok or not quant.is_file() or quant.stat().st_size == 0:
            raise RuntimeError(f"Incomplete Salmon output for {request.profile_id}")
        parse_quant_sf(quant.read_text(encoding="utf-8"))
        metadata = execution_metadata(request, argv)
        metadata.update({"returncode": result.returncode, "timed_out": result.timed_out})
        (request.output / "command.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        (request.output / "versions.json").write_text(
            json.dumps({"salmon": get_profile(request.profile_id).version,
                        "image_identity": get_profile(request.profile_id).image_identity},
                       indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        (request.output / "input_manifest.json").write_text(
            json.dumps(metadata["processed_fastq"], indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        (request.output / "stderr.log").write_text(result.stderr, encoding="utf-8")
    return results
