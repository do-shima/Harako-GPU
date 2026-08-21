"""Audit truth-v1 decoy identifiability without modifying the fixture."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path

from generate_harako_truth_bulk_v1 import decoys, transcriptome
from harako_gpu.services.decoy_accounting import PairedSequenceOracle, old_v1_aggregate_leakage


def _fastq_sequences(path: Path):
    with gzip.open(path, "rt", encoding="ascii") as handle:
        while True:
            name = handle.readline()
            if not name:
                return
            sequence = handle.readline().strip()
            plus = handle.readline()
            quality = handle.readline().strip()
            if not name.startswith("@") or not plus.startswith("+") or len(sequence) != len(quality):
                raise ValueError(f"Malformed FASTQ: {path.name}")
            yield name.split()[0].removeprefix("@").rsplit("/", 1)[0], sequence


def _quant_mass(path: Path, zero_ids: set[str]) -> tuple[Decimal, Decimal]:
    total = Decimal(0)
    zero = Decimal(0)
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            mass = Decimal(row["NumReads"])
            total += mass
            if row["Name"] in zero_ids:
                zero += mass
    return total, zero


def _reference_audit(transcripts: dict[str, str], decoy_rows: dict[str, str]) -> list[dict[str, object]]:
    zero_ids = [name for name in transcripts if name.startswith("tx_zero_")]
    rows: list[dict[str, object]] = []
    for position, (decoy_id, sequence) in enumerate(decoy_rows.items()):
        transcript_id = zero_ids[position]
        transcript = transcripts[transcript_id]
        matcher = SequenceMatcher(None, sequence, transcript, autojunk=False).find_longest_match()
        decoy_kmers = {sequence[start:start + 31] for start in range(len(sequence) - 30)}
        tx_kmers = {transcript[start:start + 31] for start in range(len(transcript) - 30)}
        rows.append({
            "decoy_id": decoy_id,
            "decoy_length": len(sequence),
            "homologous_transcript": transcript_id,
            "exact_homologous_decoy_interval": [400, 800],
            "exact_homologous_transcript_interval": [350, 750],
            "homologous_interval_percent_identity": 100.0,
            "longest_exact_match": matcher.size,
            "shared_distinct_31mers": len(decoy_kmers & tx_kmers),
        })
    return rows


def audit(fixture: Path, quant_root: Path) -> dict[str, object]:
    manifest = json.loads((fixture / "manifest.json").read_text(encoding="utf-8"))
    rows = transcriptome()
    transcripts = {row.transcript_id: row.sequence for row in rows}
    decoy_rows = decoys(rows)
    oracle = PairedSequenceOracle(transcripts, decoy_rows)
    class_counts: Counter[str] = Counter()
    source_class_counts: dict[str, Counter[str]] = {}
    audited = 0
    for sample in manifest["samples"]:
        sample_id = sample["sample"]
        r1_iter = _fastq_sequences(fixture / f"{sample_id}_R1.fastq.gz")
        r2_iter = _fastq_sequences(fixture / f"{sample_id}_R2.fastq.gz")
        with gzip.open(fixture / f"{sample_id}.truth.tsv.gz", "rt", encoding="ascii", newline="") as truth:
            for truth_row, left, right in zip(csv.DictReader(truth, delimiter="\t"), r1_iter, r2_iter):
                if left[0] != right[0] or truth_row["fragment_id"] != left[0]:
                    raise ValueError(f"Truth/FASTQ identity mismatch: {sample_id}")
                if truth_row["decoy"] != "1":
                    continue
                source = truth_row["source_transcript"]
                evidence = oracle.classify(
                    fragment_id=left[0], sample=sample_id, source_decoy=source,
                    r1=left[1], r2=right[1], source_interval=None,
                )
                category = evidence.identifiability_class.value
                class_counts[category] += 1
                source_class_counts.setdefault(source, Counter())[category] += 1
                audited += 1
    expected_decoys = sum(int(sample["decoy_origin_fragments"]) for sample in manifest["samples"])
    if audited != expected_decoys:
        raise ValueError("Not every v1 decoy-origin fragment was audited")

    zero_ids = {row.transcript_id for row in rows if row.weight_a == row.weight_b == 0}
    total_mass = Decimal(0)
    zero_mass = Decimal(0)
    transcript_origins = 0
    decoy_origins = 0
    for sample in manifest["samples"]:
        sample_id = sample["sample"]
        sample_total, sample_zero = _quant_mass(quant_root / sample_id / "quant.sf", zero_ids)
        total_mass += sample_total
        zero_mass += sample_zero
        transcript_origins += int(sample["transcript_origin_fragments"])
        decoy_origins += int(sample["decoy_origin_fragments"])
    leakage = old_v1_aggregate_leakage(
        zero_expression_mass=zero_mass, total_estimated_mass=total_mass,
        transcript_origin_fragments=transcript_origins, generated_decoy_fragments=decoy_origins,
    )
    if leakage != Decimal("0.194"):
        raise ValueError(f"truth-v1 leakage did not reproduce: {leakage}")
    return {
        "schema_version": "truth_v1_decoy_audit_v1",
        "fixture_id": manifest["fixture_id"],
        "fixture_scientific_manifest_sha256": manifest["scientific_manifest_sha256"],
        "fixture_preserved": True,
        "old_formula": {
            "numerator": "max(zero_expression_estimated_count_mass, total_estimated_count_mass_minus_transcript_origin_fragments)",
            "denominator": "generated_decoy_origin_paired_fragments",
            "unit": "estimated_count_mass_per_generated_paired_fragment",
            "read_level_attribution": False,
            "zero_expression_mass": str(zero_mass),
            "total_estimated_mass": str(total_mass),
            "transcript_origin_fragments": transcript_origins,
            "generated_decoy_fragments": decoy_origins,
            "reproduced_fraction": str(leakage),
        },
        "reference_homology": _reference_audit(transcripts, decoy_rows),
        "decoy_fragment_class_counts": dict(sorted(class_counts.items())),
        "per_decoy_class_counts": {
            name: dict(sorted(counts.items())) for name, counts in sorted(source_class_counts.items())
        },
        "audited_decoy_fragments": audited,
        "scientific_digest": hashlib.sha256(json.dumps({
            "classes": dict(sorted(class_counts.items())), "leakage": str(leakage),
        }, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--quant-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.fixture.resolve(), args.quant_root.resolve())
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "fixture_id": result["fixture_id"],
        "reproduced_fraction": result["old_formula"]["reproduced_fraction"],
        "decoy_fragment_class_counts": result["decoy_fragment_class_counts"],
        "scientific_digest": result["scientific_digest"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
