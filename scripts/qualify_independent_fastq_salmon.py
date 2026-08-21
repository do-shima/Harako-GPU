"""Prepare and summarize the pinned independent FASTQ Salmon qualification.

This harness never launches Nextflow, Docker, or Salmon.  It creates immutable
runtime inputs and evaluates already-produced quantification outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from harako_gpu.adapters.filesystem import sha256_path, write_new_text
from harako_gpu.core.contracts import QualificationDebugMode, minimal_feasibility_profile
from harako_gpu.services.backend_profile import config_fragment
from harako_gpu.services.independent_fastq_salmon import (
    SALMON_IMAGE_DIGEST,
    SALMON_VERSION,
    SalmonIndexIdentity,
    independent_fastq_nf_params,
)
from harako_gpu.services.salmon_reproducibility import (
    canonical_numerical_digest,
    classify_reproducibility,
    compare_expression_tables,
    compare_quant_tables,
    ExpressionRow,
    ExpressionTable,
    parse_quant_sf,
    parse_salmon_metadata,
    TpmStratum,
)


def directory_manifest(path: Path) -> tuple[list[dict[str, object]], str]:
    if not path.is_dir():
        raise ValueError(f"Index directory does not exist: {path}")
    files = [item for item in path.rglob("*") if item.is_file()]
    if not files:
        raise ValueError("Index directory is empty")
    rows = [
        {
            "path": item.relative_to(path).as_posix(),
            "size_bytes": item.stat().st_size,
            "sha256": sha256_path(item),
        }
        for item in sorted(files)
    ]
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return rows, hashlib.sha256(encoded).hexdigest()


def prepare(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    manifest_dir = root / "manifests" / args.candidate
    rows, index_manifest_sha256 = directory_manifest(args.salmon_index.resolve())
    decoys_sha256 = sha256_path(args.decoys.resolve())
    index_id_payload = {
        "builder": SALMON_VERSION,
        "image_digest": SALMON_IMAGE_DIGEST,
        "transcript_fasta_sha256": sha256_path(args.transcript_fasta.resolve()),
        "genome_fasta_sha256": sha256_path(args.fasta.resolve()),
        "decoys_sha256": decoys_sha256,
        "parameters": ["-k", "31", "decoy_aware_gentrome"],
        "manifest_sha256": index_manifest_sha256,
    }
    index_id = hashlib.sha256(
        json.dumps(index_id_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    identity = SalmonIndexIdentity(
        salmon_index_id=index_id,
        index_path=args.salmon_index_wsl,
        index_builder_version=SALMON_VERSION,
        index_builder_image_digest=SALMON_IMAGE_DIGEST,
        transcript_fasta_sha256=index_id_payload["transcript_fasta_sha256"],
        genome_fasta_sha256=index_id_payload["genome_fasta_sha256"],
        decoys_sha256=decoys_sha256,
        index_parameters=("-k", "31", "decoy_aware_gentrome"),
        index_manifest_sha256=index_manifest_sha256,
    )
    identity.validate()
    params = {
        "input": args.samplesheet_wsl,
        "outdir": args.outdir_wsl,
        "fasta": args.fasta_wsl,
        "gtf": args.gtf_wsl,
        "transcript_fasta": args.transcript_fasta_wsl,
        "star_index": args.star_index_wsl,
        "aligner": "star_salmon",
        "use_parabricks_star": True,
        "skip_markduplicates": True,
        "extra_star_align_args": "--low-memory --x3",
        "save_align_intermeds": True,
        "save_reference": True,
        "skip_bbsplit": True,
        "skip_preseq": True,
        **independent_fastq_nf_params(salmon_index=args.salmon_index_wsl),
    }
    command = [
        args.nextflow_wsl, "run", args.pipeline_wsl, "-profile", "docker",
        "-params-file", args.params_wsl, "-c", args.config_wsl,
        "-work-dir", args.workdir_wsl,
    ]
    profile = minimal_feasibility_profile(
        gpu_selection="0", qualification_debug_mode=QualificationDebugMode.X3
    )
    artifacts = {
        manifest_dir / "nf-samplesheet.csv": (
            "sample,fastq_1,fastq_2,strandedness\n"
            f"WT_REP1,{args.r1_wsl},{args.r2_wsl},auto\n"
        ),
        manifest_dir / "harako-samplesheet.csv": (
            "sample,condition,fastq_1,fastq_2,strandedness,library_protocol\n"
            f"WT_REP1,fixture,{args.r1_wsl},{args.r2_wsl},auto,full_length\n"
        ),
        manifest_dir / "nf-params.json": json.dumps(params, indent=2, sort_keys=True) + "\n",
        manifest_dir / "nextflow.config": config_fragment(
            profile, independent_fastq_salmon=True
        ),
        manifest_dir / "command.argv.json": json.dumps(command, indent=2) + "\n",
        manifest_dir / "salmon-index-manifest.json": json.dumps(
            {"schema_version": 1, "identity": identity.as_dict(), "files": rows},
            indent=2,
            sort_keys=True,
        ) + "\n",
    }
    for path, content in artifacts.items():
        write_new_text(path, content)
    print(json.dumps({"prepared": True, "index_id": index_id, "manifest_dir": str(manifest_dir)}))


def summarize(args: argparse.Namespace) -> None:
    quant_paths = (
        sorted(path.resolve() for path in args.quant_path)
        if args.quant_path
        else sorted(args.quant_root.resolve().glob("*/*/quant.sf"))
    )
    if args.name_prefix:
        quant_paths = [path for path in quant_paths if path.parent.name.startswith(args.name_prefix)]
    if len(quant_paths) < 2:
        raise ValueError("At least two quant.sf outputs are required")
    baseline = parse_quant_sf(quant_paths[0].read_text(encoding="utf-8"))
    baseline_gene_quant = parse_quant_sf((quant_paths[0].parent / "quant.genes.sf").read_text(encoding="utf-8"))
    baseline_gene = ExpressionTable(tuple(
        ExpressionRow(row.transcript_id, row.tpm, row.num_reads)
        for row in baseline_gene_quant.rows
    ))
    comparisons = []
    classes = []
    for path in quant_paths[1:]:
        candidate = parse_quant_sf(path.read_text(encoding="utf-8"))
        candidate_gene_quant = parse_quant_sf((path.parent / "quant.genes.sf").read_text(encoding="utf-8"))
        candidate_gene = ExpressionTable(tuple(
            ExpressionRow(row.transcript_id, row.tpm, row.num_reads)
            for row in candidate_gene_quant.rows
        ))
        transcript = compare_quant_tables(baseline, candidate)
        gene = compare_expression_tables(baseline_gene, candidate_gene)
        meta_a = parse_salmon_metadata(
            (quant_paths[0].parent / "aux_info" / "meta_info.json").read_text(encoding="utf-8")
        )
        meta_b = parse_salmon_metadata(
            (path.parent / "aux_info" / "meta_info.json").read_text(encoding="utf-8")
        )
        classification = classify_reproducibility(
            quant_byte_identical=quant_paths[0].read_bytes() == path.read_bytes(),
            transcript=transcript,
            gene=gene,
            metadata_exact=meta_a == meta_b,
        )
        classes.append(classification.value)
        comparisons.append({
            "candidate": path.parent.name,
            "class": classification.value,
            "quant_sha256": sha256_path(path),
            "canonical_digest": canonical_numerical_digest(candidate),
            "processed_fragments": meta_b.num_processed,
            "mapped_fragments": meta_b.num_mapped,
            "effective_length_max_absolute_difference": str(
                transcript.effective_length_max_absolute_difference
            ),
            "num_reads_max_absolute_difference": str(transcript.num_reads_max_absolute_difference),
            "tpm_middle_max_absolute_difference": str(
                transcript.strata[TpmStratum.MIDDLE].max_absolute_difference
            ),
            "tpm_high_max_relative_difference": (
                str(transcript.strata[TpmStratum.HIGH].max_relative_difference)
                if transcript.strata[TpmStratum.HIGH].max_relative_difference is not None else None
            ),
            "gene_num_reads_max_absolute_difference": str(gene.num_reads_max_absolute_difference),
            "gene_tpm_high_max_relative_difference": (
                str(gene.strata[TpmStratum.HIGH].max_relative_difference)
                if gene.strata[TpmStratum.HIGH].max_relative_difference is not None else None
            ),
            "transcript_tpm_spearman": transcript.tpm_spearman,
            "gene_tpm_spearman": gene.tpm_spearman,
            "zero_nonzero_transitions": list(transcript.zero_nonzero_transition_ids),
        })
    payload = {
        "schema_version": 1,
        "runs": len(quant_paths),
        "baseline_quant_sha256": sha256_path(quant_paths[0]),
        "baseline_canonical_digest": canonical_numerical_digest(baseline),
        "classes": sorted(set(classes)),
        "comparisons": comparisons,
    }
    write_new_text(args.output.resolve(), json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"summary": str(args.output.resolve()), "classes": payload["classes"]}))


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    commands = value.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.set_defaults(func=prepare)
    prepare_parser.add_argument("--candidate", default="candidate-a")
    for name in ("root", "salmon_index", "decoys", "transcript_fasta", "fasta"):
        prepare_parser.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    prepare_parser.add_argument("--gtf", type=Path, required=True)
    for name in (
        "salmon_index_wsl", "samplesheet_wsl", "outdir_wsl", "fasta_wsl", "gtf_wsl",
        "transcript_fasta_wsl", "star_index_wsl", "r1_wsl", "r2_wsl", "nextflow_wsl",
        "pipeline_wsl", "params_wsl", "config_wsl", "workdir_wsl",
    ):
        prepare_parser.add_argument("--" + name.replace("_", "-"), required=True)
    summary_parser = commands.add_parser("summarize")
    summary_parser.set_defaults(func=summarize)
    summary_parser.add_argument("--quant-root", type=Path)
    summary_parser.add_argument("--quant-path", type=Path, action="append", default=[])
    summary_parser.add_argument("--gtf", type=Path, required=True)
    summary_parser.add_argument("--output", type=Path, required=True)
    summary_parser.add_argument("--name-prefix")
    return value


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
