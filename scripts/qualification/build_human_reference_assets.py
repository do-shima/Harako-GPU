"""Build the fixed GENCODE 49 human-only capacity reference assets.

Run inside WSL. Network access is restricted to the one pinned official GENCODE
GTF URL; the already-qualified genome and transcript sources are reused.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import time
import urllib.request
from pathlib import Path


GTF_URL = "https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_49/gencode.v49.primary_assembly.annotation.gtf.gz"
GTF_MD5 = "8486a6bdcd27a8a7a08232d01cc13b77"
GENOME_SHA256 = "3023c0705e83e86309271b09e25bdf678945fac98ce2fe5bb6b6e068f2225452"
TRANSCRIPTS_SHA256 = "08ee7ee86514061de6fd62dc643c2fe962fbc393080589ebc491bd11e22b119e"


def digest(path: Path, name: str = "sha256") -> str:
    value = hashlib.new(name)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024**2), b""):
            value.update(chunk)
    return value.hexdigest()


def fasta_headers(path: Path) -> list[str]:
    headers = []
    with path.open("rt", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith(">"):
                headers.append(line[1:].strip())
    return headers


def normalized_transcript_targets(source: Path, destination: Path) -> tuple[list[str], dict[str, str]]:
    """Write ENST-only target identifiers and return their fixed gene mapping."""
    targets: list[str] = []
    mapping: dict[str, str] = {}
    with source.open("rt", encoding="utf-8") as incoming, destination.open(
        "x", encoding="utf-8", newline="\n"
    ) as outgoing:
        for line in incoming:
            if not line.startswith(">"):
                outgoing.write(line)
                continue
            header = line[1:].strip()
            fields = header.split("|")
            if len(fields) < 2 or not fields[0].startswith("ENST") or not fields[1].startswith("ENSG"):
                raise SystemExit(f"Unexpected GENCODE transcript header: {header}")
            transcript, gene = fields[0], fields[1]
            if transcript in mapping:
                raise SystemExit(f"Duplicate normalized transcript identifier: {transcript}")
            mapping[transcript] = gene
            targets.append(transcript)
            outgoing.write(f">{transcript}\n")
    return targets, mapping


def decompress(source: Path, destination: Path) -> None:
    if destination.exists():
        raise ValueError(f"Refusing to overwrite {destination}")
    with gzip.open(source, "rb") as incoming, destination.open("xb") as outgoing:
        shutil.copyfileobj(incoming, outgoing, 8 * 1024**2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True)
    args = parser.parse_args()
    runtime = Path(args.runtime_root).resolve()
    if not runtime.is_absolute() or str(runtime).startswith(("/mnt/c", "/mnt/d")):
        raise SystemExit("runtime root must be WSL ext4")
    source = runtime / "external-truth/references/gencode-v49"
    genome_gz = source / "GRCh38.primary_assembly.genome.fa.gz"
    transcripts_gz = source / "gencode.v49.transcripts.fa.gz"
    if digest(genome_gz) != GENOME_SHA256 or digest(transcripts_gz) != TRANSCRIPTS_SHA256:
        raise SystemExit("Existing GENCODE source identity mismatch")
    root = runtime / "capacity/references/human_grch38p14_gencode49_harako_gpu_v1"
    if root.exists():
        raise SystemExit(f"Reference pack already exists: {root}")
    assets = root / "assets"; assets.mkdir(parents=True)
    gtf_gz = assets / "gencode.v49.primary_assembly.annotation.gtf.gz"
    started = time.monotonic()
    urllib.request.urlretrieve(GTF_URL, gtf_gz)
    if digest(gtf_gz, "md5") != GTF_MD5:
        raise SystemExit("Official GTF MD5 mismatch")
    genome = assets / "GRCh38.primary_assembly.genome.fa"
    transcripts = assets / "gencode.v49.transcripts.fa"
    gtf = assets / "gencode.v49.primary_assembly.annotation.gtf"
    decompress(genome_gz, genome); decompress(transcripts_gz, transcripts); decompress(gtf_gz, gtf)
    transcript_headers = fasta_headers(transcripts)
    genome_headers = fasta_headers(genome)
    if len(transcript_headers) != len(set(transcript_headers)):
        raise SystemExit("Duplicate transcript FASTA identifiers")
    if len(genome_headers) != len(set(genome_headers)):
        raise SystemExit("Duplicate genome FASTA identifiers")
    transcript_targets = assets / "gencode.v49.transcript_targets.fa"
    target_ids, transcript_to_gene = normalized_transcript_targets(transcripts, transcript_targets)
    if len(target_ids) != len(transcript_headers):
        raise SystemExit("Normalized transcript inventory mismatch")
    gentrome = assets / "gencode.v49.primary.gentrome.fa"
    with gentrome.open("xb") as output:
        with transcript_targets.open("rb") as handle: shutil.copyfileobj(handle, output, 8 * 1024**2)
        with genome.open("rb") as handle: shutil.copyfileobj(handle, output, 8 * 1024**2)
    decoys = assets / "gencode.v49.primary.decoys.txt"
    decoys.write_text("\n".join(item.split()[0] for item in genome_headers) + "\n", encoding="utf-8")
    tx2gene = assets / "gencode.v49.primary.tx2gene.tsv"
    with tx2gene.open("x", encoding="utf-8", newline="\n") as output:
        output.write("transcript_id\tgene_id\n")
        for transcript in target_ids:
            output.write(f"{transcript}\t{transcript_to_gene[transcript]}\n")
    genome_contigs = {item.split()[0] for item in genome_headers}
    gtf_contigs: set[str] = set(); genes: set[str] = set(); gtf_transcripts: set[str] = set()
    with gtf.open("rt", encoding="utf-8") as handle:
        for line in handle:
            if not line or line.startswith("#"): continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) != 9: raise SystemExit("Invalid GTF row")
            gtf_contigs.add(fields[0])
            for token in fields[8].split(";"):
                token = token.strip()
                if token.startswith("gene_id "): genes.add(token.split('"')[1])
                elif token.startswith("transcript_id "): gtf_transcripts.add(token.split('"')[1])
    missing_contigs = sorted(gtf_contigs - genome_contigs)
    if missing_contigs:
        raise SystemExit(f"GTF contigs absent from genome: {missing_contigs[:5]}")
    files = {}
    for path in sorted(assets.iterdir()):
        if path.is_file(): files[path.name] = {"bytes": path.stat().st_size, "sha256": digest(path)}
    manifest = {
        "schema_version": 1, "reference_pack_id": "human_grch38p14_gencode49_harako_gpu_v1",
        "assembly": "GRCh38.p14 primary assembly", "annotation_provider": "GENCODE", "release": "49",
        "human_only": True, "sirv_targets": 0, "ercc_targets": 0,
        "source": {"genome_gzip_path": str(genome_gz), "genome_gzip_sha256": GENOME_SHA256,
                   "transcripts_gzip_path": str(transcripts_gz), "transcripts_gzip_sha256": TRANSCRIPTS_SHA256,
                   "gtf_url": GTF_URL, "gtf_md5": GTF_MD5},
        "inventory": {"genome_contigs": len(genome_headers), "gtf_contigs": len(gtf_contigs),
                      "transcript_fasta_records": len(transcript_headers),
                      "normalized_target_ids": len(target_ids), "target_id_policy": "ENST versioned identifier",
                      "gtf_transcript_ids": len(gtf_transcripts),
                      "gtf_gene_ids": len(genes), "contig_compatibility": "PASS"},
        "files": files, "wall_seconds": time.monotonic() - started,
    }
    manifest_path = root / "reference-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
