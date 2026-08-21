"""Read-only FASTQ filename inspection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harako_gpu.core.fastq import FASTQ_EXTS, infer_pair_candidates, read_side, relative_path, sample_base
from harako_gpu.core.provenance import response


def inspect_input(root: Path) -> dict[str, Any]:
    source = root.expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"Input directory does not exist: {source}")
    paths = sorted(path for path in source.rglob("*") if path.is_file() and path.name.lower().endswith(FASTQ_EXTS))
    relatives = [relative_path(path, source) for path in paths]
    available = set(relatives)
    unresolved: list[str] = []
    items: list[dict[str, Any]] = []
    for path, relative in zip(paths, relatives):
        mates = [candidate for candidate in infer_pair_candidates(relative) if candidate in available]
        if len(mates) > 1:
            unresolved.append(f"Ambiguous mate candidates for {relative}: {', '.join(mates)}")
        elif read_side(relative) == "2" and not mates:
            unresolved.append(f"R2 file has no candidate R1 mate: {relative}")
        items.append({
            "path": relative, "size_bytes": path.stat().st_size, "read_side": read_side(relative) or "single",
            "sample_suggestion": sample_base(relative), "candidate_mates": mates,
        })
    return response({
        "input_root": str(source), "fastq_files": items,
        "summary": {"total_fastq_count": len(items)}, "warnings": [] if items else ["No supported FASTQ files found."],
        "unresolved": sorted(set(unresolved)),
    })

