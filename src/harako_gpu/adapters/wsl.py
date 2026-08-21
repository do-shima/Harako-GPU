"""Read-only WSL inspection using fixed argv."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .process import CommandResult, ProcessRunner


WSL_NVIDIA_SMI_FALLBACK = "/usr/lib/wsl/lib/nvidia-smi"


@dataclass(frozen=True)
class WslNvidiaProbe:
    result: CommandResult
    executed_path: str | None
    path_exported: bool
    reason_code: str | None
    recommended_path: str | None
    attempts: tuple[CommandResult, ...]


@dataclass(frozen=True)
class WslDockerProbe:
    version: CommandResult
    info: CommandResult
    context: CommandResult


@dataclass(frozen=True)
class WslResourceProbe:
    cpu: CommandResult
    meminfo: CommandResult
    root_disk: CommandResult
    work_disk: CommandResult
    work_root: str


def inspect_wsl(runner: ProcessRunner) -> dict[str, Any]:
    status = runner.run(["wsl.exe", "--status"], encoding="utf-16-le")
    listing = runner.run(["wsl.exe", "--list", "--verbose"], encoding="utf-16-le")
    distributions: list[dict[str, Any]] = []
    default_distribution: str | None = None
    if listing.ok:
        for raw_line in listing.stdout.replace("\x00", "").splitlines():
            line = raw_line.strip()
            if not line or "NAME" in line.upper() and "VERSION" in line.upper():
                continue
            default = line.startswith("*")
            line = line.lstrip("* ")
            match = re.match(r"^(?P<name>.+?)\s+(?P<state>Running|Stopped|Installing|Uninstalling)\s+(?P<version>[12])$", line)
            if match:
                item = {**match.groupdict(), "version": int(match.group("version")), "default": default}
                distributions.append(item)
                if default:
                    default_distribution = match.group("name").strip()
    return {
        "available": status.returncode is not None or listing.returncode is not None,
        "status_ok": status.ok,
        "default_distribution": default_distribution,
        "distributions": distributions,
        "raw_status": _detail(status),
        "raw_list": _detail(listing),
    }


def run_in_wsl(
    runner: ProcessRunner,
    argv: list[str],
    timeout: float = 8.0,
    env: dict[str, str] | None = None,
) -> CommandResult:
    command = ["wsl.exe", "--exec"]
    if env:
        for key, value in env.items():
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or any(char in value for char in "\x00\n\r"):
                raise ValueError("Invalid structured WSL environment")
        command.extend(["env", *(f"{key}={value}" for key, value in sorted(env.items()))])
    return runner.run([*command, *argv], timeout=timeout)


def unc_path_to_linux(value: str, *, distribution: str | None = None) -> str:
    """Convert a WSL UNC path to its Linux spelling without invoking a shell."""
    match = re.fullmatch(r"\\\\(?:wsl\.localhost|wsl\$)\\([^\\]+)(?:\\(.*))?", value, re.IGNORECASE)
    if not match:
        raise ValueError(f"WSL planning requires a \\wsl.localhost or \\wsl$ UNC path: {value}")
    detected, tail = match.groups()
    if distribution and detected.casefold() != distribution.casefold():
        raise ValueError(f"WSL path belongs to {detected}, expected {distribution}")
    return "/" + (tail or "").replace("\\", "/")


def linux_path_to_unc(value: str, *, distribution: str) -> str:
    if not value.startswith("/") or any(character in value for character in ("\x00", "\n", "\r")):
        raise ValueError("Linux path must be absolute and free of control characters")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", distribution):
        raise ValueError("Invalid WSL distribution name")
    return rf"\\wsl.localhost\{distribution}\{value.lstrip('/').replace('/', chr(92))}"


def probe_nvidia(runner: ProcessRunner) -> WslNvidiaProbe:
    path_result = run_in_wsl(runner, ["sh", "-lc", "command -v nvidia-smi"])
    query = [
        "--query-gpu=name,uuid,memory.total,memory.free,driver_version",
        "--format=csv,noheader,nounits",
    ]
    plain_result = run_in_wsl(runner, ["nvidia-smi", *query])
    attempts = [path_result, plain_result]
    if plain_result.ok:
        executed = path_result.stdout.strip() if path_result.ok and path_result.stdout.strip() else "nvidia-smi"
        return WslNvidiaProbe(plain_result, executed, path_result.ok, None, None, tuple(attempts))
    fallback_result = run_in_wsl(runner, [WSL_NVIDIA_SMI_FALLBACK, *query])
    attempts.append(fallback_result)
    if fallback_result.ok:
        return WslNvidiaProbe(
            fallback_result,
            WSL_NVIDIA_SMI_FALLBACK,
            False,
            "NVIDIA_SMI_PATH_NOT_EXPORTED",
            "/usr/lib/wsl/lib",
            tuple(attempts),
        )
    return WslNvidiaProbe(fallback_result, None, False, "WSL_GPU_UNAVAILABLE", None, tuple(attempts))


def probe_docker_integration(runner: ProcessRunner) -> WslDockerProbe:
    return WslDockerProbe(
        version=run_in_wsl(runner, ["docker", "version", "--format", "{{json .}}"], timeout=10),
        info=run_in_wsl(runner, ["docker", "info", "--format", "{{json .}}"], timeout=10),
        context=run_in_wsl(runner, ["docker", "context", "show"]),
    )


def probe_nextflow(runner: ProcessRunner, *, version: str) -> tuple[CommandResult, CommandResult]:
    """Resolve a user-local Nextflow launcher, then execute it with pinned NXF_VER."""
    path_result = run_in_wsl(runner, ["sh", "-lc", "command -v nextflow"])
    candidate = path_result.stdout.strip() if path_result.ok else ""
    executable = candidate if candidate.startswith("/") and not any(char in candidate for char in "\x00\n\r") else "nextflow"
    result = run_in_wsl(
        runner,
        [executable, "-version"],
        timeout=30,
        env={"NXF_VER": version},
    )
    return result, path_result


def probe_resources(runner: ProcessRunner, work_root: str) -> WslResourceProbe:
    if not work_root.startswith("/") or any(character in work_root for character in ("\x00", "\n", "\r")):
        raise ValueError("WSL work root must be an absolute Linux path without control characters")
    return WslResourceProbe(
        cpu=run_in_wsl(runner, ["getconf", "_NPROCESSORS_ONLN"]),
        meminfo=run_in_wsl(runner, ["cat", "/proc/meminfo"]),
        root_disk=run_in_wsl(runner, ["df", "-Pk", "--", "/"]),
        work_disk=run_in_wsl(runner, ["df", "-Pk", "--", work_root]),
        work_root=work_root,
    )


def _detail(result: CommandResult) -> dict[str, Any]:
    return {
        "argv": list(result.argv), "returncode": result.returncode, "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(), "timed_out": result.timed_out, "exception": result.exception,
    }
