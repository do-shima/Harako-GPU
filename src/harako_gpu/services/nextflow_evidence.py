"""Safe, bounded failed-task evidence collection from a pinned Nextflow work root."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from harako_gpu.adapters.filesystem import ensure_within


EVIDENCE_FILES = (".command.sh", ".command.run", ".command.out", ".command.err", ".exitcode")


def collect_failed_task_evidence(*, trace: Path, work_root: Path, destination: Path) -> tuple[dict, ...]:
    root = work_root.resolve(strict=True)
    with trace.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle, delimiter="\t")
                if str(row.get("status", "")).upper() in {"FAILED", "ABORTED"}]
    evidence = []
    for row in rows:
        task_hash = str(row.get("hash", ""))
        if "/" not in task_hash or any(part in {"", ".", ".."} for part in task_hash.split("/")):
            raise ValueError("Failed task hash is invalid")
        prefix, suffix = task_hash.split("/", 1)
        candidates = [path for path in (root / prefix).glob(suffix + "*") if path.is_dir()]
        if len(candidates) != 1:
            raise ValueError("Failed task work directory is missing or ambiguous")
        work = ensure_within(candidates[0], root, require_exists=True)
        target = destination / f"failed-{row.get('task_id', 'unknown')}-{prefix}{suffix}"
        target.mkdir(parents=True)
        files = []
        for name in EVIDENCE_FILES:
            source = ensure_within(work / name, root)
            if source.is_file() and source.stat().st_size <= 1024**2:
                shutil.copy2(source, target / name); files.append(name)
        record = {"process": row.get("name"), "task_id": row.get("task_id"), "hash": task_hash,
                  "status": row.get("status"), "exit": row.get("exit"), "files": files,
                  "work_path_role": f"<WORK_DIR>/{prefix}/{suffix}*"}
        (target / "task.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        evidence.append(record)
    return tuple(evidence)
