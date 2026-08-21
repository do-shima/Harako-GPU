"""Sanitized, role-redacted support ZIP generation without biological data."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path

from harako_gpu.adapters.filesystem import ensure_within


ALLOWED_ROOT_FILES = {"run.json", "status.json"}
ALLOWED_FROZEN = {
    "plan.json", "approval-contract.json", "backend-profile.json", "quantification-profiles.json",
    "analysis-series.json", "params.json", "nextflow.config", "command-preview.txt", "command.json",
    "environment.json", "hardware-report.json", "pipeline-manifest.json", "patch-manifest.json",
    "runtime-requirements.json",
    "workflow-backend.json",
    "versions.tsv", "paths.tsv",
    "manifest.json",
}
ALLOWED_ATTEMPT = {
    "attempt.json", "command.json", "controller.log", "stdout.log", "stderr.log", "nextflow.log",
    "trace.tsv", "exit.json", "resource-monitor.tsv",
}
ALLOWED_TASK = {"task.json", "command.json", "stdout.log", "stderr.log", "exit.json"}
ALLOWED_ARTIFACT = {"manifest.json", "verification.json"}
SECRET_RE = re.compile(
    r"(?i)[\"']?\b(token|password|secret|authorization|docker_auth)\b[\"']?\s*[:=]\s*[\"']?[^\s,\"}]+[\"']?"
)


def _candidate_files(run_dir: Path) -> tuple[Path, ...]:
    files: list[Path] = []
    files.extend(run_dir / name for name in ALLOWED_ROOT_FILES)
    files.extend(run_dir / "frozen" / name for name in ALLOWED_FROZEN)
    for attempt in sorted((run_dir / "execution/attempts").glob("[0-9][0-9][0-9][0-9]")):
        files.extend(attempt / name for name in ALLOWED_ATTEMPT)
    for task in sorted((run_dir / "tasks").glob("*/")):
        files.extend(task / name for name in ALLOWED_TASK)
    files.extend(run_dir / "artifacts" / name for name in ALLOWED_ARTIFACT)
    return tuple(path for path in files if path.is_file() and path.stat().st_size <= 10 * 1024**2)


def _replacements(run_dir: Path) -> tuple[tuple[str, str], ...]:
    replacements = [(str(run_dir), "<RUN_DIR>")]
    paths_file = run_dir / "frozen/paths.tsv"
    if paths_file.is_file():
        for line in paths_file.read_text(encoding="utf-8").splitlines()[1:]:
            fields = line.split("\t")
            if len(fields) == 2:
                replacements.append((fields[1], f"<{fields[0]}>"))
    try:
        plan = json.loads((run_dir / "frozen/plan.json").read_text(encoding="utf-8"))
        reference = dict(plan.get("reference") or {})
        for key in ("fasta_path", "gtf_path", "transcript_fasta_path"):
            if reference.get(key):
                replacements.append((str(reference[key]), "<REFERENCE>"))
        for index, sample in enumerate(plan.get("samples", []), 1):
            for role in ("fastq_1", "fastq_2"):
                if sample.get(role):
                    replacements.append((str(sample[role]), f"<INPUT_{index}_{role.upper()}>") )
    except (OSError, json.JSONDecodeError):
        pass
    for value, _ in list(replacements):
        match = re.match(r"^(/home/[^/]+)", value)
        if match:
            replacements.append((match.group(1), "<HOME>"))
    return tuple(sorted(set(replacements), key=lambda item: -len(item[0])))


def _sanitized(path: Path, replacements: tuple[tuple[str, str], ...]) -> bytes:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ValueError(f"Cannot read support file: {path}") from exc
    for source, role in replacements:
        text = text.replace(source, role).replace(source.replace("/", "\\"), role)
    text = SECRET_RE.sub(lambda match: f"{match.group(1)}=<REDACTED>", text)
    return text.encode("utf-8")


def create_support_bundle(run_dir: Path, *, output: Path | None = None) -> Path:
    root = run_dir.resolve(strict=True)
    support_root = root / "support"
    support_root.mkdir(exist_ok=True)
    destination = (output or support_root / f"{root.name}-support.zip").resolve()
    ensure_within(destination, support_root)
    if destination.exists():
        raise ValueError("Support bundle output already exists")
    replacements = _replacements(root)
    entries = []
    payloads = []
    for path in _candidate_files(root):
        relative = path.relative_to(root).as_posix()
        if any(part.lower() in {"auth", "credentials", "secrets"} for part in path.parts):
            continue
        data = _sanitized(path, replacements)
        payloads.append((relative, data))
        entries.append({"role_path": relative, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    manifest = {"schema_version": 1, "redaction": "role_paths_no_mapping", "entries": entries,
                "excluded": ["FASTQ", "FASTA", "GTF", "index", "BAM/BAI", "quant.sf", "large matrices", "credentials"]}
    descriptor, temporary = tempfile.mkstemp(prefix=".support-", suffix=".zip", dir=support_root)
    os.close(descriptor)
    temp = Path(temporary)
    try:
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for relative, data in payloads:
                archive.writestr(relative, data)
            archive.writestr("bundle-manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        os.replace(temp, destination)
    finally:
        if temp.exists():
            temp.unlink()
    return destination
