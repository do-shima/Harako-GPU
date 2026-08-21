"""Structured WSL bioinformatics artifact validation commands."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from harako_gpu.adapters.docker import DockerImageContract
from harako_gpu.adapters.execution_context import ExecutionContext
from harako_gpu.adapters.filesystem import require_safe_linux_runtime_path
from harako_gpu.adapters.process import ProcessRunner


LEGACY_WSL_UTILITY_SAMTOOLS_IMAGE_ID = (
    "sha256:6df2a43541963ac73551a79c48bf2dbd743b37ab8dd1bdec364de1d6bc8cd7f0"
)
LEGACY_WSL_UTILITY_SAMTOOLS_CONTRACT = DockerImageContract(
    "quay.io/biocontainers/samtools:1.20--h50ea8bc_1",
    LEGACY_WSL_UTILITY_SAMTOOLS_IMAGE_ID,
    "image_id",
)


@dataclass(frozen=True)
class BamValidation:
    quickcheck: bool
    coordinate_sorted: bool
    has_sq: bool
    has_read_group: bool
    checksum: str | None
    flagstat: str
    idxstats: str

    @property
    def valid(self) -> bool:
        return self.quickcheck and self.coordinate_sorted and self.has_sq and self.has_read_group and bool(self.checksum)


def validate_bam(
    *,
    bam: str,
    bai: str,
    execution: ExecutionContext,
    image_contract: DockerImageContract | None = None,
    runner: ProcessRunner | None = None,
) -> BamValidation:
    bam = require_safe_linux_runtime_path(bam)
    bai = require_safe_linux_runtime_path(bai)
    bam_path, bai_path = PurePosixPath(bam), PurePosixPath(bai)
    if bam_path.parent != bai_path.parent:
        raise ValueError("BAM and BAI must share one validated artifact directory")
    contract = image_contract or LEGACY_WSL_UTILITY_SAMTOOLS_CONTRACT
    contract.validate()
    process = runner or ProcessRunner()
    transport = (() if execution.is_native_linux else
                 ("wsl.exe", "--distribution", str(execution.distribution), "--exec"))
    prefix = (*transport,
        "docker", "run", "--rm", "--pull=never",
        "--mount", f"type=bind,src={bam_path.parent},dst=/data,readonly",
        contract.execution_reference, "samtools",
    )
    return _validate_bam(prefix=prefix, bam_path=bam_path, process=process)


def _validate_bam(*, prefix: tuple[str, ...], bam_path: PurePosixPath,
                  process: ProcessRunner) -> BamValidation:
    container_bam = f"/data/{bam_path.name}"
    quick = process.run((*prefix, "quickcheck", "-v", container_bam), timeout=30)
    header = process.run((*prefix, "view", "-H", container_bam), timeout=30)
    checksum = process.run((*prefix, "checksum", "-a", container_bam), timeout=120)
    flagstat = process.run((*prefix, "flagstat", container_bam), timeout=120)
    idxstats = process.run((*prefix, "idxstats", container_bam), timeout=120)
    text = header.stdout
    return BamValidation(
        quick.ok, header.ok and any(line.startswith("@HD") and "SO:coordinate" in line for line in text.splitlines()),
        header.ok and any(line.startswith("@SQ") for line in text.splitlines()),
        header.ok and any(line.startswith("@RG") for line in text.splitlines()),
        checksum.stdout.strip() if checksum.ok else None,
        flagstat.stdout if flagstat.ok else "", idxstats.stdout if idxstats.ok else "",
    )
