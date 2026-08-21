"""Run the fixed truth-v2 Salmon 2.5.1 deterministic repeat matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path


IMAGE = "harako-gpu/salmon:2.5.1-qualification"
IMAGE_ID = "sha256:e6e64f39a479458ef6f007757498321ee5a3ef8a2227ff2af414fbe3c36e6f7f"
DIAGNOSTICS = (
    "decoy_unique_only", "decoy_dominant_only",
    "decoy_ambiguous_only", "decoy_exact_tie_only",
)
MAIN = ("A_REP1", "A_REP2", "A_REP3", "B_REP1", "B_REP2", "B_REP3")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _argv(sample: str, threads: int) -> tuple[str, ...]:
    return (
        "salmon", "quant", "--deterministic", "--decoder", "serial",
        "--geneMap", "/fixture/genes.gtf", "--threads", str(threads),
        "--libType=ISR", "--index", "/index",
        "-1", f"/fixture/{sample}_R1.fastq.gz",
        "-2", f"/fixture/{sample}_R2.fastq.gz", "-o", "/out",
    )


def run(fixture: Path, index: Path, output: Path) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((fixture / "manifest.json").read_text(encoding="utf-8"))
    expected = {
        row["sample"]: int(row["fragments"])
        for row in (*manifest["diagnostic_samples"], *manifest["main_samples"])
    }
    schedule = [
        *(("diagnostic_repeat", sample, repeat, 6) for sample in DIAGNOSTICS for repeat in range(1, 11)),
        *(("main_repeat", sample, repeat, 6) for sample in MAIN for repeat in range(1, 4)),
        *(("thread_check", "A_REP1", threads, threads) for threads in (1, 2, 4, 6)),
    ]
    runs: list[dict[str, object]] = []
    for phase, sample, replicate, threads in schedule:
        destination = output / phase / sample / f"run-{replicate}"
        destination.mkdir(parents=True)
        salmon = _argv(sample, threads)
        argv = (
            "docker", "run", "--rm", "-v", f"{fixture}:/fixture:ro",
            "-v", f"{index}:/index:ro", "-v", f"{destination}:/out", IMAGE, *salmon,
        )
        started = time.perf_counter()
        completed = subprocess.run(argv, capture_output=True, check=False)
        wall = time.perf_counter() - started
        (destination / "stdout.log").write_bytes(completed.stdout)
        (destination / "stderr.log").write_bytes(completed.stderr)
        if completed.returncode:
            raise RuntimeError(f"Salmon failed: {phase}/{sample}/{replicate}")
        meta_path = destination / "aux_info/meta_info.json"
        quant_path = destination / "quant.sf"
        genes_path = destination / "quant.genes.sf"
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        if int(metadata["num_processed"]) != expected[sample]:
            raise ValueError(f"Partial fragment count: {phase}/{sample}/{replicate}")
        scientific_meta = {
            key: metadata.get(key)
            for key in (
                "salmon_version", "quant_mode", "lib_types", "num_processed", "num_mapped",
                "num_targets", "num_decoy_targets", "num_decoy_fragments",
                "index_seq_hash", "index_name_hash", "index_decoy_seq_hash", "index_decoy_name_hash",
            )
        }
        runs.append({
            "phase": phase, "sample": sample, "replicate": replicate, "threads": threads,
            "num_processed": int(metadata["num_processed"]),
            "num_mapped": int(metadata["num_mapped"]),
            "quant_sf_sha256": _sha(quant_path),
            "quant_genes_sf_sha256": _sha(genes_path),
            "scientific_meta_sha256": hashlib.sha256(json.dumps(
                scientific_meta, sort_keys=True, separators=(",", ":")
            ).encode()).hexdigest(),
            "wall_seconds": wall, "salmon_argv": list(salmon),
        })

    for phase, samples, expected_repeats in (
        ("diagnostic_repeat", DIAGNOSTICS, 10), ("main_repeat", MAIN, 3),
    ):
        for sample in samples:
            selected = [row for row in runs if row["phase"] == phase and row["sample"] == sample]
            if len(selected) != expected_repeats:
                raise ValueError("Repeat matrix cardinality changed")
            for field in ("num_processed", "num_mapped", "quant_sf_sha256", "quant_genes_sf_sha256", "scientific_meta_sha256"):
                if len({row[field] for row in selected}) != 1:
                    raise ValueError(f"Deterministic identity failed: {phase}/{sample}/{field}")
    thread_runs = [row for row in runs if row["phase"] == "thread_check"]
    baseline = next(row for row in runs if row["phase"] == "main_repeat" and row["sample"] == "A_REP1")
    for field in ("num_processed", "num_mapped", "quant_sf_sha256", "quant_genes_sf_sha256", "scientific_meta_sha256"):
        if len({baseline[field], *(row[field] for row in thread_runs)}) != 1:
            raise ValueError(f"Cross-thread deterministic identity failed: {field}")
    payload: dict[str, object] = {
        "schema_version": "truth_v2_salmon_2_5_1_matrix_v1",
        "candidate_version": "2.5.1", "candidate_image": IMAGE,
        "candidate_image_id": IMAGE_ID,
        "fixture_id": manifest["fixture_id"],
        "fixture_scientific_manifest_sha256": manifest["scientific_manifest_sha256"],
        "diagnostic_repeats_per_sample": 10,
        "main_repeats_per_sample": 3,
        "thread_counts": [1, 2, 4, 6],
        "exact_identity_passed": True,
        "runs": runs,
    }
    payload["scientific_digest"] = hashlib.sha256(json.dumps({
        "fixture": payload["fixture_scientific_manifest_sha256"],
        "runs": [{k: v for k, v in row.items() if k != "wall_seconds"} for row in runs],
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (output / "matrix-report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.fixture.resolve(), args.index.resolve(), args.output.resolve())
    print(json.dumps({
        "runs": len(result["runs"]), "exact_identity_passed": result["exact_identity_passed"],
        "scientific_digest": result["scientific_digest"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
