"""Create immutable one-pass capacity plans from fixed runtime-only assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from harako_gpu.adapters.filesystem import sha256_path, write_new_text
from harako_gpu.adapters.wsl import linux_path_to_unc
from harako_gpu.core.contracts import BamRetention, MemoryMode, QualificationDebugMode
from harako_gpu.services.alignment_profiles import ONE_PASS_PROFILE_ID
from harako_gpu.services.planning import create_plan


LEVELS = {
    "C1_1M": ("recommended-only", 1_000_000),
    "C2_5M": ("compare-both", 5_000_000),
    "C3_10M": ("recommended-only", 10_000_000),
    "C4_20M": ("recommended-only", 20_000_000),
}


def local(path: str, distribution: str) -> Path:
    return Path(linux_path_to_unc(path, distribution=distribution))


def profile_manifest(profile_id: str, destination: Path, reference: dict, builder: dict,
                     root: str, distribution: str) -> Path:
    version = "2.5.1" if profile_id.startswith("salmon_2_5_1") else "1.10.3"
    image = (
        "sha256:e6e64f39a479458ef6f007757498321ee5a3ef8a2227ff2af414fbe3c36e6f7f"
        if version == "2.5.1" else
        "sha256:f83ebb158845ee8138d793347f83b92c75e83c58dd8f4600c6fea2a2453ef08e"
    )
    manifest = local(f"{root}/capacity/indices/salmon-{version}.manifest.json", distribution)
    data = {
        "profile_id": profile_id, "index_id": builder["index_id"],
        "path": f"{root}/capacity/indices/salmon-{version}", "builder_version": version,
        "image_identity": image,
        "transcript_source_sha256": reference["files"]["gencode.v49.transcript_targets.fa"]["sha256"],
        "genome_source_sha256": reference["files"]["GRCh38.primary_assembly.genome.fa"]["sha256"],
        "gtf_sha256": reference["files"]["gencode.v49.primary_assembly.annotation.gtf"]["sha256"],
        "tx2gene_sha256": reference["files"]["gencode.v49.primary.tx2gene.tsv"]["sha256"],
        "manifest_sha256": sha256_path(manifest),
    }
    path = destination / f"{profile_id}-index.json"
    write_new_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("level", choices=tuple(LEVELS))
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--distribution", default="Ubuntu")
    args = parser.parse_args()
    mode, pairs = LEVELS[args.level]
    root = args.runtime_root.rstrip("/")
    if not root.startswith("/") or root.startswith(("/mnt/c", "/mnt/d")):
        raise SystemExit("runtime root must be an absolute WSL ext4 path")
    qualification = f"{root}/one-pass-capacity"
    reference_root = f"{root}/capacity/references/human_grch38p14_gencode49_harako_gpu_v1"
    base = local(f"{qualification}/plans/{args.level}", args.distribution)
    if base.exists():
        raise SystemExit(f"One-pass plan already exists: {base}")
    base.mkdir(parents=True)
    reference = json.loads(local(f"{reference_root}/reference-manifest.json", args.distribution).read_text(encoding="utf-8"))
    builds = json.loads(local(f"{root}/capacity/indices/index-build-summary.json", args.distribution).read_text(encoding="utf-8"))
    by_name = {item["name"]: item for item in builds["indices"]}
    p251 = profile_manifest("salmon_2_5_1_deterministic", base, reference,
                            by_name["salmon-2.5.1"], root, args.distribution)
    p1103 = profile_manifest("salmon_1_10_3_compatibility", base, reference,
                             by_name["salmon-1.10.3"], root, args.distribution)
    legacy = {
        "identity": {
            "schema_version": 1, "salmon_index_id": by_name["salmon-1.10.3"]["index_id"],
            "index_path": f"{root}/capacity/indices/salmon-1.10.3", "index_builder_version": "1.10.3",
            "index_builder_image_digest": "sha256:f83ebb158845ee8138d793347f83b92c75e83c58dd8f4600c6fea2a2453ef08e",
            "transcript_fasta_sha256": reference["files"]["gencode.v49.transcript_targets.fa"]["sha256"],
            "genome_fasta_sha256": reference["files"]["GRCh38.primary_assembly.genome.fa"]["sha256"],
            "decoys_sha256": reference["files"]["gencode.v49.primary.decoys.txt"]["sha256"],
            "index_parameters": ["-k", "31", "decoy_aware_gentrome"],
            "index_manifest_sha256": sha256_path(local(
                f"{root}/capacity/indices/salmon-1.10.3.manifest.json", args.distribution,
            )),
        }
    }
    legacy_path = base / "legacy-salmon-index-manifest.json"
    write_new_text(legacy_path, json.dumps(legacy, indent=2, sort_keys=True) + "\n")
    reads = f"{root}/capacity/fixtures/{args.level}"
    samplesheet = base / "samplesheet.csv"
    write_new_text(
        samplesheet,
        "sample,condition,fastq_1,fastq_2,strandedness,library_protocol\n"
        f"ERR188044,capacity,{local(reads + '/ERR188044_1.fastq.gz', args.distribution)},"
        f"{local(reads + '/ERR188044_2.fastq.gz', args.distribution)},unstranded,TruSeq_RNA_v2\n",
    )
    primary = "salmon_2_5_1_deterministic" if mode == "compare-both" else None
    plan = create_plan(
        samplesheet=samplesheet, plan_dir=base / "plan",
        output_root=local(f"{qualification}/runs/{args.level}", args.distribution),
        work_root=local(f"{qualification}/work/{args.level}", args.distribution),
        fasta=local(f"{reference_root}/assets/GRCh38.primary_assembly.genome.fa", args.distribution),
        gtf=local(f"{reference_root}/assets/gencode.v49.primary_assembly.annotation.gtf", args.distribution),
        transcript_fasta=local(f"{reference_root}/assets/gencode.v49.transcript_targets.fa", args.distribution),
        salmon_index_manifest=legacy_path, salmon_2_5_1_index_manifest=p251,
        salmon_1_10_3_index_manifest=p1103,
        star_index=local(f"{root}/capacity/indices/star-2.7.2a", args.distribution),
        star_index_sjdb_overhang=74,
        qualification_resource_contract="full_human_47gib_probe_v1",
        alignment_profile_id=ONE_PASS_PROFILE_ID,
        allow_alignment_qualification_candidate=True,
        quantification_mode=mode, primary_quantification_profile=primary,
        bam_retention=BamRetention.KEEP, gpu_selection="all",
        memory_mode=MemoryMode.LOW_MEMORY_CANDIDATE,
        qualification_debug_mode=QualificationDebugMode.DISABLED,
        save_reference=False, skip_pseudo_alignment=False,
        species="Homo sapiens", assembly="GRCh38.p14", annotation_provider="GENCODE",
        annotation_release="49", project_slug=f"one-pass-{args.level.lower().replace('_', '-')}",
        target="wsl", wsl_distribution=args.distribution, explicit_library_type="U",
    )
    print(json.dumps({"level": args.level, "pairs": pairs, "mode": mode,
                      "plan": str(base / "plan/plan.json"), "plan_id": plan.plan_id,
                      "approval_hash": plan.approval_hash}, indent=2))


if __name__ == "__main__":
    main()
