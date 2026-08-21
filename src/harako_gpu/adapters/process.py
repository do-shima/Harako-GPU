"""Only adapter permitted to start child processes."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    exception: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.exception


class ProcessRunner:
    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float = 8.0,
        encoding: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        command = tuple(str(part) for part in argv)
        merged_env = None if env is None else {**os.environ, **dict(env)}
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding=encoding,
                errors="replace",
                timeout=timeout,
                check=False,
                shell=False,
                env=merged_env,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                command,
                None,
                _text(exc.stdout),
                _text(exc.stderr),
                timed_out=True,
                exception=f"Timed out after {timeout:g} seconds",
            )
        except OSError as exc:
            return CommandResult(command, None, "", "", exception=f"{type(exc).__name__}: {exc}")
        return CommandResult(command, completed.returncode, completed.stdout, completed.stderr)

    def run_streaming(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None,
        stdout_path: Path,
        stderr_path: Path,
        on_started: Callable[[int], None] | None = None,
        on_heartbeat: Callable[[], None] | None = None,
        heartbeat_seconds: float = 1.0,
        inherit_env: bool = True,
    ) -> CommandResult:
        """Run one attached foreground child while logs and PID remain observable."""
        command = tuple(str(part) for part in argv)
        merged_env = ({**os.environ, **dict(env or {})} if inherit_env else dict(env or {}))
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        try:
            with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout, \
                    stderr_path.open("w", encoding="utf-8", errors="replace") as stderr:
                process = subprocess.Popen(
                    command, cwd=cwd, env=merged_env, stdout=stdout, stderr=stderr,
                    stdin=subprocess.DEVNULL, text=True, shell=False, creationflags=creationflags,
                )
                if on_started:
                    on_started(process.pid)
                while process.poll() is None:
                    if on_heartbeat:
                        try:
                            on_heartbeat()
                        except OSError:
                            # Status/resource telemetry is best-effort and must not abort
                            # a scientific child process on a transient filesystem error.
                            pass
                    time.sleep(max(0.05, heartbeat_seconds))
                return CommandResult(command, process.returncode, "", "")
        except KeyboardInterrupt:
            try:
                process.terminate()  # type: ignore[possibly-undefined]
                process.wait(timeout=10)  # type: ignore[possibly-undefined]
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()  # type: ignore[possibly-undefined]
                except OSError:
                    pass
            return CommandResult(command, None, "", "", exception="INTERRUPTED")
        except OSError as exc:
            return CommandResult(command, None, "", "", exception=f"{type(exc).__name__}: {exc}")


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value
