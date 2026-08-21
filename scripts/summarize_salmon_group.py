"""Summarize an arbitrary group of isolated Salmon qualification runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from summarize_salmon_reproducibility import portable, summarize_group
from harako_gpu.services.salmon_reproducibility import parse_transcript_gene_map


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--gene-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    mapping = parse_transcript_gene_map(args.gene_map.read_text(encoding="utf-8"))
    payload = summarize_group(sorted(args.runs_root.glob("run-*")), mapping)
    args.output.write_text(
        json.dumps(portable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
