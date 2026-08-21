"""Fixed WSL-side JSON argv runner copied into each prepared runtime."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


ALLOWLIST = {"NXF_VER", "NXF_HOME", "NXF_ANSI_LOG", "PATH", "CUDA_VISIBLE_DEVICES"}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: wsl_exec_runner.py COMMAND_SPEC.json")
    spec_path = Path(sys.argv[1]).resolve(strict=True)
    data = json.loads(spec_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise SystemExit("unsupported command specification")
    argv = data.get("argv")
    cwd = data.get("cwd")
    env = data.get("env")
    pid_file = data.get("pid_file")
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x and "\x00" not in x for x in argv):
        raise SystemExit("invalid structured argv")
    if argv[0] in {"sh", "bash", "cmd", "powershell", "pwsh"}:
        raise SystemExit("shell execution forbidden")
    if not isinstance(cwd, str) or not cwd.startswith("/") or not Path(cwd).is_dir():
        raise SystemExit("invalid command cwd")
    if not isinstance(pid_file, str) or not pid_file.startswith("/"):
        raise SystemExit("invalid PID file")
    if not isinstance(env, dict) or set(env) - ALLOWLIST:
        raise SystemExit("non-allowlisted environment")
    if any(not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or not isinstance(value, str) or any(c in value for c in "\x00\n\r")
           for key, value in env.items()):
        raise SystemExit("invalid environment")
    destination = Path(pid_file)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    temporary.write_text(str(os.getpid()) + "\n", encoding="ascii")
    os.replace(temporary, destination)
    os.chdir(cwd)
    os.execvpe(argv[0], argv, {**os.environ, **env})


if __name__ == "__main__":
    main()
