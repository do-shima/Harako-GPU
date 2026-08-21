"""Fail-closed application of the pinned nf-core compatibility patch."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harako_gpu.adapters.process import ProcessRunner


class PatchContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class PatchApplication:
    status: str
    check_argv: tuple[str, ...] | None
    apply_argv: tuple[str, ...] | None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_patch_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise PatchContractError("Unsupported patch manifest schema")
    return payload


def git_apply_argv(pipeline_root: Path, patch_path: Path, *, check: bool) -> tuple[str, ...]:
    argv = ["git", "-C", str(pipeline_root), "apply"]
    if check:
        argv.append("--check")
    argv.append(str(patch_path))
    return tuple(argv)


def verify_patch_state(
    pipeline_root: Path,
    manifest: dict[str, Any],
    *,
    resolved_commit: str,
    patch_path: Path,
) -> str:
    if resolved_commit != manifest.get("resolved_commit"):
        raise PatchContractError("Resolved pipeline commit does not match the patch contract")
    if sha256_file(patch_path) != manifest.get("patch_sha256"):
        raise PatchContractError("Patch SHA-256 does not match the patch contract")
    observed = []
    for target in manifest.get("targets", []):
        target_path = pipeline_root / target["path"]
        if not target_path.is_file():
            raise PatchContractError(f"Patch target is missing: {target['path']}")
        digest = sha256_file(target_path)
        if digest == target["source_sha256"]:
            observed.append("SOURCE")
        elif digest == target["patched_sha256"]:
            observed.append("PATCHED")
        else:
            raise PatchContractError(f"Unknown upstream SHA-256 for {target['path']}: {digest}")
    if not observed:
        raise PatchContractError("Patch manifest has no targets")
    if len(set(observed)) != 1:
        raise PatchContractError("Patch targets are in a mixed source/patched state")
    return observed[0]


def apply_verified_patch(
    pipeline_root: Path,
    manifest_path: Path,
    patch_path: Path,
    *,
    resolved_commit: str,
    runner: ProcessRunner,
) -> PatchApplication:
    manifest = load_patch_manifest(manifest_path)
    state = verify_patch_state(
        pipeline_root,
        manifest,
        resolved_commit=resolved_commit,
        patch_path=patch_path,
    )
    if state == "PATCHED":
        return PatchApplication("ALREADY_APPLIED", None, None)
    check_argv = git_apply_argv(pipeline_root, patch_path, check=True)
    check_result = runner.run(check_argv, timeout=30)
    if not check_result.ok:
        raise PatchContractError(f"git apply --check failed: {check_result.stderr.strip()}")
    apply_argv = git_apply_argv(pipeline_root, patch_path, check=False)
    apply_result = runner.run(apply_argv, timeout=30)
    if not apply_result.ok:
        raise PatchContractError(f"git apply failed: {apply_result.stderr.strip()}")
    if verify_patch_state(
        pipeline_root,
        manifest,
        resolved_commit=resolved_commit,
        patch_path=patch_path,
    ) != "PATCHED":
        raise PatchContractError("Patch postcondition was not reached")
    return PatchApplication("APPLIED", check_argv, apply_argv)
