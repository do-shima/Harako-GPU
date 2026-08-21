"""Resolve ERR188044 paired library orientation without abundance inspection."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path


IMAGE = "sha256:e6e64f39a479458ef6f007757498321ee5a3ef8a2227ff2af414fbe3c36e6f7f"
CANDIDATES = ("IU", "ISF", "ISR")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024**2), b""):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True)
    args = parser.parse_args()
    runtime = Path(args.runtime_root).resolve()
    index = runtime / "capacity/indices/salmon-2.5.1"
    reference = runtime / "capacity/references/human_grch38p14_gencode49_harako_gpu_v1/assets"
    reads = runtime / "capacity/fixtures/C1_1M"
    root = runtime / "capacity/library-type-probe"
    if root.exists():
        raise SystemExit("Library-type probe already exists; refusing overwrite")
    root.mkdir(parents=True)
    uid_gid = f"{os.getuid()}:{os.getgid()}"; rows = []
    for candidate in CANDIDATES:
        output = root / candidate; output.mkdir()
        argv = [
            "docker", "run", "--rm", "--user", uid_gid,
            "--mount", f"type=bind,src={index},dst=/input/index,readonly",
            "--mount", f"type=bind,src={reads},dst=/input/reads,readonly",
            "--mount", f"type=bind,src={reference},dst=/input/reference,readonly",
            "--mount", f"type=bind,src={output},dst=/output", IMAGE,
            "salmon", "quant", "--deterministic", "--decoder", "serial",
            "--geneMap", "/input/reference/gencode.v49.primary.tx2gene.tsv", "--threads", "6",
            "--libType", candidate, "--index", "/input/index", "-1", "/input/reads/ERR188044_1.fastq.gz",
            "-2", "/input/reads/ERR188044_2.fastq.gz", "-o", "/output",
        ]
        (output / "command.json").write_text(json.dumps({"structured_argv": argv}, indent=2) + "\n", encoding="utf-8")
        started = time.monotonic()
        with (output / "stdout.log").open("x", encoding="utf-8") as stdout, (
            output / "stderr.log"
        ).open("x", encoding="utf-8") as stderr:
            result = subprocess.run(argv, stdout=stdout, stderr=stderr, text=True, check=False)
        if result.returncode:
            raise SystemExit(f"Orientation probe failed for {candidate}: {result.returncode}")
        counts = json.loads((output / "lib_format_counts.json").read_text(encoding="utf-8"))
        rows.append({
            "candidate": candidate, "compatible_fragment_ratio": counts["compatible_fragment_ratio"],
            "num_compatible_fragments": counts["num_compatible_fragments"],
            "num_assigned_fragments": counts["num_assigned_fragments"],
            "wall_seconds": time.monotonic() - started,
            "lib_format_counts_sha256": digest(output / "lib_format_counts.json"),
        })
    ranked = sorted(rows, key=lambda row: (-float(row["compatible_fragment_ratio"]), str(row["candidate"])))
    selected = ranked[0]; margin = float(selected["compatible_fragment_ratio"]) - float(ranked[1]["compatible_fragment_ratio"])
    passed = float(selected["compatible_fragment_ratio"]) >= 0.8 and margin >= 0.2
    result = {
        "schema_version": 1, "dataset": "ERR188044", "probe_subset_pairs": 1_000_000,
        "selection_inputs": "orientation-compatible fragments only",
        "abundance_mapping_rate_or_truth_used": False, "minimum_consistency": 0.8, "minimum_margin": 0.2,
        "candidates": rows, "selected_salmon_libtype": selected["candidate"] if passed else None,
        "selected_product_library_type": "U" if passed and selected["candidate"] == "IU" else selected["candidate"] if passed else None,
        "margin": margin, "status": "PASS" if passed else "UNKNOWN_LIBRARY_TYPE",
    }
    (root / "library-type-selection.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not passed:
        raise SystemExit("Orientation probe did not meet preregistered thresholds")


if __name__ == "__main__":
    main()
