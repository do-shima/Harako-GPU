"""Best-effort WSL and native-Linux resource sampling."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harako_gpu.adapters.execution_context import ExecutionContext
from harako_gpu.adapters.process import ProcessRunner


@dataclass
class ResourceMonitor:
    execution: ExecutionContext
    work_root: str
    result_root: str
    log_path: Path
    runner: ProcessRunner
    previous_cpu: tuple[int, int] | None = None
    last_storage_sample: float = 0.0
    work_current_bytes: int | None = None
    result_current_bytes: int | None = None
    work_peak_bytes: int = 0
    result_peak_bytes: int = 0
    latest: dict[str, Any] | None = None
    warning: str | None = None
    _stop_event: threading.Event | None = None
    _thread: threading.Thread | None = None

    def _probe(self, argv: tuple[str, ...], timeout: float = 5) -> str:
        command = (argv if self.execution.is_native_linux else
                   ("wsl.exe", "--distribution", str(self.execution.distribution), "--exec", *argv))
        result = self.runner.run(command, timeout=timeout)
        if not result.ok:
            raise ValueError(result.stderr or result.exception or "resource probe failed")
        return result.stdout.strip()

    def _probe_optional(self, argv: tuple[str, ...], timeout: float = 5) -> str:
        try:
            return self._probe(argv, timeout=timeout)
        except ValueError:
            return ""

    def _nvidia_smi(self) -> str:
        return "nvidia-smi" if self.execution.is_native_linux else "/usr/lib/wsl/lib/nvidia-smi"

    def sample(self) -> dict[str, Any]:
        try:
            gpu = self._probe((self._nvidia_smi(), "--query-gpu=uuid,memory.used,memory.total,utilization.gpu,power.draw,temperature.gpu,pstate,clocks_event_reasons.active",
                             "--format=csv,noheader,nounits"))
            mem = self._probe(("/usr/bin/cat", "/proc/meminfo"))
            cpu = self._probe(("/usr/bin/head", "-n", "1", "/proc/stat"))
            load = self._probe(("/usr/bin/cat", "/proc/loadavg"))
            processes = self._probe(("/usr/bin/ps", "-eo", "rss=,pcpu=,comm="))
            cgroup = self._probe_optional(("/usr/bin/cat", "/sys/fs/cgroup/memory.current"))
            memory_psi = self._probe_optional(("/usr/bin/cat", "/proc/pressure/memory"))
            disks = self._probe(("/usr/bin/df", "-Pk", "--", self.work_root, self.result_root))
            fields = [item.strip() for item in gpu.splitlines()[0].split(",")]
            memory_keys = {"MemTotal", "MemAvailable", "Cached", "Buffers", "SwapTotal", "SwapFree"}
            memory = {line.split(":", 1)[0]: int(line.split(":", 1)[1].strip().split()[0]) * 1024
                      for line in mem.splitlines() if ":" in line and line.split(":", 1)[0] in memory_keys}
            cpu_values = [int(item) for item in cpu.split()[1:]]
            idle = cpu_values[3] + (cpu_values[4] if len(cpu_values) > 4 else 0)
            iowait = cpu_values[4] if len(cpu_values) > 4 else 0
            total = sum(cpu_values)
            utilization = None
            iowait_percent = None
            if self.previous_cpu:
                previous_idle, previous_total = self.previous_cpu
                delta_total, delta_idle = total - previous_total, idle - previous_idle
                utilization = (1 - delta_idle / delta_total) * 100 if delta_total > 0 else None
                previous_iowait = getattr(self, "_previous_iowait", iowait)
                iowait_percent = (iowait - previous_iowait) / delta_total * 100 if delta_total > 0 else None
            self.previous_cpu = (idle, total)
            self._previous_iowait = iowait
            process_rss_kib = 0
            process_cpu = 0.0
            relevant = {"java", "nextflow", "pbrun", "STAR", "fastp", "salmon", "samtools"}
            for line in processes.splitlines():
                parts = line.split(None, 2)
                if len(parts) == 3 and parts[2] in relevant:
                    process_rss_kib += int(parts[0])
                    process_cpu += float(parts[1])
            psi_match = re.search(r"some\s+avg10=([0-9.]+)", memory_psi)
            loads = load.split()
            disk_lines = [line.split() for line in disks.splitlines()[1:] if line.strip()]
            free = [int(line[3]) * 1024 for line in disk_lines if len(line) >= 6]
            now = time.monotonic()
            if now - self.last_storage_sample >= 5:
                argv = ("/usr/bin/du", "-sb", "--", self.work_root, self.result_root)
                command = (argv if self.execution.is_native_linux else
                           ("wsl.exe", "--distribution", str(self.execution.distribution), "--exec", *argv))
                storage = self.runner.run(command, timeout=30)
                self.last_storage_sample = now
                rows = [line.split("\t", 1) for line in storage.stdout.splitlines() if "\t" in line]
                observed = {row[1]: int(row[0]) for row in rows}
                self.work_current_bytes = observed.get(self.work_root)
                self.result_current_bytes = observed.get(self.result_root)
                self.work_peak_bytes = max(self.work_peak_bytes, self.work_current_bytes or 0)
                self.result_peak_bytes = max(self.result_peak_bytes, self.result_current_bytes or 0)
                if not storage.ok:
                    detail = storage.stderr or storage.exception or "partial du result"
                    self.warning = f"RESOURCE_STORAGE_PARTIAL: {detail.strip()}"
            sample = {
                "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "gpu_uuid": fields[0], "vram_used_mib": float(fields[1]), "vram_total_mib": float(fields[2]),
                "gpu_utilization_percent": float(fields[3]), "power_watts": float(fields[4]),
                "temperature_c": float(fields[5]), "performance_state": fields[6],
                "throttle_reason": fields[7], "ram_used_bytes": memory["MemTotal"] - memory["MemAvailable"],
                "ram_available_bytes": memory["MemAvailable"], "ram_total_bytes": memory["MemTotal"],
                "page_cache_bytes": memory.get("Cached", 0) + memory.get("Buffers", 0),
                "swap_used_bytes": memory.get("SwapTotal", 0) - memory.get("SwapFree", 0),
                "cpu_utilization_percent": utilization,
                "cpu_iowait_percent": iowait_percent,
                "load_average_1m": float(loads[0]) if loads else None,
                "load_average_5m": float(loads[1]) if len(loads) > 1 else None,
                "load_average_15m": float(loads[2]) if len(loads) > 2 else None,
                "workflow_process_rss_bytes": process_rss_kib * 1024,
                "workflow_process_cpu_percent": process_cpu,
                "cgroup_memory_bytes": int(cgroup) if cgroup.isdigit() else None,
                "memory_psi_some_avg10": float(psi_match.group(1)) if psi_match else None,
                "work_free_bytes": free[0] if free else None, "result_free_bytes": free[-1] if free else None,
                "work_current_bytes": self.work_current_bytes, "work_peak_bytes": self.work_peak_bytes,
                "result_current_bytes": self.result_current_bytes, "result_peak_bytes": self.result_peak_bytes,
            }
            self.latest = sample
            self._append(sample)
            return sample
        except (ValueError, OSError, IndexError, KeyError) as exc:
            self.warning = f"RESOURCE_MONITOR_UNAVAILABLE: {exc}"
            return {"status": "RESOURCE_MONITOR_UNAVAILABLE", "detail": str(exc)}

    def _append(self, sample: dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        fields = (
            "timestamp", "gpu_uuid", "vram_used_mib", "vram_total_mib", "gpu_utilization_percent",
            "power_watts", "temperature_c", "performance_state", "throttle_reason", "ram_used_bytes",
            "ram_available_bytes", "ram_total_bytes", "page_cache_bytes", "swap_used_bytes",
            "cpu_utilization_percent", "cpu_iowait_percent", "load_average_1m", "load_average_5m",
            "load_average_15m", "workflow_process_rss_bytes", "workflow_process_cpu_percent",
            "cgroup_memory_bytes", "memory_psi_some_avg10", "work_free_bytes", "result_free_bytes", "work_current_bytes",
            "work_peak_bytes", "result_current_bytes", "result_peak_bytes",
        )
        new = not self.log_path.exists()
        with self.log_path.open("a", encoding="utf-8", newline="\n") as handle:
            if new:
                handle.write("\t".join(fields) + "\n")
            handle.write("\t".join("" if sample.get(key) is None else str(sample.get(key)) for key in fields) + "\n")

    @property
    def snapshot(self) -> dict[str, Any]:
        if self.latest is not None:
            return dict(self.latest)
        if self.warning:
            return {"status": "RESOURCE_MONITOR_UNAVAILABLE", "detail": self.warning}
        return {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            raise ValueError("Resource monitor is already running")
        self._stop_event = threading.Event()

        def poll() -> None:
            while self._stop_event and not self._stop_event.is_set():
                self.sample()
                self._stop_event.wait(1.0)

        self._thread = threading.Thread(target=poll, name="harako-resource-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._stop_event:
            self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

def parse_trace_counts(text: str) -> dict[str, int]:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return {"completed": 0, "cached": 0, "failed": 0}
    header = lines[0].split("\t")
    if "status" not in header:
        return {"completed": 0, "cached": 0, "failed": 0}
    index = header.index("status")
    values = [line.split("\t")[index].upper() for line in lines[1:] if len(line.split("\t")) > index]
    return {
        "completed": sum(value == "COMPLETED" for value in values),
        "cached": sum(value in {"CACHED", "CACHED (RESUME)"} for value in values),
        "failed": sum(value in {"FAILED", "ABORTED"} for value in values),
    }
