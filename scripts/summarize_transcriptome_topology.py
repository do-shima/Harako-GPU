"""Summarize a SAM stream against the Salmon transcriptome grouping contract."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from harako_gpu.services.transcriptome_grouping import inspect_sam_topology


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    result = asdict(inspect_sam_topology(sys.stdin))
    result["label"] = args.label
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
