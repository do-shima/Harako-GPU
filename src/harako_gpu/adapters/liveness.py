"""Process liveness probes for local controllers and WSL Linux PIDs."""

from __future__ import annotations

import os

from harako_gpu.adapters.process import ProcessRunner


def local_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


def wsl_pid_alive(pid: int, *, distribution: str, runner: ProcessRunner | None = None) -> bool:
    if pid <= 0:
        return False
    process = runner or ProcessRunner()
    result = process.run(
        ("wsl.exe", "--distribution", distribution, "--exec", "/usr/bin/kill", "-0", str(pid)),
        timeout=5,
    )
    return result.ok
