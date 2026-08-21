"""Summarize existing Salmon 2.5.1 artifacts without launching a process."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from harako_gpu.adapters.filesystem import sha256_path, write_new_text
from harako_gpu.services.salmon_2x_qualification import (
    CANDIDATE_VERSION,
    CandidateIndexIdentity,
    build_truth_accuracy_report,
    exact_identity,
    validate_exact_repeats,
)
from harako_gpu.services.salmon_reproducibility import parse_quant_sf, parse_salmon_metadata


def directory_manifest(path: Path) -> tuple[list[dict[str, object]], str]:
    rows = [
        {"role": item.relative_to(path).as_posix(), "size_bytes": item.stat().st_size,
         "sha256": sha256_path(item)}
        for item in sorted(path.rglob("*")) if item.is_file()
    ]
    if not rows:
        raise ValueError("Index directory is empty")
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return rows, hashlib.sha256(encoded).hexdigest()


def index_manifest(args: argparse.Namespace) -> None:
    files, inventory = directory_manifest(args.index.resolve())
    identity = CandidateIndexIdentity(
        salmon_index_id="", index_builder_version=CANDIDATE_VERSION,
        index_builder_image_id=args.image_id,
        transcript_fasta_sha256=sha256_path(args.transcript_fasta.resolve()),
        genome_fasta_sha256=sha256_path(args.genome_fasta.resolve()),
        gentrome_sha256=sha256_path(args.gentrome.resolve()),
        decoys_sha256=sha256_path(args.decoys.resolve()), kmer_size=31,
        index_inventory_sha256=inventory,
    )
    identity = CandidateIndexIdentity(**{**asdict(identity), "salmon_index_id": identity.expected_index_id})
    identity.validate()
    payload = {
        "schema_version": 1, "identity": asdict(identity),
        "command_argv": ["salmon", "index", "--threads", "6", "--transcripts", "gentrome.fa",
                         "--decoys", "decoys.txt", "--kmerLen", "31", "--index", "index"],
        "files": files,
    }
    write_new_text(args.output.resolve(), json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"index_id": identity.salmon_index_id, "files": len(files)}))


def _run_identity(path: Path):
    quant_bytes = (path / "quant.sf").read_bytes()
    gene_bytes = (path / "quant.genes.sf").read_bytes()
    quant = parse_quant_sf(quant_bytes.decode())
    metadata = parse_salmon_metadata((path / "aux_info/meta_info.json").read_text())
    partial = any(item.name.endswith((".rad.tmp", ".partial")) for item in path.rglob("*"))
    return exact_identity(quant_bytes=quant_bytes, gene_quant_bytes=gene_bytes, quant=quant,
                          metadata=metadata, partial_rad_signature=partial)


def exact_report(args: argparse.Namespace) -> None:
    run_roots = sorted(path.parent for path in args.root.resolve().rglob("quant.sf"))
    runs = [_run_identity(path) for path in run_roots]
    validate_exact_repeats(runs, expected_fragments=args.expected_fragments)
    payload = {
        "schema_version": 1, "passed": True, "runs": len(runs),
        "identity": asdict(runs[0]),
    }
    write_new_text(args.output.resolve(), json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"passed": True, "runs": len(runs), "quant_sf_sha256": runs[0].quant_sf_sha256}))


def truth_report(args: argparse.Namespace) -> None:
    manifest = json.loads(args.manifest.read_text())
    quant = {}
    metadata = {}
    for sample in manifest["samples"]:
        name = sample["sample"]
        root = args.quant_root.resolve() / name
        quant[name] = parse_quant_sf((root / "quant.sf").read_text())
        metadata[name] = parse_salmon_metadata((root / "aux_info/meta_info.json").read_text())
    report = build_truth_accuracy_report(manifest=manifest, quant_by_sample=quant,
                                         metadata_by_sample=metadata)
    payload = {"schema_version": 1, "passed": report.passed, **asdict(report)}
    write_new_text(args.output.resolve(), json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"passed": report.passed, "report": asdict(report)}, default=str))


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    commands = value.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index-manifest")
    index.set_defaults(func=index_manifest)
    for name in ("index", "transcript_fasta", "genome_fasta", "gentrome", "decoys", "output"):
        index.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    index.add_argument("--image-id", required=True)
    exact = commands.add_parser("exact-report")
    exact.set_defaults(func=exact_report)
    exact.add_argument("--root", type=Path, required=True)
    exact.add_argument("--expected-fragments", type=int, required=True)
    exact.add_argument("--output", type=Path, required=True)
    truth = commands.add_parser("truth-report")
    truth.set_defaults(func=truth_report)
    truth.add_argument("--manifest", type=Path, required=True)
    truth.add_argument("--quant-root", type=Path, required=True)
    truth.add_argument("--output", type=Path, required=True)
    return value


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
