"""Build the three fixed full-human capacity indices inside WSL ext4."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import threading
import time
from pathlib import Path


REFERENCE_PACK = "human_grch38p14_gencode49_harako_gpu_v1"
STAR_IMAGE = "sha256:f60e2def4ddd483acd575579f3596e4f9c82b7b1b85a3caa5ebceb05194efd08"
SALMON_1103_IMAGE = "sha256:f83ebb158845ee8138d793347f83b92c75e83c58dd8f4600c6fea2a2453ef08e"
SALMON_251_IMAGE = "sha256:e6e64f39a479458ef6f007757498321ee5a3ef8a2227ff2af414fbe3c36e6f7f"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024**2), b""):
            value.update(block)
    return value.hexdigest()


def tree_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def memory() -> dict[str, int]:
    values: dict[str, int] = {}
    with Path("/proc/meminfo").open("rt", encoding="ascii") as handle:
        for line in handle:
            key, value = line.split(":", 1)
            values[key] = int(value.strip().split()[0]) * 1024
    return values


def gpu() -> tuple[str, int, int, int, float, float, str]:
    argv = (
        "nvidia-smi", "--query-gpu=uuid,memory.used,memory.total,utilization.gpu,power.draw,temperature.gpu,pstate",
        "--format=csv,noheader,nounits",
    )
    result = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=5)
    if result.returncode:
        return "UNAVAILABLE", 0, 0, 0, 0.0, 0.0, "UNKNOWN"
    fields = [item.strip() for item in result.stdout.splitlines()[0].split(",")]
    return fields[0], int(fields[1]), int(fields[2]), int(fields[3]), float(fields[4]), float(fields[5]), fields[6]


def monitor(stop: threading.Event, output: Path, measured_root: Path) -> None:
    columns = (
        "timestamp", "gpu_uuid", "vram_used_mib", "vram_total_mib", "gpu_utilization_percent",
        "power_watts", "temperature_c", "performance_state", "wsl_ram_used_bytes",
        "wsl_ram_available_bytes", "wsl_ram_total_bytes", "page_cache_bytes", "swap_used_bytes",
        "filesystem_free_bytes", "measured_tree_bytes",
    )
    with output.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        while not stop.is_set():
            ram = memory(); stat = os.statvfs(measured_root); card = gpu()
            writer.writerow({
                "timestamp": time.time(), "gpu_uuid": card[0], "vram_used_mib": card[1],
                "vram_total_mib": card[2], "gpu_utilization_percent": card[3], "power_watts": card[4],
                "temperature_c": card[5], "performance_state": card[6],
                "wsl_ram_used_bytes": ram["MemTotal"] - ram["MemAvailable"],
                "wsl_ram_available_bytes": ram["MemAvailable"], "wsl_ram_total_bytes": ram["MemTotal"],
                "page_cache_bytes": ram.get("Cached", 0) + ram.get("Buffers", 0),
                "swap_used_bytes": ram.get("SwapTotal", 0) - ram.get("SwapFree", 0),
                "filesystem_free_bytes": stat.f_bavail * stat.f_frsize,
                "measured_tree_bytes": tree_bytes(measured_root),
            })
            handle.flush()
            stop.wait(1)


def inventory(root: Path) -> tuple[list[dict[str, object]], str]:
    rows = [
        {"path": str(path.relative_to(root)), "bytes": path.stat().st_size, "sha256": digest(path)}
        for path in sorted(root.rglob("*")) if path.is_file()
    ]
    payload = json.dumps(rows, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return rows, hashlib.sha256(payload).hexdigest()


def run_stage(*, name: str, argv: list[str], output: Path, root: Path, logs: Path,
              source: dict[str, object]) -> dict[str, object]:
    if output.exists():
        raise SystemExit(f"Refusing to overwrite index directory: {output}")
    output.mkdir(parents=True)
    (logs / f"{name}.command.json").write_text(
        json.dumps({"structured_argv": argv}, indent=2) + "\n", encoding="utf-8"
    )
    stop = threading.Event()
    thread = threading.Thread(target=monitor, args=(stop, logs / f"{name}.resources.tsv", root), daemon=True)
    thread.start(); started = time.monotonic()
    with (logs / f"{name}.stdout.log").open("x", encoding="utf-8") as stdout, (
        logs / f"{name}.stderr.log"
    ).open("x", encoding="utf-8") as stderr:
        process = subprocess.run(argv, stdout=stdout, stderr=stderr, text=True, check=False)
    elapsed = time.monotonic() - started; stop.set(); thread.join(timeout=10)
    if process.returncode:
        raise SystemExit(f"{name} failed with exit code {process.returncode}")
    rows, inventory_sha = inventory(output)
    resources = list(csv.DictReader((logs / f"{name}.resources.tsv").open(encoding="utf-8"), delimiter="\t"))
    result = {
        "schema_version": 1, "index_id": "", "name": name, "source": source,
        "structured_argv": argv, "wall_seconds": elapsed, "final_bytes": tree_bytes(output),
        "file_count": len(rows), "inventory_sha256": inventory_sha, "inventory": rows,
        "resources": {
            "peak_wsl_ram_bytes": max(int(row["wsl_ram_used_bytes"]) for row in resources),
            "minimum_wsl_available_bytes": min(int(row["wsl_ram_available_bytes"]) for row in resources),
            "peak_vram_mib": max(int(row["vram_used_mib"]) for row in resources),
            "peak_measured_tree_bytes": max(int(row["measured_tree_bytes"]) for row in resources),
            "minimum_filesystem_free_bytes": min(int(row["filesystem_free_bytes"]) for row in resources),
        },
    }
    identity = hashlib.sha256(json.dumps({
        "name": name, "source": source, "argv": argv, "inventory": inventory_sha,
    }, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
    result["index_id"] = f"{name}-{identity[:16]}"
    (output.parent / f"{name}.manifest.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True)
    args = parser.parse_args()
    runtime = Path(args.runtime_root).resolve()
    if str(runtime).startswith(("/mnt/c", "/mnt/d")):
        raise SystemExit("runtime root must be WSL ext4")
    ref_root = runtime / "capacity/references" / REFERENCE_PACK
    manifest = json.loads((ref_root / "reference-manifest.json").read_text(encoding="utf-8"))
    assets = ref_root / "assets"
    if manifest["reference_pack_id"] != REFERENCE_PACK or not manifest["human_only"]:
        raise SystemExit("Reference pack identity mismatch")
    for name, metadata in manifest["files"].items():
        if digest(assets / name) != metadata["sha256"]:
            raise SystemExit(f"Reference asset identity mismatch: {name}")
    indices = runtime / "capacity/indices"; indices.mkdir(parents=True, exist_ok=True)
    logs = runtime / "capacity/logs/index-builds"; logs.mkdir(parents=True, exist_ok=True)
    uid_gid = f"{os.getuid()}:{os.getgid()}"
    mount = f"type=bind,src={assets},dst=/ref,readonly"
    common_source = {
        "reference_pack_id": REFERENCE_PACK,
        "transcript_targets_sha256": manifest["files"]["gencode.v49.transcript_targets.fa"]["sha256"],
        "genome_sha256": manifest["files"]["GRCh38.primary_assembly.genome.fa"]["sha256"],
        "gtf_sha256": manifest["files"]["gencode.v49.primary_assembly.annotation.gtf"]["sha256"],
        "gentrome_sha256": manifest["files"]["gencode.v49.primary.gentrome.fa"]["sha256"],
        "decoys_sha256": manifest["files"]["gencode.v49.primary.decoys.txt"]["sha256"],
        "tx2gene_sha256": manifest["files"]["gencode.v49.primary.tx2gene.tsv"]["sha256"],
    }
    stages = (
        ("star-2.7.2a", STAR_IMAGE, [
            "STAR", "--runThreadN", "12", "--runMode", "genomeGenerate", "--genomeDir", "/out",
            "--genomeFastaFiles", "/ref/GRCh38.primary_assembly.genome.fa", "--sjdbGTFfile",
            "/ref/gencode.v49.primary_assembly.annotation.gtf", "--sjdbOverhang", "74",
            "--limitGenomeGenerateRAM", "42000000000",
        ], {**common_source, "builder": "STAR 2.7.2a", "sjdb_overhang": 74}),
        ("salmon-1.10.3", SALMON_1103_IMAGE, [
            "salmon", "index", "--threads", "12", "-t", "/ref/gencode.v49.primary.gentrome.fa",
            "-d", "/ref/gencode.v49.primary.decoys.txt", "-k", "31", "-i", "/out",
        ], {**common_source, "builder": "Salmon 1.10.3", "kmer": 31, "format": "1.x"}),
        ("salmon-2.5.1", SALMON_251_IMAGE, [
            "salmon", "index", "--threads", "12", "-t", "/ref/gencode.v49.primary.gentrome.fa",
            "-d", "/ref/gencode.v49.primary.decoys.txt", "-k", "31", "-i", "/out",
        ], {**common_source, "builder": "Salmon 2.5.1", "kmer": 31, "format": "2.x"}),
    )
    results = []
    for name, image, command, source in stages:
        output = indices / name
        docker = [
            "docker", "run", "--rm", "--user", uid_gid, "--mount", mount,
            "--mount", f"type=bind,src={output},dst=/out", image, *command,
        ]
        results.append(run_stage(name=name, argv=docker, output=output, root=runtime / "capacity",
                                 logs=logs, source={**source, "image_identity": image}))
    (indices / "index-build-summary.json").write_text(
        json.dumps({"schema_version": 1, "indices": results}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({item["name"]: item["index_id"] for item in results}, indent=2))


if __name__ == "__main__":
    main()
