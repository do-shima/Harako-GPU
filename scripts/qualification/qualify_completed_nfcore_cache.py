"""Qualify Nextflow ``-resume`` against a completed scientific run.

This harness deliberately does not call the public ``run resume`` command: a
completed product run is immutable and that command must reject it.  Instead,
the frozen Nextflow command is replayed with ``-resume`` and isolated execution
reports while the published scientific artifacts are hashed before and after.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from harako_gpu.adapters.filesystem import atomic_write_json, sha256_path
from harako_gpu.adapters.process import ProcessRunner
from harako_gpu.adapters.resources import parse_trace_counts
from harako_gpu.adapters.wsl import linux_path_to_unc


REPORT_OPTIONS = {"-with-report", "-with-timeline", "-with-trace", "-with-dag"}
SCIENTIFIC_ROLES = {
    "genomic_bam",
    "genomic_bai",
    "star_log_final",
    "star_junction",
    "star_reads_per_gene",
}


def _replace_reports(argv: list[str], output_root: str) -> list[str]:
    suffixes = {
        "-with-report": "report.html",
        "-with-timeline": "timeline.html",
        "-with-trace": "trace.tsv",
        "-with-dag": "dag.html",
    }
    replaced: list[str] = []
    index = 0
    while index < len(argv):
        value = argv[index]
        if value in REPORT_OPTIONS:
            replaced.extend((value, f"{output_root}/{suffixes[value]}"))
            index += 2
        elif value == "-name":
            replaced.extend((value, "harako-completed-resume-qualification-v2"))
            index += 2
        else:
            replaced.append(value)
            index += 1
    replaced.append("-resume")
    return replaced


def _artifact_hashes(run_dir: Path) -> dict[str, str]:
    manifest = json.loads((run_dir / "artifacts/manifest.json").read_text(encoding="utf-8"))
    hashes: dict[str, str] = {}
    for artifact in manifest["artifacts"]:
        if artifact["role"] not in SCIENTIFIC_ROLES:
            continue
        path = run_dir / artifact["relative_path"]
        if path.is_file():
            hashes[artifact["artifact_id"]] = sha256_path(path)
    return hashes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", help="Linux absolute path of a completed run")
    parser.add_argument("--distribution", default="Ubuntu")
    args = parser.parse_args()
    run_linux = args.run_dir.rstrip("/")
    run = Path(linux_path_to_unc(run_linux, distribution=args.distribution))
    status = json.loads((run / "status.json").read_text(encoding="utf-8"))
    if status["state"] not in {"COMPLETED", "COMPLETED_WITH_LIMITATION"}:
        raise SystemExit("The qualification source must be a completed run")
    frozen = json.loads((run / "frozen/command.json").read_text(encoding="utf-8"))
    output_linux = f"{run_linux}/execution/completed-resume-qualification"
    output = run / "execution/completed-resume-qualification"
    if output.exists():
        raise SystemExit(f"Qualification output already exists: {output_linux}")
    output.mkdir(parents=True)
    before = _artifact_hashes(run)
    argv = _replace_reports(list(frozen["argv"]), output_linux)
    command = {
        "schema_version": 1,
        "cwd": frozen["cwd"],
        "env": frozen["env"],
        "argv": argv,
        "pid_file": f"{output_linux}/linux.pid",
        "qualification_only": True,
    }
    atomic_write_json(output / "command.json", command)
    runner = f"{run_linux}/frozen/wsl_exec_runner.py"
    command_linux = f"{output_linux}/command.json"
    prefix = (
        "wsl.exe",
        "--distribution",
        args.distribution,
        "--exec",
        "python3",
        runner,
        command_linux,
    )
    result = ProcessRunner().run(prefix, timeout=900)
    (output / "stdout.log").write_text(result.stdout, encoding="utf-8")
    (output / "stderr.log").write_text(result.stderr, encoding="utf-8")
    trace = output / "trace.tsv"
    counts = parse_trace_counts(trace.read_text(encoding="utf-8")) if trace.is_file() else {}
    after = _artifact_hashes(run)
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_run_id": status["run_id"],
        "public_completed_resume_rejected_by_contract": True,
        "returncode": result.returncode,
        "trace_counts": counts,
        "scientific_artifact_hashes_before": before,
        "scientific_artifact_hashes_after": after,
        "scientific_artifacts_unchanged": before == after and bool(before),
    }
    atomic_write_json(output / "qualification.json", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    if result.returncode != 0 or counts.get("cached", 0) < 1 or before != after:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
