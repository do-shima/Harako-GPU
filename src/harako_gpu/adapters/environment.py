"""Centralized host and execution-context detection."""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any


def operating_system() -> str:
    return platform.system() or "Unknown"


def execution_context() -> str:
    system = operating_system()
    if system == "Linux" and (
        "microsoft" in platform.release().lower()
        or "WSL_DISTRO_NAME" in os.environ
        or "WSL_INTEROP" in os.environ
    ):
        return "wsl2" if "WSL_INTEROP" in os.environ else "wsl"
    if system == "Linux":
        return "native_linux"
    if system == "Windows":
        return "windows"
    return system.lower() or "unknown"


def host_ram_bytes() -> int | None:
    if operating_system() == "Windows":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong),
                ("total_phys", ctypes.c_ulonglong), ("avail_phys", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong), ("avail_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong), ("avail_virtual", ctypes.c_ulonglong),
                ("avail_extended_virtual", ctypes.c_ulonglong),
            ]
        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.total_phys)
        return None
    try:
        values: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, value = line.split(":", 1)
            values[key] = int(value.strip().split()[0]) * 1024
        return values.get("MemTotal")
    except (OSError, ValueError, IndexError):
        return None


def host_snapshot(cwd: Path) -> dict[str, Any]:
    usage = shutil.disk_usage(cwd)
    return {
        "os": operating_system(),
        "execution_context": execution_context(),
        "cpu": {"logical_count": os.cpu_count(), "processor": platform.processor() or platform.machine()},
        "host_ram_bytes": host_ram_bytes(),
        "disk": {"path": str(cwd.resolve()), "total_bytes": usage.total, "free_bytes": usage.free},
        "python": {
            "version": platform.python_version(), "executable": sys.executable,
            "implementation": platform.python_implementation(),
        },
    }


def executable(name: str) -> str | None:
    return shutil.which(name)

