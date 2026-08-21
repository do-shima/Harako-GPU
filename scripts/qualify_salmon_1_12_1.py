"""Summarize already-produced Salmon 1.12.1 qualification artifacts.

This script is intentionally non-executing: it neither launches containers nor
builds indices. Runtime commands stay operator-visible and structured.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from harako_gpu.adapters.filesystem import sha256_path, write_new_text
from harako_gpu.services.salmon_reproducibility import (
    ExpressionRow,
    ExpressionTable,
    compare_expression_tables,
    compare_quant_tables,
    parse_quant_sf,
    parse_salmon_metadata,
)
from harako_gpu.services.salmon_upgrade_qualification import (
    CANDIDATE_VERSION,
    CandidateIndexIdentity,
    build_non_regression_report,
)


def directory_manifest(path: Path) -> tuple[list[dict[str, object]], str]:
    files = sorted(item for item in path.rglob("*") if item.is_file())
    if not files:
        raise ValueError("Candidate index directory is empty")
    rows = [
        {
            "role": item.relative_to(path).as_posix(),
            "size_bytes": item.stat().st_size,
            "sha256": sha256_path(item),
        }
        for item in files
    ]
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return rows, hashlib.sha256(encoded).hexdigest()


def index_manifest(args: argparse.Namespace) -> None:
    rows, inventory_sha256 = directory_manifest(args.index.resolve())
    fields = {
        "index_builder_version": CANDIDATE_VERSION,
        "index_builder_image_id": args.image_id,
        "transcript_fasta_sha256": sha256_path(args.transcript_fasta.resolve()),
        "genome_fasta_sha256": sha256_path(args.genome_fasta.resolve()),
        "gentrome_sha256": sha256_path(args.gentrome.resolve()),
        "decoys_sha256": sha256_path(args.decoys.resolve()),
        "kmer_size": 31,
        "index_manifest_sha256": inventory_sha256,
    }
    id_payload = {
        "builder_version": fields["index_builder_version"],
        "builder_image": fields["index_builder_image_id"],
        "transcript_fasta": fields["transcript_fasta_sha256"],
        "genome_fasta": fields["genome_fasta_sha256"],
        "gentrome": fields["gentrome_sha256"],
        "decoys": fields["decoys_sha256"],
        "kmer_size": fields["kmer_size"],
        "manifest": fields["index_manifest_sha256"],
    }
    identity = CandidateIndexIdentity(
        salmon_index_id=hashlib.sha256(
            json.dumps(id_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        **fields,
    )
    identity.validate()
    payload = {
        "schema_version": 1,
        "identity": {
            "salmon_index_id": identity.salmon_index_id,
            **fields,
        },
        "command_argv": [
            "salmon", "index", "--threads", "6", "-t", "gentrome.fa",
            "-d", "decoys.txt", "-k", "31", "-i", "salmon-1.12.1-index",
        ],
        "files": rows,
    }
    write_new_text(args.output.resolve(), json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"index_id": identity.salmon_index_id, "manifest": str(args.output)}))


def _gene_table(path: Path) -> ExpressionTable:
    quant = parse_quant_sf(path.read_text(encoding="utf-8"))
    return ExpressionTable(
        tuple(ExpressionRow(row.transcript_id, row.tpm, row.num_reads) for row in quant.rows)
    )


def compare_versions(args: argparse.Namespace) -> None:
    baseline_quant = parse_quant_sf(args.baseline_quant.read_text(encoding="utf-8"))
    candidate_quant = parse_quant_sf(
        args.candidate_quant.read_text(encoding="utf-8"), expected_ids=baseline_quant.ids
    )
    baseline_meta = parse_salmon_metadata(args.baseline_meta.read_text(encoding="utf-8"))
    candidate_meta = parse_salmon_metadata(args.candidate_meta.read_text(encoding="utf-8"))
    transcript = compare_quant_tables(baseline_quant, candidate_quant)
    gene = compare_expression_tables(
        _gene_table(args.baseline_gene), _gene_table(args.candidate_gene)
    )
    report = build_non_regression_report(
        transcript=transcript,
        gene=gene,
        baseline_metadata=baseline_meta,
        candidate_metadata=candidate_meta,
    )
    payload = {
        "schema_version": 1,
        "passed": report.passed,
        "transcript_id_set_equal": report.transcript_id_set_equal,
        "gene_id_set_equal": report.gene_id_set_equal,
        "fragment_accounting_consistent": report.fragment_accounting_consistent,
        "baseline_processed_fragments": baseline_meta.num_processed,
        "baseline_mapped_fragments": baseline_meta.num_mapped,
        "candidate_processed_fragments": candidate_meta.num_processed,
        "candidate_mapped_fragments": candidate_meta.num_mapped,
        "mapping_rate_absolute_percentage_point_difference": str(
            report.mapping_rate_absolute_percentage_point_difference
        ),
        "transcript_tpm_pearson": transcript.tpm_pearson,
        "transcript_tpm_spearman": report.transcript_spearman,
        "gene_tpm_pearson": gene.tpm_pearson,
        "gene_tpm_spearman": report.gene_spearman,
        "transcript_zero_nonzero_transitions": list(transcript.zero_nonzero_transition_ids),
        "gene_zero_nonzero_transitions": list(gene.zero_nonzero_transition_ids),
        "transcript_num_reads_max_absolute_difference": str(
            transcript.num_reads_max_absolute_difference
        ),
        "transcript_effective_length_max_absolute_difference": str(
            transcript.effective_length_max_absolute_difference
        ),
    }
    write_new_text(args.output.resolve(), json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"passed": report.passed, "summary": str(args.output)}))


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    commands = value.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index-manifest")
    index.set_defaults(func=index_manifest)
    for name in ("index", "transcript_fasta", "genome_fasta", "gentrome", "decoys", "output"):
        index.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    index.add_argument("--image-id", required=True)
    compare = commands.add_parser("compare-versions")
    compare.set_defaults(func=compare_versions)
    for name in (
        "baseline_quant", "baseline_gene", "baseline_meta", "candidate_quant",
        "candidate_gene", "candidate_meta", "output",
    ):
        compare.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    return value


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
