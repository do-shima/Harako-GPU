"""Run fixed Salmon 1.x truth-v2 comparison controls."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import time
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from harako_gpu.services.decoy_accounting import build_truth_v2_biological_report


VERSIONS = {
    "1.10.3": ("quay.io/biocontainers/salmon:1.10.3--h6dccd9a_2", "sha256:f83ebb158845ee8138d793347f83b92c75e83c58dd8f4600c6fea2a2453ef08e"),
    "1.12.1": ("harako-gpu/salmon:1.12.1-qualification", "sha256:88b88863b8830ca6eb6747c305522c220bf660caa16eb82400240ba7637d81dd"),
}
DIAGNOSTICS = (
    "decoy_unique_only", "decoy_dominant_only",
    "decoy_ambiguous_only", "decoy_exact_tie_only",
)
MAIN = ("A_REP1", "A_REP2", "A_REP3", "B_REP1", "B_REP2", "B_REP3")


def _sha(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def _quant(path: Path, transcript_ids: set[str]) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["Name"] in transcript_ids:
                result[row["Name"]] = Decimal(row["NumReads"])
    return result


def run(fixture: Path, index_110: Path, index_112: Path, output: Path) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((fixture / "manifest.json").read_text(encoding="utf-8"))
    transcript_ids = {row["transcript_id"] for row in manifest["transcripts"]}
    expected = {
        row["sample"]: int(row["fragments"])
        for row in (*manifest["diagnostic_samples"], *manifest["main_samples"])
    }
    indices = {"1.10.3": index_110, "1.12.1": index_112}
    version_reports: dict[str, object] = {}
    for version, (image, image_id) in VERSIONS.items():
        runs: list[dict[str, object]] = []
        quant_by_sample: dict[str, dict[str, Decimal]] = {}
        processed: dict[str, int] = {}
        mapped: dict[str, int] = {}
        for sample in (*DIAGNOSTICS, *MAIN):
            destination = output / version / sample
            destination.mkdir(parents=True)
            salmon = (
                "salmon", "quant", "--geneMap", "/fixture/genes.gtf", "--threads", "6",
                "--libType=ISR", "--index", "/index",
                "-1", f"/fixture/{sample}_R1.fastq.gz",
                "-2", f"/fixture/{sample}_R2.fastq.gz", "-o", "/out",
            )
            argv = (
                "docker", "run", "--rm", "-v", f"{fixture}:/fixture:ro",
                "-v", f"{indices[version]}:/index:ro", "-v", f"{destination}:/out", image, *salmon,
            )
            started = time.perf_counter()
            completed = subprocess.run(argv, capture_output=True, check=False)
            wall = time.perf_counter() - started
            (destination / "stdout.log").write_bytes(completed.stdout)
            (destination / "stderr.log").write_bytes(completed.stderr)
            metadata_path = destination / "aux_info/meta_info.json"
            quant_path = destination / "quant.sf"
            diagnostic_zero_assignment = (
                sample in DIAGNOSTICS and completed.returncode != 0 and metadata_path.is_file()
                and quant_path.is_file() and b"minimum number of required assigned fragments" in completed.stderr
            )
            if completed.returncode and not diagnostic_zero_assignment:
                raise RuntimeError(f"Salmon {version} failed: {sample}")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if int(metadata["num_processed"]) != expected[sample]:
                raise ValueError(f"Partial fragment count: {version}/{sample}")
            estimates = _quant(quant_path, transcript_ids)
            runs.append({
                "sample": sample, "num_processed": int(metadata["num_processed"]),
                "num_mapped": int(metadata["num_mapped"]),
                "transcript_mass": str(sum(estimates.values(), Decimal(0))),
                "quant_sf_sha256": _sha(quant_path),
                "exit_code": completed.returncode,
                "zero_assignment_minimum_triggered": diagnostic_zero_assignment,
                "wall_seconds": wall, "salmon_argv": list(salmon),
            })
            if sample in MAIN:
                quant_by_sample[sample] = estimates
                processed[sample] = int(metadata["num_processed"])
                mapped[sample] = int(metadata["num_mapped"])
        biology = build_truth_v2_biological_report(
            manifest=manifest, quant_by_sample=quant_by_sample,
            processed_by_sample=processed, mapped_by_sample=mapped,
        )
        biology_payload = asdict(biology)
        biology_payload["unidentifiable_assignment_mass"] = str(biology.unidentifiable_assignment_mass)
        biology_payload["passed"] = biology.passed
        version_reports[version] = {
            "image": image, "image_id": image_id, "index_role": f"decoy-aware-{version}",
            "runs": runs, "biological_truth": biology_payload,
            "diagnostic_transcript_mass": {
                row["sample"]: row["transcript_mass"] for row in runs if row["sample"] in DIAGNOSTICS
            },
        }
    payload: dict[str, object] = {
        "schema_version": "truth_v2_salmon_1x_comparison_v1",
        "fixture_id": manifest["fixture_id"],
        "fixture_scientific_manifest_sha256": manifest["scientific_manifest_sha256"],
        "versions": version_reports,
        "truth_is_primary_not_version_agreement": True,
    }
    (output / "comparison-report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--index-1-10-3", type=Path, required=True)
    parser.add_argument("--index-1-12-1", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        args.fixture.resolve(), args.index_1_10_3.resolve(),
        args.index_1_12_1.resolve(), args.output.resolve(),
    )
    print(json.dumps({
        version: {
            "biology_passed": row["biological_truth"]["passed"],
            "diagnostic_transcript_mass": row["diagnostic_transcript_mass"],
        } for version, row in result["versions"].items()
    }, sort_keys=True))


if __name__ == "__main__":
    main()
