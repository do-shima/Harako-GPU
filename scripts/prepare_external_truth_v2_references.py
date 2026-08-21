"""Prepare runtime-only SIRV/ERCC and combined GENCODE qualification references."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from zipfile import ZipFile


XLSX_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
DNA = re.compile(r"^[ACGTN]+$")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fasta_rows(path: Path):
    opener = gzip.open if path.suffix == ".gz" else path.open
    with opener(path, "rt", encoding="utf-8") if path.suffix == ".gz" else opener("r", encoding="utf-8") as handle:
        name: str | None = None
        sequence: list[str] = []
        for line in handle:
            if line.startswith(">"):
                if name is not None:
                    yield name, "".join(sequence)
                name, sequence = line[1:].strip(), []
            else:
                sequence.append(line.strip().upper())
        if name is not None:
            yield name, "".join(sequence)


def xlsx_rows(path: Path) -> list[dict[str, str]]:
    with ZipFile(path) as archive:
        shared = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        strings = ["".join(item.itertext()) for item in shared.findall("m:si", XLSX_NS)]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    result: list[dict[str, str]] = []
    for row in sheet.findall(".//m:row", XLSX_NS):
        values: dict[str, str] = {}
        for cell in row.findall("m:c", XLSX_NS):
            value = cell.find("m:v", XLSX_NS)
            if value is None or value.text is None:
                continue
            column = "".join(char for char in cell.attrib["r"] if char.isalpha())
            values[column] = strings[int(value.text)] if cell.attrib.get("t") == "s" else value.text
        result.append(values)
    return result


def extract_sirv_design(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    sequences: dict[str, str] = {}
    genes: dict[str, str] = {}
    for row in xlsx_rows(path):
        name = row.get("G", "").rstrip("*")
        if row.get("C") != "1" or row.get("K") != "1" or not re.fullmatch(r"SIRV\d{3}", name):
            continue
        sequence = row.get("AC", "").upper()
        if not sequence or not DNA.fullmatch(sequence) or int(row["H"]) != len(sequence):
            raise ValueError(f"Invalid official SIRV sequence row: {name}")
        if name in sequences:
            raise ValueError(f"Duplicate SIRV target: {name}")
        sequences[name] = sequence
        genes[name] = name[:5]
    if len(sequences) != 69 or len(set(genes.values())) != 7:
        raise ValueError("Official E0 design must contain 69 equimolar transcripts from seven genes")
    return dict(sorted(sequences.items())), dict(sorted(genes.items()))


def identifiability(sequences: dict[str, str], *, kmer: int = 31, read_length: int = 120) -> list[dict[str, object]]:
    if read_length < kmer:
        raise ValueError("Read geometry must cover the identifiability k-mer")
    owners: dict[str, set[str]] = {}
    for name, sequence in sequences.items():
        for offset in range(len(sequence) - kmer + 1):
            owners.setdefault(sequence[offset:offset + kmer], set()).add(name)
    rows: list[dict[str, object]] = []
    for name, sequence in sequences.items():
        unique = sum(
            owners[sequence[offset:offset + kmer]] == {name}
            for offset in range(len(sequence) - kmer + 1)
        )
        if unique:
            classification = "transcript-identifiable"
        else:
            classification = "equivalence-group-identifiable"
        rows.append({
            "transcript_id": name,
            "gene_id": name[:5],
            "length": len(sequence),
            "gc_fraction": (sequence.count("G") + sequence.count("C")) / len(sequence),
            "unique_31mer_count": unique,
            "read_length": read_length,
            "classification": classification,
            "equivalence_group": name[:5] if not unique else name,
        })
    return rows


def write_fasta(path: Path, rows) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for name, sequence in rows:
            handle.write(f">{name}\n")
            for offset in range(0, len(sequence), 80):
                handle.write(sequence[offset:offset + 80] + "\n")
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx", type=Path, required=True)
    parser.add_argument("--human-transcripts", type=Path, required=True)
    parser.add_argument("--human-genome", type=Path, required=True)
    parser.add_argument("--ercc-fasta", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    sirv, genes = extract_sirv_design(args.xlsx.resolve())
    sirv_fasta = output / "sirv69.fa"
    write_fasta(sirv_fasta, sirv.items())
    sirv_map = output / "sirv69.tx2gene.tsv"
    sirv_map.write_text("".join(f"{name}\t{genes[name]}\n" for name in sirv), encoding="utf-8", newline="\n")
    ident_path = output / "sirv69.identifiability.json"
    ident_path.write_text(json.dumps(identifiability(sirv), indent=2) + "\n", encoding="utf-8", newline="\n")

    combined = output / "gencode.v49.sirv69.gentrome.fa"
    combined_map = output / "gencode.v49.sirv69.tx2gene.tsv"
    target_count = 0
    with combined.open("w", encoding="utf-8", newline="\n") as fasta, combined_map.open("w", encoding="utf-8", newline="\n") as mapping:
        for header, sequence in fasta_rows(args.human_transcripts.resolve()):
            target = header.split()[0]
            fields = target.split("|")
            if len(fields) < 2 or not fields[0].startswith("ENST") or not fields[1].startswith("ENSG"):
                raise ValueError(f"Unrecognized GENCODE transcript header: {header}")
            fasta.write(f">{target}\n{sequence}\n")
            mapping.write(f"{target}\t{fields[1]}\n")
            target_count += 1
        for name, sequence in sirv.items():
            fasta.write(f">{name}\n{sequence}\n")
            mapping.write(f"{name}\t{genes[name]}\n")
            target_count += 1
        for header, sequence in fasta_rows(args.human_genome.resolve()):
            fasta.write(f">{header.split()[0]}\n{sequence}\n")

    decoys = output / "gencode.v49.primary.decoys.txt"
    genome_names = [header.split()[0] for header, _ in fasta_rows(args.human_genome.resolve())]
    decoys.write_text("\n".join(genome_names) + "\n", encoding="utf-8", newline="\n")
    ercc_count = sum(1 for _ in fasta_rows(args.ercc_fasta.resolve()))
    if ercc_count != 92:
        raise ValueError("Official ERCC FASTA must contain exactly 92 targets")

    manifest = {
        "schema_version": 1,
        "gencode_release": "49",
        "assembly": "GRCh38.p14 primary assembly",
        "salmon_version": "2.5.1",
        "kmer": 31,
        "human_transcript_count": target_count - 69,
        "sirv_transcript_count": 69,
        "combined_target_count": target_count,
        "human_decoy_count": len(genome_names),
        "ercc_target_count": ercc_count,
        "sources": {
            "sirv_design_xlsx_sha256": sha256_path(args.xlsx.resolve()),
            "human_transcripts_gzip_sha256": sha256_path(args.human_transcripts.resolve()),
            "human_genome_gzip_sha256": sha256_path(args.human_genome.resolve()),
            "ercc_fasta_sha256": sha256_path(args.ercc_fasta.resolve()),
        },
        "outputs": {
            path.name: sha256_path(path) for path in (sirv_fasta, sirv_map, ident_path, combined, combined_map, decoys)
        },
    }
    (output / "reference-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
