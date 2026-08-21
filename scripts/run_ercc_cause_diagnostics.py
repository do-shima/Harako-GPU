"""Run the fixed ERCC cause-isolation matrix with structured Docker argv."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


IMAGE = "harako-gpu/salmon:2.5.1-qualification"
TRAINING = ("SRR896983", "SRR896985", "SRR897015", "SRR897017")
HOLDOUT = ("SRR896987", "SRR896989", "SRR897019", "SRR897021")


def run(argv: list[str], log_root: Path, name: str) -> None:
    completed = subprocess.run(argv, capture_output=True, check=False)
    (log_root / f"{name}.stdout.txt").write_bytes(completed.stdout)
    (log_root / f"{name}.stderr.txt").write_bytes(completed.stderr)
    if completed.returncode:
        raise RuntimeError(f"{name} failed with exit {completed.returncode}")


def reads_root(root: Path, sample: str) -> Path:
    if sample in TRAINING:
        return root / "runs/preprocessing" / sample / "repeat-1"
    return root / "ercc/holdout/processed" / sample


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.runtime_root.resolve()
    log_root = root / "logs/cause-isolation"
    log_root.mkdir(parents=True, exist_ok=True)
    outputs = root / "runs/cause-isolation"
    outputs.mkdir(parents=True, exist_ok=True)
    reference = root / "references/external-v2"
    for sample in (*TRAINING, *HOLDOUT):
        reads = reads_root(root, sample)
        r1, r2 = reads / f"{sample}_R1.fastq.gz", reads / f"{sample}_R2.fastq.gz"
        if not r1.is_file() or not r2.is_file():
            raise FileNotFoundError(f"Missing fixed processed pair for {sample}")
        output = outputs / sample / "combined-mappings"
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite diagnostic output: {output}")
        output.mkdir(parents=True)
        argv = [
            "docker", "run", "--rm",
            "-v", f"{root / 'indices/combined-human-sirv'}:/index:ro",
            "-v", f"{reference}:/ref:ro", "-v", f"{reads}:/reads:ro",
            "-v", f"{output}:/out", IMAGE, "salmon", "quant",
            "--deterministic", "--decoder", "serial", "--geneMap",
            "/ref/gencode.v49.sirv69.tx2gene.tsv", "--threads", "6",
            "--libType=IU", "--index", "/index", "-1", f"/reads/{r1.name}",
            "-2", f"/reads/{r2.name}", "-o", "/out", "--writeMappings",
            "/out/mappings.sam",
        ]
        run(argv, log_root, f"{sample}-combined-mappings")
        if sample in HOLDOUT:
            ercc_output = outputs / sample / "ercc-only"
            ercc_output.mkdir(parents=True)
            ercc_argv = [
                "docker", "run", "--rm", "-v", f"{root / 'indices/ercc-92'}:/index:ro",
                "-v", f"{root / 'references/ercc92'}:/ref:ro",
                "-v", f"{reads}:/reads:ro", "-v", f"{ercc_output}:/out",
                IMAGE, "salmon", "quant", "--deterministic", "--decoder", "serial",
                "--geneMap", "/ref/ERCC92.gtf", "--threads", "6", "--libType=IU",
                "--index", "/index", "-1", f"/reads/{r1.name}", "-2", f"/reads/{r2.name}",
                "-o", "/out",
            ]
            run(ercc_argv, log_root, f"{sample}-ercc-only")
    summary = {
        "schema_version": 1,
        "image": IMAGE,
        "training": list(TRAINING),
        "holdout": list(HOLDOUT),
        "combined_mapping_sam": "complete",
        "holdout_ercc_only": "complete",
    }
    (root / "manifests/cause-isolation/diagnostic-run-manifest.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
