"""Sample WSL GPU and host resources during a bounded qualification run."""

from __future__ import annotations

import argparse
import csv
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


NVIDIA_SMI = "/usr/lib/wsl/lib/nvidia-smi"
GPU_QUERY = (
    "index,uuid,name,memory.total,memory.used,utilization.gpu,"
    "power.draw,temperature.gpu"
)


def _meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
        key, raw = line.split(":", 1)
        values[key] = int(raw.strip().split()[0]) * 1024
    return values


def _cpu_ticks() -> tuple[int, int]:
    fields = Path("/proc/stat").read_text(encoding="ascii").splitlines()[0].split()[1:]
    ticks = [int(value) for value in fields]
    idle = ticks[3] + (ticks[4] if len(ticks) > 4 else 0)
    return sum(ticks), idle


def monitor(gpu_log: Path, resource_log: Path, interval: float) -> None:
    gpu_log.parent.mkdir(parents=True, exist_ok=True)
    resource_log.parent.mkdir(parents=True, exist_ok=True)
    previous_total, previous_idle = _cpu_ticks()
    with gpu_log.open("x", encoding="utf-8", newline="") as gpu_handle, resource_log.open(
        "x", encoding="utf-8", newline=""
    ) as resource_handle:
        gpu_writer = csv.writer(gpu_handle)
        resource_writer = csv.writer(resource_handle)
        gpu_writer.writerow([
            "timestamp_utc", "index", "uuid", "name", "memory_total_mib", "memory_used_mib",
            "utilization_gpu_percent", "power_draw_w", "temperature_c",
        ])
        resource_writer.writerow([
            "timestamp_utc", "cpu_utilization_percent", "memory_total_bytes", "memory_available_bytes",
        ])
        while True:
            timestamp = datetime.now(timezone.utc).isoformat()
            completed = subprocess.run(
                [NVIDIA_SMI, f"--query-gpu={GPU_QUERY}", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(f"nvidia-smi failed: {completed.stderr.strip()}")
            for line in completed.stdout.splitlines():
                gpu_writer.writerow([timestamp, *(field.strip() for field in line.split(","))])
            total, idle = _cpu_ticks()
            delta_total, delta_idle = total - previous_total, idle - previous_idle
            cpu = 0.0 if delta_total <= 0 else 100.0 * (delta_total - delta_idle) / delta_total
            memory = _meminfo()
            resource_writer.writerow([timestamp, f"{cpu:.3f}", memory["MemTotal"], memory["MemAvailable"]])
            gpu_handle.flush()
            resource_handle.flush()
            previous_total, previous_idle = total, idle
            time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu-log", type=Path, required=True)
    parser.add_argument("--resource-log", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    if not 0.5 <= args.interval <= 1.0:
        parser.error("interval must be between 0.5 and 1.0 seconds")
    monitor(args.gpu_log, args.resource_log, args.interval)


if __name__ == "__main__":
    main()
