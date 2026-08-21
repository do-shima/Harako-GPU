"""Measure SIRV502 coverage with the pinned diagnostic minimap2 profile."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
from pathlib import Path


IMAGE = "quay.io/biocontainers/minimap2@sha256:0c397895db3b494baa4f78de7110d516a1a57707d9c7df456634220bffd965ba"
CIGAR = re.compile(r"(\d+)([MIDNSHP=X])")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.runtime_root.resolve()
    sequence = None
    current = None
    parts: list[str] = []
    for line in (root / "references/external-v2/sirv69.fa").read_text().splitlines():
        if line.startswith(">"):
            if current == "SIRV502":
                sequence = "".join(parts)
                break
            current, parts = line[1:].split()[0], []
        else:
            parts.append(line.strip())
    if sequence is None and current == "SIRV502":
        sequence = "".join(parts)
    if not sequence:
        raise ValueError("SIRV502 reference missing")
    coverage = [0] * len(sequence)
    argv = [
        "docker", "run", "--rm", "-v", f"{root}:/runtime:ro", IMAGE,
        "minimap2", "-x", "sr", "-a", "--secondary=no", "-t", "2",
        "/runtime/references/external-v2/sirv69.fa",
        "/runtime/runs/preprocessing/SRR3497201/repeat-1/SRR3497201_R1.fastq.gz",
        "/runtime/runs/preprocessing/SRR3497201/repeat-1/SRR3497201_R2.fastq.gz",
    ]
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    aligned_records = 0
    assert process.stdout is not None
    for line in process.stdout:
        if line.startswith("@"):
            continue
        fields = line.rstrip("\n").split("\t")
        if len(fields) < 11 or fields[2] != "SIRV502":
            continue
        aligned_records += 1
        reference_position = int(fields[3]) - 1
        for length_text, operation in CIGAR.findall(fields[5]):
            length = int(length_text)
            if operation in "M=X":
                for position in range(reference_position, min(reference_position + length, len(coverage))):
                    coverage[position] += 1
                reference_position += length
            elif operation in "DN":
                reference_position += length
    stderr = process.stderr.read() if process.stderr is not None else ""
    returncode = process.wait()
    if returncode:
        raise RuntimeError(f"minimap2 failed: {stderr[-1000:]}")
    quartile = len(coverage) // 4
    windows = {
        "first": coverage[:quartile], "second": coverage[quartile:2 * quartile],
        "third": coverage[2 * quartile:3 * quartile], "fourth": coverage[3 * quartile:],
    }
    mean = statistics.fmean(coverage)
    report = {
        "schema_version": 1,
        "target": "SIRV502",
        "reference_length": len(coverage),
        "aligned_records": aligned_records,
        "mean_coverage": mean,
        "coverage_cv": statistics.pstdev(coverage) / mean if mean else None,
        "zero_coverage_fraction": sum(value == 0 for value in coverage) / len(coverage),
        "minimum_coverage": min(coverage),
        "maximum_coverage": max(coverage),
        "quartile_mean_coverage": {name: statistics.fmean(values) for name, values in windows.items()},
        "official_affected_interval": "NOT_SPECIFIED_IN_BATCH_AMENDMENT",
        "image": IMAGE,
    }
    args.output.resolve().write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
