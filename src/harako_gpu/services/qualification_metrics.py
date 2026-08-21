"""Parse bounded qualification monitor logs without executing runtime commands."""

from __future__ import annotations

import csv
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any


GPU_FIELDS = frozenset({
    "timestamp_utc", "index", "uuid", "name", "memory_total_mib", "memory_used_mib",
    "utilization_gpu_percent", "power_draw_w", "temperature_c",
})
RESOURCE_FIELDS = frozenset({
    "timestamp_utc", "cpu_utilization_percent", "memory_total_bytes", "memory_available_bytes",
})


def _rows(path: Path, required: frozenset[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(required - set(reader.fieldnames or ()))
        if missing:
            raise ValueError("Monitor CSV is missing fields: " + ", ".join(missing))
        rows = list(reader)
    if not rows:
        raise ValueError("Monitor CSV has no samples")
    return rows


def summarize_gpu_metrics(
    path: Path,
    *,
    interval_start: datetime | None = None,
    interval_end: datetime | None = None,
) -> dict[str, Any]:
    rows = _rows(path, GPU_FIELDS)
    if (interval_start is None) != (interval_end is None):
        raise ValueError("Both interval_start and interval_end are required")
    if interval_start is not None and interval_end is not None:
        rows = [
            row for row in rows
            if interval_start <= datetime.fromisoformat(row["timestamp_utc"]) <= interval_end
        ]
        if not rows:
            raise ValueError("GPU monitor has no samples in the requested interval")
    utilization = [float(row["utilization_gpu_percent"]) for row in rows]
    memory = [float(row["memory_used_mib"]) for row in rows]
    power = [float(row["power_draw_w"]) for row in rows]
    temperature = [float(row["temperature_c"]) for row in rows]
    identities = {(row["index"], row["uuid"], row["name"]) for row in rows}
    if len(identities) != 1:
        raise ValueError("Qualification monitor must describe exactly one GPU")
    index, uuid, name = identities.pop()
    return {
        "sample_count": len(rows),
        "gpu_index": index,
        "gpu_uuid": uuid,
        "gpu_name": name,
        "peak_vram_mib": max(memory),
        "median_gpu_utilization_percent": statistics.median(utilization),
        "maximum_gpu_utilization_percent": max(utilization),
        "peak_power_w": max(power),
        "maximum_temperature_c": max(temperature),
    }


def summarize_resource_metrics(path: Path) -> dict[str, Any]:
    rows = _rows(path, RESOURCE_FIELDS)
    total_values = {int(row["memory_total_bytes"]) for row in rows}
    if len(total_values) != 1:
        raise ValueError("Host total RAM changed within the monitor log")
    total = total_values.pop()
    available = [int(row["memory_available_bytes"]) for row in rows]
    return {
        "sample_count": len(rows),
        "peak_cpu_utilization_percent": max(float(row["cpu_utilization_percent"]) for row in rows),
        "memory_total_bytes": total,
        "minimum_memory_available_bytes": min(available),
        "peak_memory_used_bytes": total - min(available),
    }
