"""Acquire the one preregistered ENA run and create fixed nested subsets."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path


EXPECTED_SELECTION_ID = "medium-human-err188044-v1"
EXPECTED_ACCESSION = "ERR188044"
LEVELS = (("C1_1M", 1_000_000), ("C2_5M", 5_000_000), ("C3_10M", 10_000_000), ("C4_20M", 20_000_000))


def digests(path: Path) -> tuple[str, str]:
    md5 = hashlib.md5()  # noqa: S324 - required official transport identity
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024**2), b""):
            md5.update(block); sha.update(block)
    return md5.hexdigest(), sha.hexdigest()


def record(handle) -> tuple[bytes, bytes, bytes, bytes] | None:
    lines = tuple(handle.readline() for _ in range(4))
    if not lines[0]:
        if any(lines[1:]):
            raise ValueError("Truncated FASTQ record")
        return None
    if any(not line for line in lines) or not lines[0].startswith(b"@") or not lines[2].startswith(b"+"):
        raise ValueError("Invalid four-line FASTQ record")
    if len(lines[1].rstrip()) != len(lines[3].rstrip()):
        raise ValueError("FASTQ sequence/quality length mismatch")
    return lines  # type: ignore[return-value]


def qname(header: bytes) -> bytes:
    value = header[1:].strip().split(maxsplit=1)[0]
    return value[:-2] if value.endswith((b"/1", b"/2")) else value


def writer(path: Path):
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".partial", dir=path.parent)
    raw = os.fdopen(descriptor, "wb")
    compressed = gzip.GzipFile(filename="", mode="wb", compresslevel=6, fileobj=raw, mtime=0)
    return Path(temporary), raw, compressed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--selection", required=True)
    args = parser.parse_args()
    runtime = Path(args.runtime_root).resolve()
    if str(runtime).startswith(("/mnt/c", "/mnt/d")):
        raise SystemExit("runtime root must be WSL ext4")
    selection = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    if selection["selection_id"] != EXPECTED_SELECTION_ID or selection["selected_accession"] != EXPECTED_ACCESSION:
        raise SystemExit("Dataset preregistration identity mismatch")
    source = runtime / "capacity/source"; source.mkdir(parents=True, exist_ok=True)
    started = time.monotonic(); source_rows = []
    for item in selection["fastq"]:
        destination = source / item["name"]
        if destination.exists():
            raise SystemExit(f"Duplicate download refused: {destination}")
        temporary = destination.with_suffix(destination.suffix + ".partial")
        if temporary.exists():
            raise SystemExit(f"Partial prior download requires audit: {temporary}")
        allowed = f"https://ftp.sra.ebi.ac.uk/vol1/fastq/ERR188/ERR188044/{item['name']}"
        if item["url"] != allowed:
            raise SystemExit("Non-preregistered URL refused")
        command = ["curl", "--fail", "--location", "--proto", "=https", "--output", str(temporary), item["url"]]
        result = subprocess.run(command, check=False)
        if result.returncode:
            raise SystemExit(f"ENA download failed for {item['role']}: {result.returncode}")
        if temporary.stat().st_size != item["bytes"]:
            raise SystemExit(f"ENA byte-size mismatch for {item['role']}")
        md5, sha = digests(temporary)
        if md5 != item["md5"]:
            raise SystemExit(f"ENA MD5 mismatch for {item['role']}")
        os.replace(temporary, destination)
        source_rows.append({**item, "sha256": sha, "download_command": command})

    fixture_root = runtime / "capacity/fixtures"
    if fixture_root.exists():
        raise SystemExit("Capacity fixtures already exist; refusing overwrite")
    outputs: dict[str, tuple[Path, Path]] = {}
    active: dict[str, tuple[tuple[Path, object, object], tuple[Path, object, object]]] = {}
    for level, _ in LEVELS:
        directory = fixture_root / level; directory.mkdir(parents=True)
        left, right = directory / f"{EXPECTED_ACCESSION}_1.fastq.gz", directory / f"{EXPECTED_ACCESSION}_2.fastq.gz"
        outputs[level] = left, right
        active[level] = writer(left), writer(right)
    lengths: Counter[int] = Counter(); count = 0
    with gzip.open(source / f"{EXPECTED_ACCESSION}_1.fastq.gz", "rb") as r1, gzip.open(
        source / f"{EXPECTED_ACCESSION}_2.fastq.gz", "rb"
    ) as r2:
        while True:
            one, two = record(r1), record(r2)
            if one is None and two is None:
                break
            if one is None or two is None:
                raise SystemExit("Orphan FASTQ record")
            count += 1
            if qname(one[0]) != qname(two[0]):
                raise SystemExit(f"R1/R2 QNAME mismatch at pair {count}")
            lengths[len(one[1].rstrip())] += 1; lengths[len(two[1].rstrip())] += 1
            for level, maximum in LEVELS:
                if count <= maximum:
                    active[level][0][2].writelines(one); active[level][1][2].writelines(two)
            for level, maximum in LEVELS:
                if count == maximum:
                    for temporary, raw, compressed in active[level]:
                        compressed.close(); raw.close()
                    for temporary, destination in zip((active[level][0][0], active[level][1][0]), outputs[level]):
                        os.replace(temporary, destination)
        if count < LEVELS[-1][1]:
            raise SystemExit(f"Source contains only {count} pairs; 20M preregistered subset unavailable")
    subset_rows = []
    for level, pairs in LEVELS:
        files = []
        for role, path in zip(("R1", "R2"), outputs[level]):
            md5, sha = digests(path)
            with gzip.open(path, "rb") as handle:
                while handle.read(8 * 1024**2):
                    pass
            files.append({"role": role, "path": str(path), "bytes": path.stat().st_size, "md5": md5, "sha256": sha})
        subset_rows.append({"level": level, "paired_fragments": pairs, "files": files})
    result = {
        "schema_version": 1, "selection_id": EXPECTED_SELECTION_ID, "accession": EXPECTED_ACCESSION,
        "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": source_rows, "observed_paired_fragments": count, "orphans": 0,
        "read_length_distribution": {str(key): value for key, value in sorted(lengths.items())},
        "subsets": subset_rows, "subset_policy": "deterministic_first_n_nested_prefix_gzip_mtime_0_level_6",
        "wall_seconds": time.monotonic() - started,
    }
    (source / "source-and-subsets-manifest.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"observed_paired_fragments": count, "subsets": [row["level"] for row in subset_rows]}, indent=2))


if __name__ == "__main__":
    main()
