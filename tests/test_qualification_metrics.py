from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from harako_gpu.services.qualification_metrics import summarize_gpu_metrics, summarize_resource_metrics


def test_gpu_metrics_are_scoped_to_parabricks_interval(tmp_path: Path) -> None:
    path = tmp_path / "gpu.csv"
    path.write_text(
        "timestamp_utc,index,uuid,name,memory_total_mib,memory_used_mib,utilization_gpu_percent,power_draw_w,temperature_c\n"
        "2026-01-01T00:00:00+00:00,0,GPU-1,RTX,24576,1000,0,20,40\n"
        "2026-01-01T00:00:01+00:00,0,GPU-1,RTX,24576,9000,80,200,55\n"
        "2026-01-01T00:00:02+00:00,0,GPU-1,RTX,24576,8000,40,150,50\n",
        encoding="utf-8",
    )
    summary = summarize_gpu_metrics(
        path,
        interval_start=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
        interval_end=datetime(2026, 1, 1, 0, 0, 2, tzinfo=timezone.utc),
    )
    assert summary["peak_vram_mib"] == 9000
    assert summary["median_gpu_utilization_percent"] == 60
    assert summary["maximum_gpu_utilization_percent"] == 80


def test_resource_metrics_and_malformed_csv(tmp_path: Path) -> None:
    path = tmp_path / "resources.csv"
    path.write_text(
        "timestamp_utc,cpu_utilization_percent,memory_total_bytes,memory_available_bytes\n"
        "2026-01-01T00:00:00+00:00,10,1000,800\n"
        "2026-01-01T00:00:01+00:00,90,1000,300\n",
        encoding="utf-8",
    )
    summary = summarize_resource_metrics(path)
    assert summary["peak_cpu_utilization_percent"] == 90
    assert summary["peak_memory_used_bytes"] == 700
    bad = tmp_path / "bad.csv"
    bad.write_text("timestamp_utc\n2026-01-01T00:00:00+00:00\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing fields"):
        summarize_gpu_metrics(bad)
