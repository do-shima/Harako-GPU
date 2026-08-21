"""Qualify native transport with the fixed non-scientific fail/resume fixture."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
from pathlib import Path

from harako_gpu.adapters.execution import CommandSpec, run_native_streaming, write_command_spec
from harako_gpu.adapters.execution_context import NATIVE_LINUX, parse_execution_context, require_native_linux_host
from harako_gpu.adapters.filesystem import atomic_write_json, require_safe_linux_runtime_path
from harako_gpu.adapters.process import ProcessRunner
from harako_gpu.adapters.resources import ResourceMonitor


NEXTFLOW_VERSION = "25.04.3"
FIXTURE = "fixed-fail-once-v1"


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="New absolute native-Linux evidence directory")
    parser.add_argument("--nextflow", required=True, help="Existing absolute Nextflow 25.04.3 executable")
    return parser


def main() -> None:
    args = _parser().parse_args()
    require_native_linux_host()
    root_value = require_safe_linux_runtime_path(args.root)
    nextflow_value = require_safe_linux_runtime_path(args.nextflow)
    root = Path(root_value)
    nextflow = Path(nextflow_value)
    repository = Path(__file__).resolve().parents[2]
    if repository == root or repository in root.parents or root in repository.parents:
        raise SystemExit("Qualification root must be outside the repository")
    if root.exists():
        raise SystemExit(f"Qualification directory already exists: {root}")
    if not nextflow.is_file():
        raise SystemExit(f"Nextflow executable is missing: {nextflow}")

    root.mkdir(parents=True)
    launch = root / "launch"
    launch.mkdir()
    pipeline = root / "pipeline"
    shutil.copytree(repository / "qualification/lifecycle-nextflow", pipeline)
    work = root / "work"
    nxf_home = root / "nxf-home"
    sentinel = root / "fail-once.sentinel"
    process = ProcessRunner()
    environment = {
        "NXF_VER": NEXTFLOW_VERSION,
        "NXF_HOME": str(nxf_home),
        "NXF_ANSI_LOG": "false",
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    }
    version = process.run((str(nextflow), "-version"), timeout=30, env=environment)
    version_text = version.stdout + version.stderr
    if not version.ok or re.search(r"\b25\.04\.3\b", version_text) is None:
        raise SystemExit("Exact Nextflow 25.04.3 is unavailable")

    attempts: list[dict[str, object]] = []
    trace_rows: list[list[dict[str, str]]] = []
    native = parse_execution_context(NATIVE_LINUX)
    wsl_command_detected = False
    for number, resume in ((1, False), (2, True)):
        attempt = root / f"attempt-{number:04d}"
        attempt.mkdir()
        trace = attempt / "trace.tsv"
        report = attempt / "report.html"
        argv = (
            str(nextflow), "run", str(pipeline), "-work-dir", str(work),
            "--sentinel", str(sentinel), "-with-trace", str(trace),
            "-with-report", str(report),
        ) + (("-resume",) if resume else ())
        spec = CommandSpec(argv, str(launch), environment, str(attempt / "linux.pid"))
        write_command_spec(attempt / "command.json", spec)
        monitor = ResourceMonitor(
            execution=native, work_root=str(work), result_root=str(root),
            log_path=attempt / "resource-monitor.tsv", runner=process,
        )
        monitor.start()
        result = run_native_streaming(
            spec, runner=process, stdout_path=attempt / "stdout.log",
            stderr_path=attempt / "stderr.log", on_heartbeat=lambda: monitor.snapshot,
        )
        monitor.stop()
        nextflow_log = launch / ".nextflow.log"
        if nextflow_log.is_file():
            shutil.copy2(nextflow_log, attempt / "nextflow.log")
        rows = _rows(trace)
        trace_rows.append(rows)
        wsl_command_detected |= any("wsl.exe" in part.casefold() for part in spec.argv)
        attempts.append({
            "attempt": number,
            "returncode": result.returncode,
            "resource_sampled": (attempt / "resource-monitor.tsv").is_file(),
        })

    first_rows, resume_rows = trace_rows
    completed_files = list(work.rglob("completed.txt")) if work.is_dir() else []
    completed_token = (completed_files[0].read_text(encoding="utf-8").strip()
                       if len(completed_files) == 1 else None)
    first_exit_42 = any(row.get("status", "").upper() == "FAILED" and row.get("exit") == "42"
                        for row in first_rows)
    prepare_cached = any("PREPARE_TOKEN" in row.get("name", "") and
                         row.get("status", "").upper().startswith("CACHED") for row in resume_rows)
    fail_once_completed = any("FAIL_ONCE" in row.get("name", "") and
                              row.get("status", "").upper() == "COMPLETED" for row in resume_rows)
    payload = {
        "schema_version": 1,
        "fixture": FIXTURE,
        "execution_context": NATIVE_LINUX,
        "nextflow_version": NEXTFLOW_VERSION,
        "first_exit_code": attempts[0]["returncode"],
        "first_failed": attempts[0]["returncode"] not in (0, None),
        "first_process_exit_42": first_exit_42,
        "resume_exit_code": attempts[1]["returncode"],
        "resume_succeeded": attempts[1]["returncode"] == 0,
        "prepare_token_cached": prepare_cached,
        "fail_once_completed": fail_once_completed,
        "completed_token": completed_token,
        "attempt_history_preserved": all(
            (root / f"attempt-{number:04d}/trace.tsv").is_file() for number in (1, 2)
        ),
        "resource_sampled": all(bool(item["resource_sampled"]) for item in attempts),
        "wsl_command_detected": wsl_command_detected,
        "attempts": attempts,
    }
    atomic_write_json(root / "qualification.json", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    passed = all((
        payload["first_failed"], payload["first_process_exit_42"],
        payload["resume_succeeded"], payload["prepare_token_cached"],
        payload["fail_once_completed"], payload["completed_token"] == "fixed-lifecycle-token",
        payload["attempt_history_preserved"], payload["resource_sampled"],
        not payload["wsl_command_detected"],
    ))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
