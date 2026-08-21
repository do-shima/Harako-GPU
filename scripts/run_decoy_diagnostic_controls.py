"""Run fixed Salmon 2.5.1 decoy diagnostic controls with structured argv."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import time
from decimal import Decimal
from pathlib import Path

from harako_gpu.services.decoy_accounting import diagnostic_mapping_argv


IMAGE = "harako-gpu/salmon:2.5.1-qualification"
IMAGE_ID = "sha256:e6e64f39a479458ef6f007757498321ee5a3ef8a2227ff2af414fbe3c36e6f7f"
SAMPLES = (
    "decoy_unique_only", "decoy_dominant_only",
    "decoy_ambiguous_only", "decoy_exact_tie_only",
)


def _product_argv(*, index: str, gene_map: str, r1: str, r2: str, output: str) -> tuple[str, ...]:
    return (
        "salmon", "quant", "--deterministic", "--decoder", "serial",
        "--geneMap", gene_map, "--threads", "6", "--libType=ISR",
        "--index", index, "-1", r1, "-2", r2, "-o", output,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fasta_ids(path: Path) -> set[str]:
    return {
        line[1:].split()[0]
        for line in path.read_text(encoding="ascii").splitlines()
        if line.startswith(">")
    }


def _quant_mass(path: Path, transcript_ids: set[str]) -> Decimal:
    total = Decimal(0)
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["Name"] in transcript_ids:
                total += Decimal(row["NumReads"])
    return total


def run(fixture: Path, transcript_index: Path, decoy_index: Path, output: Path) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=False)
    transcript_ids = _fasta_ids(fixture / "transcripts.fa")
    fixture_manifest = json.loads((fixture / "manifest.json").read_text(encoding="utf-8"))
    expected = {row["sample"]: int(row["fragments"]) for row in fixture_manifest["diagnostic_samples"]}
    runs: list[dict[str, object]] = []
    for role, index in (("transcript_only", transcript_index), ("decoy_aware", decoy_index)):
        for sample in SAMPLES:
            destination = output / role / sample
            destination.mkdir(parents=True)
            product = _product_argv(
                index="/index", gene_map="/fixture/genes.gtf",
                r1=f"/fixture/{sample}_R1.fastq.gz",
                r2=f"/fixture/{sample}_R2.fastq.gz", output="/out",
            )
            salmon_argv = diagnostic_mapping_argv(product, keep_rad=role == "decoy_aware")
            argv = (
                "docker", "run", "--rm",
                "-v", f"{fixture}:/fixture:ro", "-v", f"{index}:/index:ro",
                "-v", f"{destination}:/out", IMAGE, *salmon_argv,
            )
            started = time.perf_counter()
            completed = subprocess.run(argv, capture_output=True, check=False)
            wall = time.perf_counter() - started
            (destination / "stdout.log").write_bytes(completed.stdout)
            (destination / "stderr.log").write_bytes(completed.stderr)
            if completed.returncode:
                raise RuntimeError(f"Salmon diagnostic failed: {role}/{sample}")
            meta_path = destination / "aux_info/meta_info.json"
            quant_path = destination / "quant.sf"
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            if int(metadata["num_processed"]) != expected[sample]:
                raise ValueError(f"Fragment accounting mismatch: {role}/{sample}")
            rad_files = sorted(path for path in destination.rglob("*.rad") if path.is_file())
            runs.append({
                "index_role": role,
                "sample": sample,
                "expected_fragments": expected[sample],
                "num_processed": int(metadata["num_processed"]),
                "num_mapped": int(metadata["num_mapped"]),
                "num_decoy_fragments": metadata.get("num_decoy_fragments"),
                "num_decoy_targets": metadata.get("num_decoy_targets"),
                "index_decoy_name_hash": metadata.get("index_decoy_name_hash"),
                "index_decoy_seq_hash": metadata.get("index_decoy_seq_hash"),
                "estimated_transcript_mass": str(_quant_mass(quant_path, transcript_ids)),
                "quant_sf_sha256": _sha256(quant_path),
                "meta_info_sha256": _sha256(meta_path),
                "keep_rad": role == "decoy_aware",
                "rad_files": [
                    {"name": path.relative_to(destination).as_posix(), "size_bytes": path.stat().st_size,
                     "sha256": _sha256(path)} for path in rad_files
                ],
                "wall_seconds": wall,
                "salmon_argv": list(salmon_argv),
            })
    payload: dict[str, object] = {
        "schema_version": "decoy_control_runs_v1",
        "candidate_version": "2.5.1",
        "candidate_image": IMAGE,
        "candidate_image_id": IMAGE_ID,
        "fixture_id": fixture_manifest["fixture_id"],
        "fixture_scientific_manifest_sha256": fixture_manifest["scientific_manifest_sha256"],
        "runs": runs,
    }
    payload["scientific_digest"] = hashlib.sha256(
        json.dumps({
            "fixture": payload["fixture_scientific_manifest_sha256"],
            "runs": [{k: v for k, v in row.items() if k not in {"wall_seconds", "meta_info_sha256"}}
                     for row in runs],
        }, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (output / "control-report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--transcript-index", type=Path, required=True)
    parser.add_argument("--decoy-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run(
        args.fixture.resolve(), args.transcript_index.resolve(),
        args.decoy_index.resolve(), args.output.resolve(),
    )
    print(json.dumps({
        "runs": len(payload["runs"]), "scientific_digest": payload["scientific_digest"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
