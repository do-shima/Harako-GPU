"""Filesystem reads, hashing, and guarded writes."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import time
from pathlib import Path
from typing import Any

from harako_gpu.core.canonical import sha256_payload


def sha256_path(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_new_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except FileExistsError as exc:
        raise ValueError(f"Refusing to overwrite existing plan artifact: {path}") from exc


def atomic_write_text(path: Path, text: str) -> None:
    """Durably replace a mutable state file through a same-directory temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(6):
            try:
                os.replace(temporary_path, path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def create_exclusive_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ValueError(f"Exclusive state already exists: {path}") from exc


def ensure_within(path: Path, root: Path, *, require_exists: bool = False) -> Path:
    """Resolve symlinks and reject traversal outside a declared runtime root."""
    candidate = path.expanduser().resolve(strict=require_exists)
    boundary = root.expanduser().resolve(strict=require_exists)
    if candidate != boundary and boundary not in candidate.parents:
        raise ValueError(f"Path escapes declared root: {candidate}")
    return candidate


def require_safe_linux_runtime_path(value: str) -> str:
    if not value.startswith("/") or value.startswith(("/mnt/c", "/mnt/d")):
        raise ValueError("Runtime path must be an absolute Linux filesystem path outside /mnt/c and /mnt/d")
    if any(part in {"", ".", ".."} for part in value.split("/")[1:]) or any(char in value for char in "\x00\n\r"):
        raise ValueError("Runtime path contains an unsafe component")
    return value.rstrip("/") or "/"


def make_tree_read_only(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        mode = path.stat().st_mode
        path.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    mode = root.stat().st_mode
    root.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def tree_inventory(root: Path, *, exclude_names: frozenset[str] = frozenset({".git"})) -> tuple[tuple[dict[str, Any], ...], str]:
    boundary = root.resolve(strict=True)
    rows: list[dict[str, Any]] = []
    for path in sorted(boundary.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(boundary)
        if any(part in exclude_names for part in relative.parts):
            continue
        if path.is_symlink():
            target = os.readlink(path)
            resolved = path.resolve(strict=True)
            if boundary != resolved and boundary not in resolved.parents:
                raise ValueError(f"Snapshot symlink escapes root: {relative}")
            rows.append({"path": relative.as_posix(), "kind": "symlink", "target": target})
        elif path.is_file():
            rows.append({"path": relative.as_posix(), "kind": "file", "size": path.stat().st_size,
                         "sha256": sha256_path(path)})
        elif path.is_dir():
            rows.append({"path": relative.as_posix(), "kind": "directory"})
    inventory = tuple(rows)
    return inventory, sha256_payload({"kind": "harako-tree-inventory-v1", "rows": inventory})
