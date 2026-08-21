"""Backend-neutral, explicit alignment output manifest contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from harako_gpu.adapters.filesystem import atomic_write_json, sha256_path
from harako_gpu.services.workflow_backends import CANONICAL_OUTPUT_CONTRACT


ALIGNMENT_FILENAMES = {
    "bam": "{sample}.sorted.bam",
    "bai": "{sample}.sorted.bam.bai",
    "star_log": "{sample}.Log.final.out",
    "junctions": "{sample}.SJ.out.tab",
    "star_gene_counts": "{sample}.ReadsPerGene.out.tab",
    "transcriptome_bam": "{sample}.Aligned.toTranscriptome.out.bam",
}

SUPPORT_FILENAMES = {
    "processed_fastq_r1": "preprocessing/fastp/{sample}_R1.fastp.fastq.gz",
    "processed_fastq_r2": "preprocessing/fastp/{sample}_R2.fastp.fastq.gz",
    "fastp_json": "preprocessing/fastp/{sample}.fastp.json",
    "fastp_html": "preprocessing/fastp/{sample}.fastp.html",
    "featurecounts_biotype": "qc/featurecounts/{sample}.featureCounts.txt",
}

NATIVE_COMMAND_FILENAMES = {
    "fastp_command": "preprocessing/fastp/{sample}.command.json",
}

GLOBAL_FILENAMES = {
    "multiqc_report": "reports/multiqc/multiqc_report.html",
}


def alignment_artifacts(run_dir: Path, sample: str) -> dict[str, Path]:
    root = run_dir / "results/alignment" / sample
    result = {
        role: root / template.format(sample=sample)
        for role, template in ALIGNMENT_FILENAMES.items()
    }
    missing = [role for role, path in result.items() if not path.is_file()]
    if missing:
        raise ValueError("Canonical alignment outputs are missing: " + ", ".join(missing))
    return result


def update_backend_output_manifest(
    run_dir: Path,
    *,
    workflow_backend: str,
    sample: str,
    artifacts: Mapping[str, Path],
) -> Path:
    manifest_path = run_dir / "results/backend-output-manifest.json"
    existing: dict[str, Any] = {
        "schema_version": 1,
        "contract_id": CANONICAL_OUTPUT_CONTRACT,
        "workflow_backend": workflow_backend,
        "artifacts": [],
    }
    if manifest_path.is_file():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Backend output manifest is malformed") from exc
        if (existing.get("contract_id"), existing.get("workflow_backend")) != (
            CANONICAL_OUTPUT_CONTRACT,
            workflow_backend,
        ):
            raise ValueError("Backend output manifest identity mismatch")
    retained = [
        item for item in existing.get("artifacts", [])
        if item.get("sample") not in {sample, None}
    ]
    generated: list[dict[str, Any]] = []
    for role in ALIGNMENT_FILENAMES:
        path = artifacts[role].resolve()
        try:
            relative = path.relative_to((run_dir / "results").resolve()).as_posix()
        except ValueError as exc:
            raise ValueError("Backend output escapes the run results directory") from exc
        generated.append({
            "role": role,
            "sample": sample,
            "relative_path": relative,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_path(path),
        })
    for role, template in SUPPORT_FILENAMES.items():
        path = (run_dir / "results" / template.format(sample=sample)).resolve()
        if not path.is_file():
            raise ValueError(f"Canonical backend output is missing: {role}")
        generated.append({
            "role": role,
            "sample": sample,
            "relative_path": path.relative_to((run_dir / "results").resolve()).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_path(path),
        })
    if workflow_backend == "harako_native_v1":
        for role, template in NATIVE_COMMAND_FILENAMES.items():
            path = (run_dir / "results" / template.format(sample=sample)).resolve()
            if not path.is_file():
                raise ValueError(f"Canonical native output is missing: {role}")
            generated.append({
                "role": role,
                "sample": sample,
                "relative_path": path.relative_to((run_dir / "results").resolve()).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_path(path),
            })
    for role, relative in GLOBAL_FILENAMES.items():
        path = (run_dir / "results" / relative).resolve()
        if not path.is_file():
            raise ValueError(f"Canonical backend output is missing: {role}")
        generated.append({
            "role": role,
            "sample": None,
            "relative_path": relative,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_path(path),
        })
    existing["artifacts"] = sorted(
        [*retained, *generated], key=lambda item: (str(item["sample"]), item["role"]),
    )
    atomic_write_json(manifest_path, existing)
    return manifest_path


def validate_backend_output_manifest(run_dir: Path, expected_backend: str) -> dict[str, Any]:
    path = run_dir / "results/backend-output-manifest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read backend output manifest: {exc}") from exc
    if (payload.get("schema_version"), payload.get("contract_id"), payload.get("workflow_backend")) != (
        1,
        CANONICAL_OUTPUT_CONTRACT,
        expected_backend,
    ):
        raise ValueError("Backend output manifest contract mismatch")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("Backend output manifest artifacts are invalid")
    seen: set[tuple[str, str | None]] = set()
    for item in artifacts:
        if not isinstance(item, dict):
            raise ValueError("Backend output manifest artifact is invalid")
        key = (str(item.get("role")), item.get("sample"))
        if key in seen:
            raise ValueError("Backend output manifest contains a duplicate role/sample")
        seen.add(key)
        relative = Path(str(item.get("relative_path")))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe backend output manifest path")
        artifact = (run_dir / "results" / relative).resolve()
        try:
            artifact.relative_to((run_dir / "results").resolve())
        except ValueError as exc:
            raise ValueError("Backend output manifest path escapes results") from exc
        if (not artifact.is_file() or artifact.stat().st_size != item.get("size_bytes")
                or sha256_path(artifact) != item.get("sha256")):
            raise ValueError("Backend output manifest artifact identity mismatch")
    return payload


def artifact_for_role(
    run_dir: Path, *, expected_backend: str, role: str, sample: str | None,
) -> Path:
    payload = validate_backend_output_manifest(run_dir, expected_backend)
    matches = [
        item for item in payload["artifacts"]
        if item["role"] == role and item.get("sample") == sample
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one canonical backend output: {sample}/{role}")
    return run_dir / "results" / str(matches[0]["relative_path"])
