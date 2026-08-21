"""The only process adapter used by the local Streamlit presentation layer."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LaunchedController:
    pid: int
    argv: tuple[str, ...]
    stdout_path: str
    stderr_path: str


def streamlit_argv(*, app_path: Path, host: str, port: int, no_browser: bool,
                   output_root: str | None = None,
                   python_executable: str | None = None) -> tuple[str, ...]:
    if host not in {"127.0.0.1", "localhost", "0.0.0.0"}:
        raise ValueError("GUI host must be loopback or the explicit unqualified 0.0.0.0 override")
    if not 1024 <= port <= 65535:
        raise ValueError("GUI port must be between 1024 and 65535")
    app = app_path.resolve(strict=True)
    argv = (
        python_executable or sys.executable, "-m", "streamlit", "run",
        "--server.address", host, "--server.port", str(port),
        "--server.headless", "true" if no_browser else "false",
        "--browser.gatherUsageStats", "false",
        "--client.showSidebarNavigation", "false", str(app),
    )
    if output_root:
        if any(character in output_root for character in "\x00\r\n"):
            raise ValueError("Output root must not contain control characters")
        argv += ("--", "--output-root", output_root)
    return argv


def run_streamlit(argv: tuple[str, ...]) -> int:
    """Run the local UI attached to the invoking CLI; never use a shell."""
    return subprocess.run(argv, shell=False, check=False).returncode


def controller_argv(*, action: str, run_dir: str, approval_hash: str,
                    distribution: str = "Ubuntu", execution_context: str = "wsl2",
                    python_executable: str | None = None) -> tuple[str, ...]:
    if action not in {"start", "resume"}:
        raise ValueError("GUI controller action must be start or resume")
    if not run_dir or any(character in run_dir for character in "\x00\r\n"):
        raise ValueError("Run directory is required and must not contain control characters")
    if len(approval_hash) != 64 or any(character not in "0123456789abcdef" for character in approval_hash.lower()):
        raise ValueError("Exact 64-character approval hash is required")
    if execution_context not in {"wsl2", "native-linux"}:
        raise ValueError("GUI controller execution context must be wsl2 or native-linux")
    argv = (
        python_executable or sys.executable, "-m", "harako_gpu", "run", action,
        "--run-dir", run_dir, "--approval-hash", approval_hash,
    )
    if execution_context == "native-linux":
        argv += ("--execution-context", "native-linux")
    else:
        argv += ("--distribution", distribution)
    return argv


def launch_controller(*, argv: tuple[str, ...], run_dir_host: Path) -> LaunchedController:
    root = run_dir_host.resolve(strict=True)
    execution = root / "execution"
    stdout_path = execution / "gui-controller.stdout.log"
    stderr_path = execution / "gui-controller.stderr.log"
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    stdout = stdout_path.open("a", encoding="utf-8", errors="replace")
    stderr = stderr_path.open("a", encoding="utf-8", errors="replace")
    try:
        process = subprocess.Popen(
            argv, cwd=root, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            shell=False, close_fds=True, creationflags=creationflags,
        )
    finally:
        stdout.close()
        stderr.close()
    return LaunchedController(process.pid, argv, str(stdout_path), str(stderr_path))
