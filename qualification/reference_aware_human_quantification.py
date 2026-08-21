"""Fixed qualification harness for human FASTQ quantification-only levels Q1-Q5."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

from harako_gpu.core.capabilities import BamOutputMode
from harako_gpu.core.contracts import BamRetention, MemoryMode
from harako_gpu.services.planning import create_plan


DIST = "Ubuntu"
LEVELS = {
    "Q1": ("C1_1M", "recommended-only", None),
    "Q2": ("C2_5M", "compare-both", "salmon_2_5_1_deterministic"),
    "Q3": ("C3_10M", "recommended-only", None),
    "Q4": ("C4_20M", "compare-both", "salmon_2_5_1_deterministic"),
    "Q5": ("source", "recommended-only", None),
}


def _linux(path: Path, *, unc_root: Path, linux_root: str) -> str:
    relative = path.resolve().relative_to(unc_root.resolve()).as_posix()
    return f"{linux_root}/{relative}"


def prepare(level: str, *, unc_root: Path, linux_root: str) -> dict:
    fixture, mode, primary = LEVELS[level]
    capacity = unc_root / "capacity"
    root = unc_root / "human-quant-only"
    level_root = root / level
    plan_root = level_root / "plan"
    if plan_root.exists():
        raise ValueError(f"Plan already exists: {plan_root}")
    plan_root.parent.mkdir(parents=True, exist_ok=True)
    reads = (capacity / "source" if level == "Q5" else capacity / "fixtures" / fixture)
    r1 = reads / ("ERR188044_1.fastq.gz")
    r2 = reads / ("ERR188044_2.fastq.gz")
    if not r1.is_file() or not r2.is_file():
        raise ValueError(f"Frozen input missing for {level}")
    sheet = level_root / "samplesheet.csv"
    with sheet.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("sample", "condition", "fastq_1", "fastq_2", "strandedness", "library_protocol"))
        writer.writeheader()
        writer.writerow({"sample": "ERR188044", "condition": "capacity", "fastq_1": str(r1),
                         "fastq_2": str(r2), "strandedness": "unstranded", "library_protocol": "TruSeq_RNA_v2"})
    assets = capacity / "references/human_grch38p14_gencode49_harako_gpu_v1/assets"
    plan = create_plan(
        samplesheet=sheet, plan_dir=plan_root, output_root=root / "runs" / level,
        work_root=root / "work" / level, fasta=assets / "GRCh38.primary_assembly.genome.fa",
        gtf=assets / "gencode.v49.primary_assembly.annotation.gtf",
        transcript_fasta=assets / "gencode.v49.transcript_targets.fa",
        bam_retention=BamRetention.NONE, bam_output_mode=BamOutputMode.NONE,
        gpu_selection="none", memory_mode=MemoryMode.STANDARD, species="Homo sapiens",
        assembly="GRCh38.p14", annotation_provider="GENCODE", annotation_release="49",
        project_slug=f"human-quant-{level.lower()}", target="wsl", wsl_distribution=DIST,
        salmon_index_manifest=capacity / "plans/C1_1M/legacy-salmon-index-manifest.json",
        salmon_2_5_1_index_manifest=capacity / "plans/C1_1M/salmon_2_5_1_deterministic-index.json",
        salmon_1_10_3_index_manifest=capacity / "plans/C1_1M/salmon_1_10_3_compatibility-index.json",
        quantification_mode=mode, primary_quantification_profile=primary,
        explicit_library_type="U", alignment_profile_id="none",
    )
    prereg = Path("docs/qualification/human-quantification-only-capacity-preregistration.json").resolve()
    frozen = root / "capacity-preregistration.json"
    if not frozen.exists():
        frozen.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(prereg, frozen)
    return {"level": level, "plan_id": plan.plan_id, "approval_hash": plan.approval_hash,
            "plan": _linux(plan_root / "plan.json", unc_root=unc_root, linux_root=linux_root),
            "runtime_root": f"{linux_root}/human-quant-only"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("level", choices=tuple(LEVELS))
    parser.add_argument("--runtime-root-unc", type=Path, required=True)
    parser.add_argument("--runtime-root-linux", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.level, unc_root=args.runtime_root_unc,
                             linux_root=args.runtime_root_linux.rstrip("/")), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
