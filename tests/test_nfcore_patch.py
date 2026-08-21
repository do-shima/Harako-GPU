from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from harako_gpu.adapters.nfcore_patch import (
    PatchContractError,
    git_apply_argv,
    load_patch_manifest,
    verify_patch_state,
)


REPOSITORY = Path(__file__).resolve().parents[1]


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_patch_contract_accepts_only_pinned_source_and_structured_argv(tmp_path: Path) -> None:
    pipeline = tmp_path / "pipeline"
    pipeline.mkdir()
    target = pipeline / "module.nf"
    target.write_bytes(b"source\n")
    patch = tmp_path / "fix.patch"
    patch.write_bytes(b"patch\n")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "resolved_commit": "abc123",
                "patch_sha256": _digest(b"patch\n"),
                "targets": [
                    {
                        "path": "module.nf",
                        "source_sha256": _digest(b"source\n"),
                        "patched_sha256": _digest(b"patched\n"),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = load_patch_manifest(manifest_path)
    assert verify_patch_state(pipeline, manifest, resolved_commit="abc123", patch_path=patch) == "SOURCE"
    argv = git_apply_argv(pipeline, patch, check=True)
    assert argv == ("git", "-C", str(pipeline), "apply", "--check", str(patch))
    assert not any("eval" in part or ";" in part for part in argv)


def test_patch_contract_rejects_unknown_upstream_sha(tmp_path: Path) -> None:
    pipeline = tmp_path / "pipeline"
    pipeline.mkdir()
    (pipeline / "module.nf").write_bytes(b"unknown\n")
    patch = tmp_path / "fix.patch"
    patch.write_bytes(b"patch\n")
    manifest = {
        "resolved_commit": "abc123",
        "patch_sha256": _digest(b"patch\n"),
        "targets": [
            {
                "path": "module.nf",
                "source_sha256": _digest(b"source\n"),
                "patched_sha256": _digest(b"patched\n"),
            }
        ],
    }
    with pytest.raises(PatchContractError, match="Unknown upstream SHA-256"):
        verify_patch_state(pipeline, manifest, resolved_commit="abc123", patch_path=patch)


def test_checked_in_patch_manifest_and_reporting_only_scope() -> None:
    patch_dir = REPOSITORY / "patches" / "nf-core-rnaseq-3.26.0"
    manifest = load_patch_manifest(patch_dir / "manifest.json")
    patch_path = patch_dir / manifest["patch_file"]
    assert _digest(patch_path.read_bytes()) == manifest["patch_sha256"]
    assert manifest["revision"] == "3.26.0"
    assert manifest["resolved_commit"] == "e7ca46272c8f9d5ceee3f71759f4ba551d3217a4"
    assert manifest["behavior"]["alignment_arguments_changed"] is False
    assert manifest["behavior"]["container_changed"] is False
    text = patch_path.read_text(encoding="utf-8")
    assert "--logfile ${prefix}.parabricks.log" in text
    assert "--logfile ${prefix}.Log.final.out" in text
    assert "--low-memory" not in text
    assert "--no-markdups" not in text


def test_prebuilt_star_index_patch_is_exactly_pinned() -> None:
    patch_dir = REPOSITORY / "patches" / "nf-core-rnaseq-3.26.0"
    manifest = load_patch_manifest(patch_dir / "prebuilt-star-index-manifest.json")
    patch_path = patch_dir / "parabricks-prebuilt-star-index.patch"
    assert _digest(patch_path.read_bytes()) == manifest["patch_sha256"]
    assert manifest["resolved_commit"] == "e7ca46272c8f9d5ceee3f71759f4ba551d3217a4"
    assert [item["path"] for item in manifest["targets"]] == ["subworkflows/local/prepare_genome/main.nf"]
    text = patch_path.read_text(encoding="utf-8")
    assert "use_parabricks_star && fasta_provided && !star_index" in text
    assert "curl" not in text and "wget" not in text and "eval" not in text
