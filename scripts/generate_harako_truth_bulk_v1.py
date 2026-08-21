"""Generate the independent deterministic harako_truth_bulk_v1 runtime fixture.

The simulator uses only the Python standard library.  It never observes a
Salmon index or output.  FASTQ/reference artifacts belong under the caller's
runtime root and must not be committed.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


FIXTURE_ID = "harako_truth_bulk_v1"
GENERATOR_VERSION = 1
MASTER_SEED = 251_20260816
READ_LENGTH = 100
FRAGMENTS_PER_SAMPLE = 50_000
DECOY_FRAGMENTS_PER_SAMPLE = 500
FRAGMENT_MEAN = 220
FRAGMENT_SD = 18
SUBSTITUTION_ERROR_RATE = 0.001
SAMPLES = (
    ("A_REP1", "A", 1101), ("A_REP2", "A", 1102), ("A_REP3", "A", 1103),
    ("B_REP1", "B", 1201), ("B_REP2", "B", 1202), ("B_REP3", "B", 1203),
)
DNA = "ACGT"


@dataclass(frozen=True)
class Transcript:
    transcript_id: str
    gene_id: str
    sequence: str
    stratum: str
    group_id: str
    weight_a: int
    weight_b: int


def _random_dna(rng: random.Random, length: int) -> str:
    return "".join(rng.choice(DNA) for _ in range(length))


def _mutate(sequence: str, rng: random.Random, rate: float) -> str:
    result: list[str] = []
    for base in sequence:
        if rng.random() < rate:
            result.append(rng.choice(DNA.replace(base, "")))
        else:
            result.append(base)
    return "".join(result)


def transcriptome() -> tuple[Transcript, ...]:
    """Return a stable 48-transcript, 30-gene truth design."""

    rng = random.Random(MASTER_SEED)
    rows: list[Transcript] = []
    # Twelve single-isoform genes with fully unique sequence.
    for number in range(1, 13):
        gene = f"gene_unique_{number:02d}"
        fold = 2 if number % 3 == 0 else (1 if number % 3 == 1 else -2)
        weight_a = 500 + number * 120
        weight_b = weight_a * fold if fold > 0 else weight_a // abs(fold)
        rows.append(Transcript(f"tx_unique_{number:02d}", gene, _random_dna(rng, 1200),
                               "unique_identifiable", gene, weight_a, weight_b))
    # Eight genes with a shared core and isoform-specific regions.
    for number in range(1, 9):
        gene = f"gene_isoform_{number:02d}"
        core = _random_dna(rng, 850)
        total_a = 1500 + number * 150
        total_b = total_a * (2 if number <= 4 else 1)
        for isoform, share in ((1, 3), (2, 2)):
            sequence = core[:425] + _random_dna(rng, 350) + core[425:]
            rows.append(Transcript(
                f"tx_isoform_{number:02d}_{isoform}", gene, sequence,
                "ambiguous_isoform", gene, total_a * share, total_b * share,
            ))
    # Four high-similarity paralog genes.  The pair aggregate is the stable unit.
    for pair in range(1, 3):
        ancestor = _random_dna(rng, 1200)
        for paralog in range(1, 3):
            gene = f"gene_paralog_{pair}_{paralog}"
            sequence = _mutate(ancestor, rng, 0.025)
            rows.extend((
                Transcript(f"tx_paralog_{pair}_{paralog}_1", gene, sequence,
                           "paralog_group", f"paralog_pair_{pair}", 1000, 2000),
                Transcript(f"tx_paralog_{pair}_{paralog}_2", gene,
                           sequence[:600] + _random_dna(rng, 200) + sequence[600:],
                           "paralog_group", f"paralog_pair_{pair}", 600, 1200),
            ))
    # Six two-isoform genes provide twelve zero-expression controls.
    for number in range(1, 7):
        gene = f"gene_zero_{number:02d}"
        for isoform in (1, 2):
            rows.append(Transcript(f"tx_zero_{number:02d}_{isoform}", gene,
                                   _random_dna(rng, 1200), "zero_expression", gene, 0, 0))
    if len(rows) != 48 or len({row.gene_id for row in rows}) != 30:
        raise AssertionError("Truth transcriptome cardinality changed")
    return tuple(rows)


def decoys(transcripts: Iterable[Transcript]) -> dict[str, str]:
    """Create four genome-like decoys that include zero-transcript homology."""

    zeros = [row for row in transcripts if row.stratum == "zero_expression"]
    rng = random.Random(MASTER_SEED + 1)
    result: dict[str, str] = {}
    for index in range(4):
        homologous = zeros[index].sequence[350:750]
        result[f"decoy_{index + 1:02d}"] = _random_dna(rng, 400) + homologous + _random_dna(rng, 400)
    return result


def _allocate(weights: dict[str, int], total: int) -> dict[str, int]:
    denominator = sum(weights.values())
    raw = {name: total * weight / denominator for name, weight in weights.items()}
    allocated = {name: int(value) for name, value in raw.items()}
    missing = total - sum(allocated.values())
    order = sorted(weights, key=lambda name: (raw[name] - allocated[name], name), reverse=True)
    for name in order[:missing]:
        allocated[name] += 1
    return allocated


def sample_counts(transcripts: Iterable[Transcript], condition: str) -> dict[str, int]:
    field = "weight_a" if condition == "A" else "weight_b"
    weights = {row.transcript_id: getattr(row, field) for row in transcripts if getattr(row, field)}
    counts = _allocate(weights, FRAGMENTS_PER_SAMPLE - DECOY_FRAGMENTS_PER_SAMPLE)
    counts.update({row.transcript_id: 0 for row in transcripts if row.transcript_id not in counts})
    return counts


def _reverse_complement(sequence: str) -> str:
    return sequence.translate(str.maketrans("ACGT", "TGCA"))[::-1]


def _read_with_errors(sequence: str, rng: random.Random) -> str:
    return _mutate(sequence, rng, SUBSTITUTION_ERROR_RATE)


def _gzip_text(path: Path):
    raw = path.open("wb")
    stream = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6)
    return raw, stream


def _write_fasta(path: Path, entries: Iterable[tuple[str, str]]) -> None:
    with path.open("w", encoding="ascii", newline="\n") as handle:
        for name, sequence in entries:
            handle.write(f">{name}\n")
            for start in range(0, len(sequence), 80):
                handle.write(sequence[start:start + 80] + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _emit_sample(root: Path, sample: str, condition: str, seed: int,
                 transcript_rows: tuple[Transcript, ...], decoy_rows: dict[str, str]) -> dict[str, object]:
    rng = random.Random(MASTER_SEED + seed)
    counts = sample_counts(transcript_rows, condition)
    sources: list[tuple[str, str, str, str, bool]] = []
    by_id = {row.transcript_id: row for row in transcript_rows}
    for transcript_id, count in counts.items():
        row = by_id[transcript_id]
        sources.extend((transcript_id, row.gene_id, row.sequence, row.stratum, False) for _ in range(count))
    decoy_counts = _allocate({name: 1 for name in decoy_rows}, DECOY_FRAGMENTS_PER_SAMPLE)
    for name, count in decoy_counts.items():
        sources.extend((name, name, decoy_rows[name], "decoy", True) for _ in range(count))
    rng.shuffle(sources)
    if len(sources) != FRAGMENTS_PER_SAMPLE:
        raise AssertionError("Truth fragment allocation changed")

    r1_path = root / f"{sample}_R1.fastq.gz"
    r2_path = root / f"{sample}_R2.fastq.gz"
    truth_path = root / f"{sample}.truth.tsv.gz"
    r1_raw, r1_gz = _gzip_text(r1_path)
    r2_raw, r2_gz = _gzip_text(r2_path)
    truth_raw, truth_gz = _gzip_text(truth_path)
    try:
        truth_gz.write(b"fragment_id\tsource_transcript\tsource_gene\tcondition\tstratum\tdecoy\n")
        for number, (source, gene, sequence, stratum, is_decoy) in enumerate(sources, start=1):
            fragment_length = max(READ_LENGTH * 2, min(len(sequence), round(rng.gauss(FRAGMENT_MEAN, FRAGMENT_SD))))
            start = rng.randrange(0, len(sequence) - fragment_length + 1)
            fragment = sequence[start:start + fragment_length]
            # ISR: mate 1 is reverse relative to the transcript; mate 2 is forward.
            r1 = _read_with_errors(_reverse_complement(fragment[-READ_LENGTH:]), rng)
            r2 = _read_with_errors(fragment[:READ_LENGTH], rng)
            fragment_id = f"HBT{seed:04d}{number:08d}"
            quality = "I" * READ_LENGTH
            r1_gz.write(f"@{fragment_id}/1\n{r1}\n+\n{quality}\n".encode())
            r2_gz.write(f"@{fragment_id}/2\n{r2}\n+\n{quality}\n".encode())
            truth_gz.write(
                f"{fragment_id}\t{source}\t{gene}\t{condition}\t{stratum}\t{int(is_decoy)}\n".encode()
            )
    finally:
        for stream, raw in ((r1_gz, r1_raw), (r2_gz, r2_raw), (truth_gz, truth_raw)):
            stream.close()
            raw.close()
    # Full read-through verifies gzip CRC and record cardinality without retaining reads.
    read_counts = []
    for path in (r1_path, r2_path):
        with gzip.open(path, "rt", encoding="ascii") as handle:
            line_count = sum(1 for _ in handle)
        if line_count % 4:
            raise ValueError(f"Malformed generated FASTQ: {path.name}")
        read_counts.append(line_count // 4)
    if read_counts != [FRAGMENTS_PER_SAMPLE, FRAGMENTS_PER_SAMPLE]:
        raise ValueError("Generated paired FASTQ count mismatch")
    return {
        "sample": sample, "condition": condition, "seed": seed,
        "fragments": FRAGMENTS_PER_SAMPLE,
        "transcript_origin_fragments": FRAGMENTS_PER_SAMPLE - DECOY_FRAGMENTS_PER_SAMPLE,
        "decoy_origin_fragments": DECOY_FRAGMENTS_PER_SAMPLE,
        "r1_sha256": _sha256(r1_path), "r2_sha256": _sha256(r2_path),
        "truth_sha256": _sha256(truth_path), "transcript_counts": counts,
    }


def generate(root: Path) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=False)
    transcript_rows = transcriptome()
    decoy_rows = decoys(transcript_rows)
    transcript_fasta = root / "transcripts.fa"
    genome_fasta = root / "genome-decoys.fa"
    gentrome_fasta = root / "gentrome.fa"
    decoy_list = root / "decoys.txt"
    gene_map = root / "genes.gtf"
    _write_fasta(transcript_fasta, ((row.transcript_id, row.sequence) for row in transcript_rows))
    _write_fasta(genome_fasta, decoy_rows.items())
    _write_fasta(gentrome_fasta, [
        *((row.transcript_id, row.sequence) for row in transcript_rows), *decoy_rows.items(),
    ])
    decoy_list.write_text("".join(name + "\n" for name in decoy_rows), encoding="ascii", newline="\n")
    gene_map.write_text("".join(
        f'{row.transcript_id}\tharako\texon\t1\t{len(row.sequence)}\t.\t+\t.\t'
        f'gene_id "{row.gene_id}"; transcript_id "{row.transcript_id}";\n'
        for row in transcript_rows
    ), encoding="ascii", newline="\n")
    samples = [_emit_sample(root, *sample, transcript_rows, decoy_rows) for sample in SAMPLES]
    files = (transcript_fasta, genome_fasta, gentrome_fasta, decoy_list, gene_map)
    payload: dict[str, object] = {
        "fixture_id": FIXTURE_ID, "generator_version": GENERATOR_VERSION,
        "master_seed": MASTER_SEED, "read_length": READ_LENGTH,
        "fragment_length_mean": FRAGMENT_MEAN, "fragment_length_sd": FRAGMENT_SD,
        "substitution_error_rate": SUBSTITUTION_ERROR_RATE,
        "library_type": "ISR", "fragments_per_sample": FRAGMENTS_PER_SAMPLE,
        "transcript_count": len(transcript_rows),
        "gene_count": len({row.gene_id for row in transcript_rows}),
        "zero_expression_transcript_count": sum(row.weight_a == row.weight_b == 0 for row in transcript_rows),
        "decoy_count": len(decoy_rows),
        "transcripts": [
            {"transcript_id": row.transcript_id, "gene_id": row.gene_id,
             "stratum": row.stratum, "group_id": row.group_id, "length": len(row.sequence)}
            for row in transcript_rows
        ],
        "samples": samples,
        "reference_files": {path.name: _sha256(path) for path in files},
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["scientific_manifest_sha256"] = hashlib.sha256(encoded).hexdigest()
    (root / "manifest.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = generate(args.output.resolve())
    print(json.dumps({
        "fixture_id": payload["fixture_id"],
        "scientific_manifest_sha256": payload["scientific_manifest_sha256"],
        "samples": len(payload["samples"]),
    }))


if __name__ == "__main__":
    main()
