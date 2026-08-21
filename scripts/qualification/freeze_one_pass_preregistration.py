"""Freeze the tracked one-pass preregistration into the WSL runtime area."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from harako_gpu.adapters.filesystem import sha256_path, write_new_text
from harako_gpu.adapters.wsl import linux_path_to_unc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--distribution", default="Ubuntu")
    args = parser.parse_args()
    root = args.runtime_root.rstrip("/")
    if not root.startswith("/") or root.startswith(("/mnt/c", "/mnt/d")):
        raise SystemExit("runtime root must be an absolute WSL ext4 path")
    destination = Path(linux_path_to_unc(root, distribution=args.distribution))
    destination.mkdir(parents=True, exist_ok=True)
    frozen = destination / "one-pass-workstation-preregistration.json"
    digest_file = destination / "one-pass-workstation-preregistration.sha256"
    if frozen.exists() or digest_file.exists():
        raise SystemExit("one-pass preregistration is already frozen")
    payload = json.loads(args.source.read_text(encoding="utf-8"))
    write_new_text(frozen, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    digest = sha256_path(frozen)
    write_new_text(digest_file, f"{digest}  {frozen.name}\n")
    print(json.dumps({"path": str(frozen), "sha256": digest}, indent=2))


if __name__ == "__main__":
    main()
