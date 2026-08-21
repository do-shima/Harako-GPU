"""Qualification-only contracts for medium human capacity measurements."""

from __future__ import annotations

import gzip
import math
import os
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO, Iterable


GIB = 1024**3
CAPACITY_LEVELS = (1_000_000, 5_000_000, 10_000_000, 20_000_000)


class CapacityClassification(StrEnum):
    QUALIFIED_COMFORTABLE = "QUALIFIED_COMFORTABLE"
    QUALIFIED_CONSTRAINED = "QUALIFIED_CONSTRAINED"
    RESOURCE_FAILED = "RESOURCE_FAILED"
    NOT_RUN_SAFETY_GATE = "NOT_RUN_SAFETY_GATE"


@dataclass(frozen=True)
class DiskGate:
    total_bytes: int
    free_bytes: int
    estimated_high_water_bytes: int

    @property
    def hard_reserve_bytes(self) -> int:
        return max(30 * GIB, math.ceil(self.total_bytes * 0.15))

    @property
    def remaining_bytes(self) -> int:
        return self.free_bytes - self.estimated_high_water_bytes

    @property
    def passed(self) -> bool:
        return self.remaining_bytes >= self.hard_reserve_bytes


@dataclass(frozen=True)
class ResourceObservation:
    terminal_success: bool
    required_artifacts_valid: bool
    peak_ram_bytes: int
    total_ram_bytes: int
    peak_vram_mib: float
    total_vram_mib: float
    disk_reserve_maintained: bool
    minimum_available_ram_bytes: int | None = None
    low_available_ram_duration_seconds: float = 0.0
    oom_or_cuda_failure: bool = False
    docker_instability: bool = False

    @property
    def ram_fraction(self) -> float:
        return self.peak_ram_bytes / self.total_ram_bytes

    @property
    def vram_fraction(self) -> float:
        return self.peak_vram_mib / self.total_vram_mib


def classify_capacity(value: ResourceObservation) -> CapacityClassification:
    low_available_hard_stop = (
        value.minimum_available_ram_bytes is not None
        and value.minimum_available_ram_bytes < 4 * GIB
        and value.low_available_ram_duration_seconds >= 30
    )
    if (not value.terminal_success or not value.required_artifacts_valid or
            value.oom_or_cuda_failure or value.docker_instability or
            not value.disk_reserve_maintained or value.ram_fraction >= 0.90 or
            value.vram_fraction >= 0.95 or low_available_hard_stop):
        return CapacityClassification.RESOURCE_FAILED
    if value.ram_fraction >= 0.80 or value.vram_fraction >= 0.90:
        return CapacityClassification.QUALIFIED_CONSTRAINED
    return CapacityClassification.QUALIFIED_COMFORTABLE


def may_run_next_scale(value: ResourceObservation) -> bool:
    return (
        classify_capacity(value) is CapacityClassification.QUALIFIED_COMFORTABLE
        and value.peak_ram_bytes < value.total_ram_bytes * 0.80
        and value.peak_vram_mib < value.total_vram_mib * 0.90
    )


def normalize_qname(header: bytes) -> bytes:
    if not header.startswith(b"@"):
        raise ValueError("FASTQ header must start with @")
    token = header[1:].strip().split(maxsplit=1)[0]
    if token.endswith((b"/1", b"/2")):
        token = token[:-2]
    if not token:
        raise ValueError("FASTQ QNAME is empty")
    return token


def _record(handle: BinaryIO) -> tuple[bytes, bytes, bytes, bytes] | None:
    lines = tuple(handle.readline() for _ in range(4))
    if not lines[0]:
        if any(lines[1:]):
            raise ValueError("Truncated FASTQ record")
        return None
    if any(not line for line in lines) or not lines[2].startswith(b"+"):
        raise ValueError("Invalid four-line FASTQ record")
    sequence = lines[1].rstrip(b"\r\n")
    quality = lines[3].rstrip(b"\r\n")
    if not sequence or len(sequence) != len(quality):
        raise ValueError("FASTQ sequence/quality length mismatch")
    return lines  # type: ignore[return-value]


def _gzip_writer(path: Path) -> tuple[BinaryIO, BinaryIO]:
    raw = path.open("xb")
    compressed = gzip.GzipFile(filename="", mode="wb", compresslevel=6, fileobj=raw, mtime=0)
    return raw, compressed


def create_nested_prefix_subset(
    *, source_r1: Path, source_r2: Path, output_r1: Path, output_r2: Path, pairs: int,
) -> int:
    """Stream exactly the first ``pairs`` records into deterministic gzip files."""
    if pairs < 1:
        raise ValueError("pairs must be positive")
    if output_r1.exists() or output_r2.exists():
        raise ValueError("Refusing to overwrite a capacity subset")
    output_r1.parent.mkdir(parents=True, exist_ok=True)
    output_r2.parent.mkdir(parents=True, exist_ok=True)
    temp_paths: list[Path] = []
    try:
        for output in (output_r1, output_r2):
            descriptor, name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
            os.close(descriptor)
            Path(name).unlink()
            temp_paths.append(Path(name))
        with gzip.open(source_r1, "rb") as left, gzip.open(source_r2, "rb") as right:
            raw1, writer1 = _gzip_writer(temp_paths[0])
            raw2, writer2 = _gzip_writer(temp_paths[1])
            try:
                count = 0
                while count < pairs:
                    record1, record2 = _record(left), _record(right)
                    if record1 is None or record2 is None:
                        raise ValueError(f"Source ended before {pairs} pairs")
                    if normalize_qname(record1[0]) != normalize_qname(record2[0]):
                        raise ValueError(f"R1/R2 QNAME mismatch at pair {count + 1}")
                    writer1.writelines(record1)
                    writer2.writelines(record2)
                    count += 1
            finally:
                writer1.close(); raw1.close(); writer2.close(); raw2.close()
        os.replace(temp_paths[0], output_r1)
        os.replace(temp_paths[1], output_r2)
        return count
    finally:
        for path in temp_paths:
            if path.exists():
                path.unlink()


def validate_paired_fastq(r1: Path, r2: Path, *, expected_pairs: int | None = None) -> dict[str, object]:
    count = 0
    lengths: set[int] = set()
    with gzip.open(r1, "rb") as left, gzip.open(r2, "rb") as right:
        while True:
            record1, record2 = _record(left), _record(right)
            if record1 is None and record2 is None:
                break
            if record1 is None or record2 is None:
                raise ValueError("Orphan FASTQ record")
            if normalize_qname(record1[0]) != normalize_qname(record2[0]):
                raise ValueError(f"R1/R2 QNAME mismatch at pair {count + 1}")
            lengths.update((len(record1[1].rstrip()), len(record2[1].rstrip())))
            count += 1
    if expected_pairs is not None and count != expected_pairs:
        raise ValueError(f"Expected {expected_pairs} pairs, observed {count}")
    return {"paired_fragments": count, "read_lengths": sorted(lengths), "orphans": 0}


def observed_ratio_estimate(
    *, requested_pairs: int, observations: Iterable[tuple[int, int]], fixed_bytes: int = 0,
) -> dict[str, object]:
    rows = sorted((int(pairs), int(size)) for pairs, size in observations)
    if not rows or requested_pairs < 1 or fixed_bytes < 0:
        raise ValueError("Estimator inputs are invalid")
    tested = rows[0][0] <= requested_pairs <= rows[-1][0]
    nearest = min(rows, key=lambda row: abs(row[0] - requested_pairs))
    variable = max(0, nearest[1] - fixed_bytes)
    estimate = fixed_bytes + math.ceil(variable * requested_pairs / nearest[0])
    return {
        "requested_pairs": requested_pairs,
        "estimated_bytes": estimate,
        "basis_pairs": nearest[0],
        "fixed_bytes": fixed_bytes,
        "status": "OBSERVED_RANGE_DESCRIPTIVE" if tested else "EXTRAPOLATED_UNQUALIFIED",
        "confidence": "descriptive_piecewise_ratio_only",
    }


def select_paired_orientation(
    compatible_counts: dict[str, int], *, minimum_consistency: float = 0.8, minimum_margin: float = 0.2,
) -> dict[str, object]:
    """Select paired orientation against the shared unstranded fragment universe."""
    if set(compatible_counts) != {"IU", "ISF", "ISR"} or any(value < 1 for value in compatible_counts.values()):
        raise ValueError("IU, ISF, and ISR orientation-compatible counts are required")
    denominator = compatible_counts["IU"]
    proportions = {key: value / denominator for key, value in compatible_counts.items()}
    ranked = sorted(proportions, key=lambda key: (-proportions[key], key))
    margin = proportions[ranked[0]] - proportions[ranked[1]]
    passed = proportions[ranked[0]] >= minimum_consistency and margin >= minimum_margin
    return {
        "proportions": proportions,
        "selected_salmon_libtype": ranked[0] if passed else None,
        "selected_product_library_type": "U" if passed and ranked[0] == "IU" else ranked[0] if passed else None,
        "margin": margin,
        "status": "PASS" if passed else "UNKNOWN_LIBRARY_TYPE",
        "denominator": "IU num_assigned_fragments (unstranded shared orientation universe)",
    }
