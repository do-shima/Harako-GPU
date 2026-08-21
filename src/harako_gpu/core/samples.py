"""Versioned sample structural schema."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Mapping, Sequence

from .fastq import FASTQ_EXTS, read_side, sample_base


SAMPLE_SCHEMA_VERSION = 1
SAMPLE_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
STRANDEDNESS = {"auto", "unstranded", "forward", "reverse"}


@dataclass(frozen=True)
class Sample:
    sample: str
    condition: str
    fastq_1: str
    fastq_2: str = ""
    strandedness: str = "auto"
    library_protocol: str = "unspecified"

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class SampleValidation:
    schema_version: int
    valid: bool
    errors: tuple[str, ...]


def validate_samples(rows: Sequence[Mapping[str, object]]) -> SampleValidation:
    errors: list[str] = []
    seen_samples: set[str] = set()
    seen_fastqs: set[str] = set()
    if not rows:
        errors.append("At least one sample is required.")
    for index, row in enumerate(rows, start=1):
        sample = str(row.get("sample") or "").strip()
        condition = str(row.get("condition") or "").strip()
        fastq_1 = str(row.get("fastq_1") or "").strip()
        fastq_2 = str(row.get("fastq_2") or "").strip()
        strandedness = str(row.get("strandedness") or "auto").strip().lower()
        protocol = str(row.get("library_protocol") or "").strip()
        prefix = f"sample row {index}"
        if not sample or not SAMPLE_ID_RE.fullmatch(sample):
            errors.append(f"{prefix}: invalid sample identifier")
        elif sample in seen_samples:
            errors.append(f"{prefix}: duplicate sample identifier '{sample}'")
        seen_samples.add(sample)
        if not condition:
            errors.append(f"{prefix}: condition is required")
        if not fastq_1:
            errors.append(f"{prefix}: fastq_1 is required")
        elif not fastq_1.lower().endswith(FASTQ_EXTS):
            errors.append(f"{prefix}: unsupported fastq_1 extension")
        if fastq_2 and not fastq_2.lower().endswith(FASTQ_EXTS):
            errors.append(f"{prefix}: unsupported fastq_2 extension")
        if read_side(fastq_1) == "2":
            errors.append(f"{prefix}: fastq_1 is labeled as R2")
        if fastq_2:
            if read_side(fastq_2) != "2":
                errors.append(f"{prefix}: fastq_2 is not labeled as R2")
            if sample_base(fastq_1) != sample_base(fastq_2):
                errors.append(f"{prefix}: FASTQ pair sample hints disagree")
        for fastq in (fastq_1, fastq_2):
            if not fastq:
                continue
            if fastq in seen_fastqs:
                errors.append(f"{prefix}: FASTQ path is assigned more than once")
            seen_fastqs.add(fastq)
        if strandedness not in STRANDEDNESS:
            errors.append(f"{prefix}: invalid strandedness '{strandedness}'")
        if not protocol:
            errors.append(f"{prefix}: library_protocol is required")
    return SampleValidation(SAMPLE_SCHEMA_VERSION, not errors, tuple(sorted(set(errors))))


def rows_for_analysis(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Translate the versioned sample spelling into the unchanged analysis policy spelling."""
    return [
        {
            "sample": row.get("sample"),
            "condition": row.get("condition"),
            "fastq1": row.get("fastq_1"),
            "fastq2": row.get("fastq_2"),
        }
        for row in rows
    ]

