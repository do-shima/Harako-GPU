"""Freeze the committed capacity preregistration into a WSL runtime root."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from harako_gpu.adapters.filesystem import sha256_path, write_new_text
from harako_gpu.adapters.wsl import linux_path_to_unc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--distribution", default="Ubuntu")
    args = parser.parse_args()
    source = Path("docs/qualification/medium-human-capacity-preregistration.json")
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["frozen_at"] = datetime.now(UTC).isoformat()
    payload["source_document_sha256"] = sha256_path(source)
    destination = Path(linux_path_to_unc(
        f"{args.runtime_root.rstrip('/')}/capacity/capacity-preregistration.json",
        distribution=args.distribution,
    ))
    write_new_text(destination, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    digest = sha256_path(destination)
    write_new_text(destination.with_suffix(".sha256"), f"{digest}  {destination.name}\n")
    print(json.dumps({"path": str(destination), "sha256": digest}, indent=2))


if __name__ == "__main__":
    main()
