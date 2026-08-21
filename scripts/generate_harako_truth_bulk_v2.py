"""Generate the stratified harako_truth_bulk_v2_decoy_stratified fixture."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
from pathlib import Path
from typing import Iterable

from generate_harako_truth_bulk_v1 import (
    DNA,
    FRAGMENT_MEAN,
    FRAGMENT_SD,
    READ_LENGTH,
    SUBSTITUTION_ERROR_RATE,
    Transcript,
    _allocate,
    _gzip_text,
    _random_dna,
    _read_with_errors,
    _reverse_complement,
    _sha256,
    _write_fasta,
    sample_counts,
    transcriptome,
)
from harako_gpu.services.decoy_accounting import (
    IdentifiabilityClass,
    PairedSequenceOracle,
)


FIXTURE_ID = "harako_truth_bulk_v2_decoy_stratified"
GENERATOR_VERSION = 2
MASTER_SEED = 252_20260816
MAIN_FRAGMENTS = 50_000
MAIN_DECOY_FRAGMENTS = 500
DIAGNOSTIC_FRAGMENTS = 20_000
SAMPLES = (
    ("A_REP1", "A", 2101), ("A_REP2", "A", 2102), ("A_REP3", "A", 2103),
    ("B_REP1", "B", 2201), ("B_REP2", "B", 2202), ("B_REP3", "B", 2203),
)
DIAGNOSTICS = {
    "decoy_unique_only": IdentifiabilityClass.DECOY_UNIQUE,
    "decoy_dominant_only": IdentifiabilityClass.DECOY_DOMINANT,
    "decoy_ambiguous_only": IdentifiabilityClass.DECOY_AMBIGUOUS,
    "decoy_exact_tie_only": IdentifiabilityClass.DECOY_EXACT_TIE,
}


def _mutate_fixed(sequence: str, *, spacing: int, offset: int) -> str:
    values = list(sequence)
    for position in range(offset, len(values), spacing):
        values[position] = DNA[(DNA.index(values[position]) + 1) % len(DNA)]
    return "".join(values)


def _mutate_blocks(
    sequence: str, *, block_length: int, spacing: int, offset: int,
) -> str:
    """Add decoy-specific blocks while retaining long transcript-like seeds."""

    values = list(sequence)
    for block_start in range(offset, len(values), spacing):
        for position in range(block_start, min(block_start + block_length, len(values))):
            values[position] = DNA[(DNA.index(values[position]) + 1) % len(DNA)]
    return "".join(values)


def stratified_decoys(rows: Iterable[Transcript]) -> dict[str, str]:
    transcripts = {row.transcript_id: row.sequence for row in rows}
    rng = random.Random(MASTER_SEED)
    unique = _mutate_blocks(
        transcripts["tx_zero_04_1"], block_length=16, spacing=70, offset=23,
    )
    # Non-homologous flanks keep this target distinct in the index while the
    # central transcript copy creates observation-level exact ties by design.
    exact_tie = (
        _random_dna(rng, 200) + transcripts["tx_zero_03_1"] + _random_dna(rng, 200)
    )
    return {
        "decoy_unique": unique,
        "decoy_dominant": _mutate_fixed(transcripts["tx_zero_01_1"], spacing=22, offset=7),
        "decoy_ambiguous": _mutate_fixed(transcripts["tx_zero_02_1"], spacing=97, offset=43),
        "decoy_exact_tie": exact_tie,
    }


def _fragment_pair(sequence: str, start: int, length: int, rng: random.Random) -> tuple[str, str]:
    fragment = sequence[start:start + length]
    r1 = _read_with_errors(_reverse_complement(fragment[-READ_LENGTH:]), rng)
    r2 = _read_with_errors(fragment[:READ_LENGTH], rng)
    return r1, r2


def _class_source(category: IdentifiabilityClass) -> str:
    return {
        IdentifiabilityClass.DECOY_UNIQUE: "decoy_unique",
        IdentifiabilityClass.DECOY_DOMINANT: "decoy_dominant",
        IdentifiabilityClass.DECOY_AMBIGUOUS: "decoy_ambiguous",
        IdentifiabilityClass.DECOY_EXACT_TIE: "decoy_exact_tie",
    }[category]


def _accepted_decoy_fragment(
    *, oracle: PairedSequenceOracle, decoy_rows: dict[str, str], category: IdentifiabilityClass,
    sample: str, fragment_id: str, rng: random.Random,
) -> tuple[str, str, str, int, int, object]:
    source = _class_source(category)
    sequence = decoy_rows[source]
    for _ in range(10_000):
        length = max(READ_LENGTH * 2, min(len(sequence), round(rng.gauss(FRAGMENT_MEAN, FRAGMENT_SD))))
        start = rng.randrange(0, len(sequence) - length + 1)
        r1, r2 = _fragment_pair(sequence, start, length, rng)
        evidence = oracle.classify(
            fragment_id=fragment_id, sample=sample, source_decoy=source,
            source_interval=(start, start + length), r1=r1, r2=r2,
        )
        if evidence.identifiability_class is category:
            return source, r1, r2, start, length, evidence
    raise RuntimeError(f"Unable to construct {category.value} fragment")


def _open_outputs(root: Path, sample: str):
    paths = (
        root / f"{sample}_R1.fastq.gz", root / f"{sample}_R2.fastq.gz",
        root / f"{sample}.truth.tsv.gz",
    )
    streams = [_gzip_text(path) for path in paths]
    streams[2][1].write(
        b"fragment_id\tsource_kind\tsource_id\tsource_gene\tsource_start\tfragment_length\t"
        b"condition\tidentifiability_class\tbest_decoy_distance\tbest_transcript_distance\t"
        b"best_transcript_id\tscore_margin\tr1_sequence\tr2_sequence\n"
    )
    return paths, streams


def _write_pair(streams, fragment_id: str, r1: str, r2: str) -> None:
    quality = "I" * READ_LENGTH
    streams[0][1].write(f"@{fragment_id}/1\n{r1}\n+\n{quality}\n".encode())
    streams[1][1].write(f"@{fragment_id}/2\n{r2}\n+\n{quality}\n".encode())


def _close_outputs(streams) -> None:
    for raw, stream in streams:
        stream.close()
        raw.close()


def _validate_fastq_pair(paths: tuple[Path, Path, Path], expected: int) -> None:
    counts: list[int] = []
    for path in paths[:2]:
        with gzip.open(path, "rt", encoding="ascii") as handle:
            lines = sum(1 for _ in handle)
        if lines % 4:
            raise ValueError(f"Malformed FASTQ: {path.name}")
        counts.append(lines // 4)
    with gzip.open(paths[2], "rt", encoding="ascii") as handle:
        truth_rows = sum(1 for _ in handle) - 1
    if counts != [expected, expected] or truth_rows != expected:
        raise ValueError("Paired FASTQ/truth cardinality mismatch")


def _emit_diagnostic(
    root: Path, sample: str, category: IdentifiabilityClass,
    oracle: PairedSequenceOracle, decoy_rows: dict[str, str], seed: int,
) -> dict[str, object]:
    rng = random.Random(MASTER_SEED + seed)
    paths, streams = _open_outputs(root, sample)
    class_counts: dict[str, int] = {}
    try:
        for number in range(1, DIAGNOSTIC_FRAGMENTS + 1):
            fragment_id = f"HBV2D{seed:04d}{number:08d}"
            source, r1, r2, start, length, evidence = _accepted_decoy_fragment(
                oracle=oracle, decoy_rows=decoy_rows, category=category,
                sample=sample, fragment_id=fragment_id, rng=rng,
            )
            _write_pair(streams, fragment_id, r1, r2)
            class_counts[evidence.identifiability_class.value] = class_counts.get(
                evidence.identifiability_class.value, 0
            ) + 1
            streams[2][1].write(
                f"{fragment_id}\tdecoy\t{source}\t{source}\t{start}\t{length}\tdiagnostic\t"
                f"{evidence.identifiability_class.value}\t{evidence.best_decoy_distance}\t"
                f"{evidence.best_transcript_distance}\t{evidence.best_transcript_id or ''}\t"
                f"{evidence.score_margin}\t{r1}\t{r2}\n".encode()
            )
    finally:
        _close_outputs(streams)
    _validate_fastq_pair(paths, DIAGNOSTIC_FRAGMENTS)
    if class_counts != {category.value: DIAGNOSTIC_FRAGMENTS}:
        raise ValueError("Diagnostic sample is not class-pure")
    return {
        "sample": sample, "role": "diagnostic_decoy_only", "seed": seed,
        "fragments": DIAGNOSTIC_FRAGMENTS, "class_counts": class_counts,
        "r1_sha256": _sha256(paths[0]), "r2_sha256": _sha256(paths[1]),
        "truth_sha256": _sha256(paths[2]),
    }


def _emit_main(
    root: Path, sample: str, condition: str, seed: int, rows: tuple[Transcript, ...],
    oracle: PairedSequenceOracle, decoy_rows: dict[str, str],
) -> dict[str, object]:
    rng = random.Random(MASTER_SEED + seed)
    counts = sample_counts(rows, condition)
    # Rescale v1 biological weights from 49,500 to the same v2 main total.
    counts = _allocate({name: value for name, value in counts.items() if value},
                       MAIN_FRAGMENTS - MAIN_DECOY_FRAGMENTS)
    counts.update({row.transcript_id: 0 for row in rows if row.transcript_id not in counts})
    by_id = {row.transcript_id: row for row in rows}
    sources: list[str] = [name for name, count in counts.items() for _ in range(count)]
    rng.shuffle(sources)
    paths, streams = _open_outputs(root, sample)
    class_counts: dict[str, int] = {}
    number = 0
    try:
        for source in sources:
            number += 1
            row = by_id[source]
            length = max(READ_LENGTH * 2, min(len(row.sequence), round(rng.gauss(FRAGMENT_MEAN, FRAGMENT_SD))))
            start = rng.randrange(0, len(row.sequence) - length + 1)
            r1, r2 = _fragment_pair(row.sequence, start, length, rng)
            fragment_id = f"HBV2M{seed:04d}{number:08d}"
            evidence = oracle.classify(
                fragment_id=fragment_id, sample=sample, source_decoy="",
                source_interval=(start, start + length), r1=r1, r2=r2, source_is_decoy=False,
            )
            _write_pair(streams, fragment_id, r1, r2)
            streams[2][1].write(
                f"{fragment_id}\ttranscript\t{source}\t{row.gene_id}\t{start}\t{length}\t{condition}\t"
                f"{evidence.identifiability_class.value}\t{evidence.best_decoy_distance}\t"
                f"{evidence.best_transcript_distance}\t{evidence.best_transcript_id or ''}\t"
                f"{evidence.score_margin}\t{r1}\t{r2}\n".encode()
            )
        per_class = MAIN_DECOY_FRAGMENTS // len(DIAGNOSTICS)
        for category in DIAGNOSTICS.values():
            for _ in range(per_class):
                number += 1
                fragment_id = f"HBV2M{seed:04d}{number:08d}"
                source, r1, r2, start, length, evidence = _accepted_decoy_fragment(
                    oracle=oracle, decoy_rows=decoy_rows, category=category,
                    sample=sample, fragment_id=fragment_id, rng=rng,
                )
                _write_pair(streams, fragment_id, r1, r2)
                class_counts[category.value] = class_counts.get(category.value, 0) + 1
                streams[2][1].write(
                    f"{fragment_id}\tdecoy\t{source}\t{source}\t{start}\t{length}\t{condition}\t"
                    f"{category.value}\t{evidence.best_decoy_distance}\t"
                    f"{evidence.best_transcript_distance}\t{evidence.best_transcript_id or ''}\t"
                    f"{evidence.score_margin}\t{r1}\t{r2}\n".encode()
                )
    finally:
        _close_outputs(streams)
    _validate_fastq_pair(paths, MAIN_FRAGMENTS)
    return {
        "sample": sample, "role": "main_biological", "condition": condition, "seed": seed,
        "fragments": MAIN_FRAGMENTS, "transcript_origin_fragments": sum(counts.values()),
        "decoy_origin_fragments": MAIN_DECOY_FRAGMENTS, "class_counts": class_counts,
        "transcript_counts": counts, "r1_sha256": _sha256(paths[0]),
        "r2_sha256": _sha256(paths[1]), "truth_sha256": _sha256(paths[2]),
    }


def generate(root: Path) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=False)
    rows = transcriptome()
    transcripts = {row.transcript_id: row.sequence for row in rows}
    decoy_rows = stratified_decoys(rows)
    oracle = PairedSequenceOracle(transcripts, decoy_rows)
    files = {
        "transcripts.fa": list(transcripts.items()),
        "decoys.fa": list(decoy_rows.items()),
        "gentrome.fa": [*transcripts.items(), *decoy_rows.items()],
    }
    for name, entries in files.items():
        _write_fasta(root / name, entries)
    (root / "decoys.txt").write_text("".join(name + "\n" for name in decoy_rows), encoding="ascii")
    (root / "genes.gtf").write_text("".join(
        f'{row.transcript_id}\tharako\texon\t1\t{len(row.sequence)}\t.\t+\t.\t'
        f'gene_id "{row.gene_id}"; transcript_id "{row.transcript_id}";\n'
        for row in rows
    ), encoding="ascii")
    diagnostics = [
        _emit_diagnostic(root, sample, category, oracle, decoy_rows, 3000 + position)
        for position, (sample, category) in enumerate(DIAGNOSTICS.items(), start=1)
    ]
    main = [_emit_main(root, *sample, rows, oracle, decoy_rows) for sample in SAMPLES]
    reference_paths = [root / name for name in (*files, "decoys.txt", "genes.gtf")]
    payload: dict[str, object] = {
        "fixture_id": FIXTURE_ID, "generator_version": GENERATOR_VERSION,
        "oracle_schema_version": "decoy_identifiability_v1", "master_seed": MASTER_SEED,
        "read_length": READ_LENGTH, "fragment_length_mean": FRAGMENT_MEAN,
        "fragment_length_sd": FRAGMENT_SD, "substitution_error_rate": SUBSTITUTION_ERROR_RATE,
        "library_type": "ISR", "transcript_count": len(rows),
        "gene_count": len({row.gene_id for row in rows}), "decoy_count": len(decoy_rows),
        "zero_expression_transcripts": [row.transcript_id for row in rows if row.weight_a == row.weight_b == 0],
        "zero_identifiable_transcripts": [
            row.transcript_id for row in rows
            if row.weight_a == row.weight_b == 0 and row.transcript_id not in {
                "tx_zero_01_1", "tx_zero_02_1", "tx_zero_03_1", "tx_zero_04_1"
            }
        ],
        "decoy_design": {
            "DECOY_UNIQUE": {"source": "decoy_unique", "transcript_relation": "16-base decoy-specific blocks every 70 bases on a transcript-like backbone"},
            "DECOY_DOMINANT": {"source": "decoy_dominant", "transcript_relation": "fixed 22-base mutation spacing"},
            "DECOY_AMBIGUOUS": {"source": "decoy_ambiguous", "transcript_relation": "fixed 97-base mutation spacing"},
            "DECOY_EXACT_TIE": {"source": "decoy_exact_tie", "transcript_relation": "tx_zero_03_1 embedded between non-homologous flanks"},
        },
        "transcripts": [
            {"transcript_id": row.transcript_id, "gene_id": row.gene_id,
             "stratum": row.stratum, "group_id": row.group_id, "length": len(row.sequence)}
            for row in rows
        ],
        "diagnostic_samples": diagnostics, "main_samples": main,
        "reference_sha256": {path.name: _sha256(path) for path in reference_paths},
    }
    scientific = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    payload["scientific_manifest_sha256"] = scientific
    (root / "manifest.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = generate(args.output.resolve())
    print(json.dumps({
        "fixture_id": payload["fixture_id"],
        "scientific_manifest_sha256": payload["scientific_manifest_sha256"],
        "main_samples": len(payload["main_samples"]),
        "diagnostic_samples": len(payload["diagnostic_samples"]),
    }))


if __name__ == "__main__":
    main()
