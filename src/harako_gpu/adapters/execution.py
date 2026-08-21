"""Structured native/WSL command specifications; never invokes a shell."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping

from harako_gpu.adapters.filesystem import atomic_write_text
from harako_gpu.adapters.process import CommandResult, ProcessRunner
from harako_gpu.core.canonical import sha256_payload


ENV_ALLOWLIST = frozenset({
    "NXF_VER", "NXF_HOME", "NXF_ANSI_LOG", "NXF_OFFLINE", "NXF_PLUGINS_DIR",
    "PATH", "CUDA_VISIBLE_DEVICES",
})


@dataclass(frozen=True)
class CommandSpec:
    argv: tuple[str, ...]
    cwd: str
    env: Mapping[str, str]
    pid_file: str
    schema_version: int = 1

    def validate(self) -> None:
        if self.schema_version != 1 or not self.argv or any(not part or "\x00" in part for part in self.argv):
            raise ValueError("Structured argv must be a non-empty NUL-free list")
        if self.argv[0] in {"sh", "bash", "cmd", "powershell", "pwsh"}:
            raise ValueError("Shell execution is forbidden")
        if not self.cwd.startswith("/") or not self.pid_file.startswith("/"):
            raise ValueError("WSL/native Linux cwd and PID file must be absolute")
        if set(self.env) - ENV_ALLOWLIST:
            raise ValueError("Command environment contains a non-allowlisted key")
        if any(not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or any(c in value for c in "\x00\n\r")
               for key, value in self.env.items()):
            raise ValueError("Invalid structured environment")

    @property
    def argv_sha256(self) -> str:
        self.validate()
        return sha256_payload({"kind": "harako-command-argv-v1", "argv": self.argv})

    @property
    def env_sha256(self) -> str:
        self.validate()
        return sha256_payload({"kind": "harako-command-env-v1", "env": dict(self.env)})

    def as_dict(self) -> dict[str, object]:
        self.validate()
        return {**asdict(self), "argv_sha256": self.argv_sha256, "env_sha256": self.env_sha256}


def write_command_spec(path: Path, spec: CommandSpec) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(spec.as_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError as exc:
        raise ValueError(f"Command specification already exists: {path}") from exc


def wsl_exec_argv(*, distribution: str, runner_path: str, spec_path: str) -> tuple[str, ...]:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", distribution):
        raise ValueError("Invalid WSL distribution")
    for value in (runner_path, spec_path):
        if not value.startswith("/") or any(char in value for char in "\x00\n\r"):
            raise ValueError("WSL runner/spec paths must be absolute")
    return ("wsl.exe", "--distribution", distribution, "--exec", "python3", runner_path, spec_path)


def run_native_streaming(
    spec: CommandSpec,
    *,
    runner: ProcessRunner,
    stdout_path: Path,
    stderr_path: Path,
    on_started: Callable[[int], None] | None = None,
    on_heartbeat: Callable[[], None] | None = None,
) -> CommandResult:
    """Run one validated native command with only its frozen allowlisted environment."""
    spec.validate()
    cwd = Path(spec.cwd)
    if not cwd.is_dir() or not Path(spec.pid_file).parent.is_dir():
        raise ValueError("Native execution cwd/PID parent must exist")

    def record_started(pid: int) -> None:
        atomic_write_text(Path(spec.pid_file), f"{pid}\n")
        if on_started:
            on_started(pid)

    return runner.run_streaming(
        spec.argv, cwd=cwd, env=dict(spec.env), stdout_path=stdout_path, stderr_path=stderr_path,
        on_started=record_started, on_heartbeat=on_heartbeat, inherit_env=False,
    )
