"""Foreground fixed-stage execution and immutable resume orchestration."""

from __future__ import annotations

import csv
import gzip
import json
import os
import shutil
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Mapping

from harako_gpu.adapters.bio_validation import (
    LEGACY_WSL_UTILITY_SAMTOOLS_IMAGE_ID,
    validate_bam,
)
from harako_gpu.adapters.docker import DockerImageContract
from harako_gpu.adapters.execution import CommandSpec, run_native_streaming, wsl_exec_argv, write_command_spec
from harako_gpu.adapters.execution_context import ExecutionContext, require_context_match
from harako_gpu.adapters.filesystem import atomic_write_json, sha256_path, tree_inventory, write_new_text
from harako_gpu.adapters.process import ProcessRunner
from harako_gpu.adapters.resources import ResourceMonitor, parse_trace_counts
from harako_gpu.adapters.versioned_salmon import VersionedSalmonRequest, execution_metadata
from harako_gpu.core.run_lifecycle import (
    AttemptState, FailureClassification, FailureRecord, RunState, RunStatus, StageId,
    TaskRecord, TaskState,
)
from harako_gpu.services.artifacts import verify_artifacts
from harako_gpu.services.concordance import (
    ORTHOGONAL_GENE_CONCORDANCE_ARTIFACT, compare_abundance,
    compare_orthogonal_gene_counts, compare_profile_runtimes, parse_gtf_annotations, parse_quant_sf,
    render_summary_html, result_dict, stratified_concordance,
    stratified_orthogonal_concordance,
)
from harako_gpu.services.matrices import build_profile_matrices
from harako_gpu.services.nextflow_evidence import collect_failed_task_evidence
from harako_gpu.services.quantification_profiles import ProcessedFastqPair, ProfileIndex, get_profile
from harako_gpu.services.run_state import RunStateStore, utc_now
from harako_gpu.services.star_gene_counts import (
    column_manifest, metadata_counts_tsv, parse_reads_per_gene, selected_counts_tsv,
    validate_gene_universe,
)
from harako_gpu.services.run_preparation import (
    FASTP_IMAGE_IDENTITY,
    IMAGE_CONTRACTS,
)
from harako_gpu.services.host_profiles import runtime_quantification_image_contract
from harako_gpu.services.runtime_validation_images import resolve_frozen_bam_validator_contract
from harako_gpu.services.backend_outputs import (
    ALIGNMENT_FILENAMES,
    alignment_artifacts,
    artifact_for_role,
    update_backend_output_manifest,
    validate_backend_output_manifest,
)
from harako_gpu.services.workflow_backends import HARAKO_NATIVE_V1, workflow_backend_for_plan


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _log(attempt: Path, message: str) -> None:
    with (attempt / "controller.log").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{utc_now()}\t{message}\n")


def _identity(run_dir: Path) -> Mapping[str, Any]:
    return dict(_load(run_dir / "run.json")["identity"])


def _transport_argv(execution: ExecutionContext, argv: tuple[str, ...]) -> tuple[str, ...]:
    if execution.is_native_linux:
        return argv
    return ("wsl.exe", "--distribution", str(execution.distribution), "--exec", *argv)


def _salmon_timing(*, started_at: str, ended_at: str, wall_seconds: float,
                   paired_fragments: int, execution_order: int) -> dict[str, Any]:
    if wall_seconds <= 0 or paired_fragments < 1 or execution_order not in {1, 2}:
        raise ValueError("Salmon timing requires positive runtime/fragments and fixed execution order")
    return {
        "started_at": started_at, "ended_at": ended_at, "wall_seconds": wall_seconds,
        "paired_fragments": paired_fragments,
        "fragments_per_second": paired_fragments / wall_seconds,
        "execution_order": execution_order,
    }


def _user_ids(execution: ExecutionContext, runner: ProcessRunner) -> tuple[str, str]:
    if execution.is_native_linux:
        return str(os.getuid()), str(os.getgid())
    values = [runner.run(("wsl.exe", "--distribution", str(execution.distribution),
                          "--exec", "/usr/bin/id", option), timeout=5)
              for option in ("-u", "-g")]
    if any(not item.ok or not item.stdout.strip().isdigit() for item in values):
        raise ValueError("Cannot resolve WSL user identity")
    return values[0].stdout.strip(), values[1].stdout.strip()


def verify_frozen(run_dir: Path) -> None:
    manifest = _load(run_dir / "frozen/manifest.json")
    entries = manifest.get("inventory") or []
    observed = []
    for entry in entries:
        relative = str(entry["path"])
        path = run_dir / "frozen" / relative
        if not path.is_file() or sha256_path(path) != entry["sha256"] or path.stat().st_size != entry["size"]:
            raise ValueError(f"Frozen contract changed: {relative}")
        observed.append(entry)
    from harako_gpu.core.canonical import sha256_payload
    if sha256_payload({"kind": "harako-tree-inventory-v1", "rows": tuple(observed)}) != manifest["inventory_sha256"]:
        raise ValueError("Frozen inventory identity mismatch")


def _attempt_dir(run_dir: Path) -> tuple[str, Path]:
    attempts = run_dir / "execution/attempts"
    count = len([item for item in attempts.iterdir() if item.is_dir()]) + 1
    attempt_id = f"{count:04d}"
    destination = attempts / attempt_id
    destination.mkdir()
    atomic_write_json(destination / "attempt.json", {
        "schema_version": 1, "attempt_id": attempt_id, "state": AttemptState.CREATED,
        "created_at": utc_now(),
    })
    return attempt_id, destination


def _set_attempt(path: Path, state: AttemptState, **extra: Any) -> None:
    payload = _load(path / "attempt.json")
    payload.update({"state": state, "updated_at": utc_now(), **extra})
    atomic_write_json(path / "attempt.json", payload)


def _task_counts(tasks: tuple[TaskRecord, ...]) -> dict[str, int]:
    counts = {item.value: 0 for item in TaskState}
    for task in tasks:
        counts[task.state.value] += 1
    return counts


def _update_status(store: RunStateStore, *, stage: str | None, task: str | None,
                   attempt_id: str, resources: Mapping[str, Any] | None = None,
                   processes: Mapping[str, int] | None = None) -> None:
    current = store.status()
    store.write_status(replace(
        current, current_stage=stage, current_task=task, attempt_id=attempt_id,
        updated_at=utc_now(), task_counts=_task_counts(store.read_tasks()),
        process_counts=dict(processes or current.process_counts),
        resource_snapshot=dict(resources or current.resource_snapshot),
    ))


def _begin_task(store: RunStateStore, task_id: str, attempt_id: str,
                stdout: Path, stderr: Path) -> TaskRecord:
    task = next(item for item in store.read_tasks() if item.task_id == task_id)
    if task.state in {TaskState.SUCCEEDED, TaskState.CACHED} and task.output_validation == "VALIDATED":
        cached = replace(task, state=TaskState.CACHED, attempt=attempt_id, cached=True)
        store.replace_task(cached)
        return cached
    running = replace(task, state=TaskState.RUNNING, attempt=attempt_id, started_at=utc_now(), ended_at=None,
                      stdout_path=stdout.relative_to(store.run_dir).as_posix(),
                      stderr_path=stderr.relative_to(store.run_dir).as_posix(), cached=False)
    store.replace_task(running)
    _update_status(store, stage=running.stage_id, task=task_id, attempt_id=attempt_id)
    return running


def _finish_task(store: RunStateStore, task: TaskRecord, *, exit_code: int = 0,
                 validation: str = "VALIDATED", expected: tuple[str, ...] = ()) -> None:
    store.replace_task(replace(task, state=TaskState.SUCCEEDED, ended_at=utc_now(), exit_code=exit_code,
                               output_validation=validation, expected_outputs=expected))


def _fail(store: RunStateStore, attempt: Path, task: TaskRecord | None, classification: FailureClassification,
          message: str, detail: str, *, interrupted: bool = False) -> None:
    if task:
        store.replace_task(replace(task, state=TaskState.INTERRUPTED if interrupted else TaskState.FAILED,
                                   ended_at=utc_now(), output_validation="INVALID",
                                   failure_classification=classification.value))
    failure = FailureRecord(
        classification, task.stage_id if task else StageId.PREFLIGHT.value,
        task.task_id if task else None, None, None, message, message, detail,
        tuple(value for value in ((task.stdout_path if task else None), (task.stderr_path if task else None)) if value),
        True, "Inspect status and logs, then resume the same immutable run after correcting the prerequisite.",
    )
    _set_attempt(attempt, AttemptState.INTERRUPTED if interrupted else AttemptState.FAILED,
                 ended_at=utc_now(), failure=asdict(failure))
    target = RunState.INTERRUPTED if interrupted else RunState.FAILED
    store.transition(target, ended_at=utc_now(), resumable=True, failure=asdict(failure),
                     task_counts=_task_counts(store.read_tasks()),
                     next_actions=("run status", "support-bundle create", "run resume"))


def _copy_alignment_artifacts(run_dir: Path, sample: str) -> dict[str, Path]:
    plan = _load(run_dir / "frozen/plan.json")
    workflow = workflow_backend_for_plan(plan)
    if workflow.workflow_backend == HARAKO_NATIVE_V1:
        result = alignment_artifacts(run_dir, sample)
        update_backend_output_manifest(
            run_dir, workflow_backend=workflow.workflow_backend, sample=sample, artifacts=result,
        )
        validate_backend_output_manifest(run_dir, workflow.workflow_backend)
        return result
    source = run_dir / "results/nfcore/star_salmon"
    destination = run_dir / "results/alignment" / sample
    destination.mkdir(parents=True, exist_ok=True)
    source_paths = {
        "bam": f"{sample}.sorted.bam",
        "bai": f"{sample}.sorted.bam.bai",
        "star_log": f"log/{sample}.Log.final.out",
        "junctions": f"log/{sample}.SJ.out.tab",
        "star_gene_counts": f"log/{sample}.ReadsPerGene.out.tab",
        "transcriptome_bam": f"{sample}.Aligned.toTranscriptome.out.bam",
    }
    result = {}
    for role, source_relative in source_paths.items():
        candidate = source / source_relative
        if not candidate.is_file():
            raise ValueError(f"Expected exactly one alignment artifact: {source_relative}")
        target = destination / ALIGNMENT_FILENAMES[role].format(sample=sample)
        if not target.exists():
            shutil.copy2(candidate, target)
        result[role] = target
    _normalize_reference_outputs(run_dir, sample)
    update_backend_output_manifest(
        run_dir, workflow_backend=workflow.workflow_backend, sample=sample, artifacts=result,
    )
    validate_backend_output_manifest(run_dir, workflow.workflow_backend)
    return result


def _normalize_reference_outputs(run_dir: Path, sample: str) -> None:
    mappings = {
        f"results/nfcore/fastp/{sample}_R1.fastp.fastq.gz":
            f"results/preprocessing/fastp/{sample}_R1.fastp.fastq.gz",
        f"results/nfcore/fastp/{sample}_R2.fastp.fastq.gz":
            f"results/preprocessing/fastp/{sample}_R2.fastp.fastq.gz",
        f"results/nfcore/fastp/{sample}.fastp.json":
            f"results/preprocessing/fastp/{sample}.fastp.json",
        f"results/nfcore/fastp/{sample}.fastp.html":
            f"results/preprocessing/fastp/{sample}.fastp.html",
        f"results/nfcore/star_salmon/featurecounts/{sample}.featureCounts.tsv":
            f"results/qc/featurecounts/{sample}.featureCounts.txt",
        "results/nfcore/multiqc/star_salmon/multiqc_report.html":
            "results/reports/multiqc/multiqc_report.html",
    }
    for source_relative, target_relative in mappings.items():
        source = run_dir / source_relative
        target = run_dir / target_relative
        if not source.is_file():
            raise ValueError(f"Expected reference backend output is missing: {source_relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)


def _processed_pair(run_dir: Path, sample: str, library_type: str) -> ProcessedFastqPair:
    plan = _load(run_dir / "frozen/plan.json")
    quant_only = plan.get("execution_route") == "fastq_quantification_only"
    workflow = workflow_backend_for_plan(plan)
    if (run_dir / "results/backend-output-manifest.json").is_file():
        r1 = artifact_for_role(
            run_dir, expected_backend=workflow.workflow_backend,
            role="processed_fastq_r1", sample=sample,
        )
        r2 = artifact_for_role(
            run_dir, expected_backend=workflow.workflow_backend,
            role="processed_fastq_r2", sample=sample,
        )
    else:
        native = workflow.workflow_backend == HARAKO_NATIVE_V1
        fastp = run_dir / ("results/preprocessing/fastp" if quant_only or native else "results/nfcore/fastp")
        r1, r2 = fastp / f"{sample}_R1.fastp.fastq.gz", fastp / f"{sample}_R2.fastp.fastq.gz"
    if not r1.is_file() or not r2.is_file():
        raise ValueError("Processed paired FASTQ artifacts are missing")
    def records(path: Path) -> int:
        with gzip.open(path, "rt", encoding="ascii", errors="strict") as handle:
            lines = sum(1 for _ in handle)
        if lines % 4:
            raise ValueError("Processed FASTQ structure is truncated")
        return lines // 4
    r1_records, r2_records = records(r1), records(r2)
    if r1_records < 1 or r1_records != r2_records:
        raise ValueError("Processed FASTQ pair count/orphan validation failed")
    contract = str(plan.get("processed_fastq_contract") or (
        "harako-fastp-1.0.1-fixed-v1" if quant_only else "nfcore-rnaseq-3.26.0-fastp-fixed-v1"
    ))
    return ProcessedFastqPair(sample, str(r1), str(r2), sha256_path(r1), sha256_path(r2),
                              r1_records, contract, "fastp-1.0.1-pinned",
                              ("fastp", "1.0.1", FASTP_IMAGE_IDENTITY), library_type)


def _fastq_records(path: Path) -> int:
    with gzip.open(path, "rt", encoding="ascii", errors="strict") as handle:
        lines = sum(1 for _ in handle)
    if lines % 4:
        raise ValueError("FASTQ structure is truncated")
    return lines // 4


def _run_fastp(*, run_dir: Path, run_dir_linux: str, execution: ExecutionContext,
               plan: Mapping[str, Any], sample: Mapping[str, Any], attempt: Path,
               store: RunStateStore, attempt_id: str, runner: ProcessRunner,
               monitor: ResourceMonitor | None = None) -> None:
    sample_id = str(sample["sample"])
    task_id = f"fastp:{sample_id}"
    stdout, stderr = attempt / f"fastp-{sample_id}.stdout.log", attempt / f"fastp-{sample_id}.stderr.log"
    task = _begin_task(store, task_id, attempt_id, stdout, stderr)
    if task.state is TaskState.CACHED:
        return
    r1_linux, r2_linux = str(sample["fastq_1"]), str(sample["fastq_2"])
    r1 = execution.host_path(r1_linux)
    r2 = execution.host_path(r2_linux)
    if not r1.is_file() or not r2.is_file():
        raise ValueError("Raw paired FASTQ is missing")
    if _fastq_records(r1) != _fastq_records(r2):
        raise ValueError("Raw FASTQ paired record counts differ")
    out = run_dir / "results/preprocessing/fastp"
    out.mkdir(parents=True, exist_ok=True)
    output_linux = f"{run_dir_linux}/results/preprocessing/fastp"
    uid_value, gid_value = _user_ids(execution, runner)
    fastp_contract = IMAGE_CONTRACTS["fastp"]
    image = fastp_contract.execution_reference
    docker = ["docker", "run", "--rm", "--user", f"{uid_value}:{gid_value}",
        "--mount", f"type=bind,src={r1_linux},dst=/input/R1.fastq.gz,readonly",
        "--mount", f"type=bind,src={r2_linux},dst=/input/R2.fastq.gz,readonly",
        "--mount", f"type=bind,src={output_linux},dst=/output", image,
        "fastp", "--in1", "/input/R1.fastq.gz", "--in2", "/input/R2.fastq.gz",
        "--out1", f"/output/{sample_id}_R1.fastp.fastq.gz",
        "--out2", f"/output/{sample_id}_R2.fastp.fastq.gz",
        "--json", f"/output/{sample_id}.fastp.json", "--html", f"/output/{sample_id}.fastp.html",
        "--failed_out", f"/output/{sample_id}.paired.fail.fastq.gz",
        "--unpaired1", f"/output/{sample_id}_R1.fail.fastq.gz",
        "--unpaired2", f"/output/{sample_id}_R2.fail.fastq.gz",
        "--thread", "6", "--detect_adapter_for_pe"]
    result = runner.run_streaming(_transport_argv(execution, tuple(docker)),
                                  cwd=run_dir, env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")} if execution.is_native_linux else None,
                                  stdout_path=stdout, stderr_path=stderr,
                                  on_heartbeat=(lambda: _update_status(store, stage=task.stage_id, task=task.task_id,
                                      attempt_id=attempt_id, resources=monitor.snapshot)) if monitor else None,
                                  inherit_env=not execution.is_native_linux)
    expected = (out / f"{sample_id}_R1.fastp.fastq.gz", out / f"{sample_id}_R2.fastp.fastq.gz",
                out / f"{sample_id}.fastp.json", out / f"{sample_id}.fastp.html")
    if not result.ok or any(not item.is_file() or item.stat().st_size == 0 for item in expected):
        raise RuntimeError(f"Incomplete fastp output: {result.returncode}/{result.exception}")
    pair = _processed_pair(run_dir, sample_id, str(plan["quantification"]["explicit_library_type"]))
    atomic_write_json(out / f"{sample_id}.command.json", {
        "schema_version": 1, "contract_id": "harako-fastp-1.0.1-fixed-v1",
        "structured_argv": docker, "image_reference": fastp_contract.reference,
        "image_identity": FASTP_IMAGE_IDENTITY, "returncode": result.returncode,
        "input": {"r1": r1_linux, "r2": r2_linux, "r1_sha256": sha256_path(r1), "r2_sha256": sha256_path(r2)},
        "output": {"r1_sha256": pair.r1_sha256, "r2_sha256": pair.r2_sha256,
                   "paired_fragments": pair.paired_fragments},
    })
    _finish_task(store, task, expected=tuple(item.relative_to(run_dir).as_posix() for item in expected))


def _run_salmon(*, run_dir: Path, run_dir_linux: str, execution: ExecutionContext, plan: Mapping[str, Any],
                profile_id: str, sample: str, attempt: Path, store: RunStateStore,
                attempt_id: str, runner: ProcessRunner, monitor: ResourceMonitor | None = None) -> None:
    task_id = ("salmon-primary:" if profile_id == plan["quantification"]["primary_profile_id"] else "salmon-secondary:") + sample
    stdout, stderr = attempt / f"{task_id.replace(':', '-')}.stdout.log", attempt / f"{task_id.replace(':', '-')}.stderr.log"
    task = _begin_task(store, task_id, attempt_id, stdout, stderr)
    if task.state is TaskState.CACHED:
        return
    profile = dict(plan["quantification"]["profiles"])[profile_id]
    index = ProfileIndex(**profile["index"])
    pair = _processed_pair(run_dir, sample, str(plan["quantification"]["explicit_library_type"]))
    output = run_dir / "results/quantification" / profile_id / sample
    if output.exists():
        archived = attempt / f"invalid-output-{profile_id}-{sample}"
        if archived.exists():
            raise ValueError("Invalid Salmon output archive already exists in this attempt")
        source_linux = f"{run_dir_linux}/results/quantification/{profile_id}/{sample}"
        target_linux = f"{run_dir_linux}/execution/attempts/{attempt_id}/{archived.name}"
        if execution.is_native_linux:
            shutil.move(output, archived)
        else:
            moved = runner.run(("wsl.exe", "--distribution", str(execution.distribution), "--exec", "docker", "run", "--rm",
                                "--mount", f"type=bind,src={run_dir_linux},dst=/run",
                                "--entrypoint", "/usr/bin/mv", LEGACY_WSL_UTILITY_SAMTOOLS_IMAGE_ID, "--",
                                f"/run/results/quantification/{profile_id}/{sample}",
                                f"/run/execution/attempts/{attempt_id}/{archived.name}"), timeout=30)
            if not moved.ok:
                raise ValueError(f"Cannot archive incomplete Salmon output: {moved.stderr or moved.exception}")
        _log(attempt, f"previous incomplete Salmon output archived profile={profile_id}")
    request = VersionedSalmonRequest(profile_id, pair, index, Path(plan["reference"]["gtf_path"]), output)
    # Build with canonical Linux paths, while validation uses the corresponding WSL UNC files.
    profile_contract = get_profile(profile_id)
    index_linux = index.path
    fastp_root = (
        "results/preprocessing/fastp"
        if plan.get("execution_route") == "fastq_quantification_only"
        or workflow_backend_for_plan(plan).workflow_backend == HARAKO_NATIVE_V1
        else "results/nfcore/fastp"
    )
    r1_linux = f"{run_dir_linux}/{fastp_root}/{sample}_R1.fastp.fastq.gz"
    r2_linux = f"{run_dir_linux}/{fastp_root}/{sample}_R2.fastp.fastq.gz"
    output_linux = f"{run_dir_linux}/results/quantification/{profile_id}/{sample}"
    runtime_image = dict(profile.get("runtime_image") or {})
    if runtime_image:
        image_contract = DockerImageContract(
            str(runtime_image.get("reference")), str(runtime_image.get("identity")),
            str(runtime_image.get("identity_kind")),  # type: ignore[arg-type]
        )
        host_profile_id = str(dict(dict(plan.get("capability_snapshot") or {}).get("result") or {}).get("host_profile_id"))
        expected_overlay = runtime_quantification_image_contract(host_profile_id, profile_id)
        if expected_overlay is None or image_contract.as_dict() != expected_overlay.as_dict():
            raise ValueError("Runtime quantification image overlay mismatch")
    else:
        image_contract = IMAGE_CONTRACTS[profile_id]
        if (image_contract.reference, image_contract.identity) != (
            profile_contract.image_reference, profile_contract.image_identity,
        ):
            raise ValueError("Profile and execution image contracts differ")
    execution_image = image_contract.execution_reference
    uid_value, gid_value = _user_ids(execution, runner)
    profile_root_linux = f"{run_dir_linux}/results/quantification/{profile_id}"
    if execution.is_native_linux:
        execution.host_path(profile_root_linux).mkdir(parents=True, exist_ok=True)
    else:
        mkdir = runner.run(("wsl.exe", "--distribution", str(execution.distribution), "--exec", "/usr/bin/mkdir", "-p", "--",
                            profile_root_linux), timeout=10)
        if not mkdir.ok:
            raise ValueError("Cannot create profile-specific output root")
        ownership = runner.run(("wsl.exe", "--distribution", str(execution.distribution), "--exec", "docker", "run", "--rm",
                                "--mount", f"type=bind,src={profile_root_linux},dst=/target",
                                "--entrypoint", "/usr/bin/chown", LEGACY_WSL_UTILITY_SAMTOOLS_IMAGE_ID,
                                f"{uid_value}:{gid_value}", "/target"), timeout=30)
        if not ownership.ok:
            raise ValueError("Cannot establish non-root profile output ownership")
    docker = ["docker", "run", "--rm", "--user", f"{uid_value}:{gid_value}",
        "--mount", f"type=bind,src={index_linux},dst=/input/index,readonly",
        "--mount", f"type=bind,src={r1_linux},dst=/input/reads/R1.fastq.gz,readonly",
        "--mount", f"type=bind,src={r2_linux},dst=/input/reads/R2.fastq.gz,readonly",
        "--mount", f"type=bind,src={run_dir_linux}/frozen/tx2gene.tsv,dst=/input/reference/tx2gene.tsv,readonly",
        "--mount", f"type=bind,src={run_dir_linux}/results/quantification/{profile_id},dst=/output",
        execution_image]
    from harako_gpu.services.quantification_profiles import salmon_argv
    docker += list(salmon_argv(profile_id, index="/input/index", gene_map="/input/reference/tx2gene.tsv",
        r1="/input/reads/R1.fastq.gz", r2="/input/reads/R2.fastq.gz", output=f"/output/{sample}",
        library_type=pair.library_type))
    command = _transport_argv(execution, tuple(docker))
    started_at = utc_now()
    monotonic_started = time.monotonic()
    result = runner.run_streaming(command, cwd=run_dir,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")} if execution.is_native_linux else None,
        stdout_path=stdout, stderr_path=stderr,
        on_heartbeat=(lambda: _update_status(store, stage=task.stage_id, task=task.task_id,
            attempt_id=attempt_id, resources=monitor.snapshot)) if monitor else None,
        inherit_env=not execution.is_native_linux)
    ended_at = utc_now()
    wall_seconds = max(time.monotonic() - monotonic_started, 1e-9)
    _log(attempt, f"salmon process returned profile={profile_id} code={result.returncode} exception={result.exception}")
    quant = output / "quant.sf"
    genes = output / "quant.genes.sf"
    if not result.ok or not quant.is_file() or not genes.is_file():
        raise RuntimeError(f"Incomplete Salmon output for {profile_id}: {result.returncode}/{result.exception}")
    parse_quant_sf(quant.read_text(encoding="utf-8")); parse_quant_sf(genes.read_text(encoding="utf-8"))
    _log(attempt, f"salmon outputs parsed profile={profile_id}")
    metadata = execution_metadata(request, tuple(docker))
    metadata.update({"image_reference": image_contract.reference,
                     "image_identity": image_contract.identity})
    metadata.update({
        "returncode": result.returncode, "run_id": _identity(run_dir)["run_id"],
        "profile_id": profile_id, "version": profile_contract.version,
        "threads": profile_contract.threads, "index_id": index.index_id,
    })
    metadata.update(_salmon_timing(
        started_at=started_at, ended_at=ended_at, wall_seconds=wall_seconds,
        paired_fragments=pair.paired_fragments,
        execution_order=1 if profile_id == plan["quantification"]["primary_profile_id"] else 2,
    ))
    atomic_write_json(output / "command.json", metadata)
    atomic_write_json(output / "versions.json", {"salmon": get_profile(profile_id).version,
                                                   "image_identity": image_contract.identity})
    atomic_write_json(output / "input_manifest.json", metadata["processed_fastq"])
    _log(attempt, f"salmon manifests written profile={profile_id}")
    _finish_task(store, task, expected=(quant.relative_to(run_dir).as_posix(), genes.relative_to(run_dir).as_posix()))
    _log(attempt, f"salmon task completed profile={profile_id}")


def _select_star(run_dir: Path, plan: Mapping[str, Any], sample: str,
                 execution: ExecutionContext) -> None:
    source = run_dir / "results/alignment" / sample / f"{sample}.ReadsPerGene.out.tab"
    table = parse_reads_per_gene(source.read_text(encoding="utf-8"))
    gtf = execution.host_path(str(plan["reference"]["gtf_path"]))
    with (gzip.open(gtf, "rt", encoding="utf-8") if gtf.suffix == ".gz" else gtf.open(encoding="utf-8")) as handle:
        annotations = parse_gtf_annotations(handle.read())
    validate_gene_universe(table, annotations)
    library = str(plan["quantification"]["explicit_library_type"])
    column, counts = table.selected(library)
    output = run_dir / "results/alignment/star_gene_counts"
    output.mkdir(parents=True, exist_ok=True)
    selected = output / f"{sample}.selected_gene_counts.tsv"
    write_new_text(selected, selected_counts_tsv(counts))
    write_new_text(output / f"{sample}.metadata_counts.tsv", metadata_counts_tsv(table.metadata, column))
    pair = _processed_pair(run_dir, sample, library)
    manifest = column_manifest(sample=sample, source_file=source.relative_to(run_dir).as_posix(),
        source_sha256=sha256_path(source), library_type=library, gtf_sha256=plan["reference"]["gtf_sha256"],
        reference_pack_id=plan["reference"]["reference_pack_id"],
        processed_fastq_sha256=f"{pair.r1_sha256}:{pair.r2_sha256}", run_identity=_identity(run_dir)["identity_digest"])
    atomic_write_json(output / f"{sample}.column_manifest.json", manifest)


def _quant_map(path: Path) -> dict[str, Any]:
    return {row.feature_id: row for row in parse_quant_sf(path.read_text(encoding="utf-8"))}


def _star_counts(path: Path) -> dict[str, float]:
    rows = csv.DictReader(path.read_text(encoding="utf-8").splitlines(), delimiter="\t")
    return {row["gene_id"]: float(row["count"]) for row in rows}


def _build_concordance(run_dir: Path, plan: Mapping[str, Any], sample: str,
                       execution: ExecutionContext) -> None:
    primary = str(plan["quantification"]["primary_profile_id"])
    secondary = str(plan["quantification"]["secondary_profile_id"])
    base = run_dir / "results/quantification"
    pt, st = _quant_map(base / primary / sample / "quant.sf"), _quant_map(base / secondary / sample / "quant.sf")
    pg, sg = _quant_map(base / primary / sample / "quant.genes.sf"), _quant_map(base / secondary / sample / "quant.genes.sf")
    transcript = compare_abundance({k: v.tpm for k, v in pt.items()}, {k: v.tpm for k, v in st.items()})
    gene = compare_abundance({k: v.tpm for k, v in pg.items()}, {k: v.tpm for k, v in sg.items()})
    transcript_counts = compare_abundance(
        {k: v.num_reads for k, v in pt.items()}, {k: v.num_reads for k, v in st.items()},
    )
    gene_counts = compare_abundance(
        {k: v.num_reads for k, v in pg.items()}, {k: v.num_reads for k, v in sg.items()},
    )
    gtf = execution.host_path(str(plan["reference"]["gtf_path"]))
    with (gzip.open(gtf, "rt", encoding="utf-8") if gtf.suffix == ".gz" else gtf.open(encoding="utf-8")) as handle:
        annotations = parse_gtf_annotations(handle.read())
    strata = stratified_concordance({k: v.tpm for k, v in pg.items()}, {k: v.tpm for k, v in sg.items()}, annotations)
    quant_only = plan.get("execution_route") == "fastq_quantification_only"
    if quant_only:
        star_results, star_strata, star_status = {}, {}, "NOT_APPLICABLE"
    else:
        star = _star_counts(run_dir / "results/alignment/star_gene_counts" / f"{sample}.selected_gene_counts.tsv")
        star_results = {primary: compare_orthogonal_gene_counts(star, {k: v.num_reads for k, v in pg.items()}),
                        secondary: compare_orthogonal_gene_counts(star, {k: v.num_reads for k, v in sg.items()})}
        star_strata = {primary: stratified_orthogonal_concordance(star, {k: v.num_reads for k, v in pg.items()}, annotations),
                       secondary: stratified_orthogonal_concordance(star, {k: v.num_reads for k, v in sg.items()}, annotations)}
        star_status = "AVAILABLE_QUALIFIED"
    destination = run_dir / "results/concordance"; destination.mkdir(parents=True, exist_ok=True)
    identity = _identity(run_dir)
    runtime_profiles = {}
    for profile_id in (primary, secondary):
        command_path = base / profile_id / sample / "command.json"
        command = _load(command_path)
        quant_path = base / profile_id / sample / "quant.sf"
        runtime_profiles[profile_id] = {
            "wall_seconds": command["wall_seconds"],
            "fragments_per_second": command["fragments_per_second"],
            "execution_order": command["execution_order"],
            "output_bytes": sum(
                path.stat().st_size for path in (
                    quant_path, base / profile_id / sample / "quant.genes.sf",
                )
            ),
            "quant_sf_rows": len(_quant_map(quant_path)),
        }
    runtime = compare_profile_runtimes(
        runtime_profiles, {profile_id: get_profile(profile_id).version for profile_id in runtime_profiles},
    )
    payload = {"schema_version": 2, "comparison_id": identity["analysis_series_id"],
        "analysis_series_id": identity["analysis_series_id"], "primary_profile_id": primary,
        "secondary_profile_id": secondary, "star_comparator_status": star_status,
        "transcript": result_dict(transcript), "gene": result_dict(gene),
        "transcript_tpm": result_dict(transcript), "gene_tpm": result_dict(gene),
        "transcript_num_reads": result_dict(transcript_counts),
        "gene_num_reads": result_dict(gene_counts), "runtime": runtime,
        "star": {k: result_dict(v) for k, v in star_results.items()}, "annotation_strata": strata,
        "star_annotation_strata": star_strata, "limitations": ["descriptive only", "profile difference is not an error verdict"]}
    atomic_write_json(destination / "profile_comparison.json", payload)
    write_new_text(destination / "profile_comparison.tsv", "level\tcommon\tspearman\tpearson\ttop100_overlap\n" +
        f"transcript_tpm\t{transcript.common_features}\t{transcript.spearman}\t{transcript.log_pearson}\t{transcript.top100_overlap}\n" +
        f"gene_tpm\t{gene.common_features}\t{gene.spearman}\t{gene.log_pearson}\t{gene.top100_overlap}\n" +
        f"transcript_num_reads\t{transcript_counts.common_features}\t{transcript_counts.spearman}\t{transcript_counts.log_pearson}\t{transcript_counts.top100_overlap}\n" +
        f"gene_num_reads\t{gene_counts.common_features}\t{gene_counts.spearman}\t{gene_counts.log_pearson}\t{gene_counts.top100_overlap}\n")
    for level, result in (("transcript", transcript), ("gene", gene)):
        text = "feature_id\tprimary_tpm\tsecondary_tpm\tabs_log2_ratio\tcategory\n" + "".join(
            f"{row.feature_id}\t{row.left_tpm}\t{row.right_tpm}\t{row.log2_ratio}\t{row.category}\n"
            for row in result.sensitive_features)
        write_new_text(destination / f"{level}_method_sensitive.tsv", text)
    if not quant_only:
        write_new_text(destination / ORTHOGONAL_GENE_CONCORDANCE_ARTIFACT,
            "profile_id\tcommon_genes\tspearman\tpearson\ttop100_overlap\n" + "".join(
            f"{key}\t{value.common_genes}\t{value.spearman}\t{value.log_pearson}\t{value.top100_overlap}\n"
            for key, value in star_results.items()))
    write_new_text(destination / "annotation_stratified_concordance.tsv", "stratum\tfeatures\n" + "".join(
        f"{row['stratum']}\t{row['features']}\n" for row in strata))
    report = render_summary_html(analysis_series_id=identity["analysis_series_id"],
        project_id=identity["project_slug"], primary_profile=get_profile(primary).as_dict(),
        secondary_profile=get_profile(secondary).as_dict(), reference_pack_id=identity["reference_pack_id"],
        library_type=str(plan["quantification"]["explicit_library_type"]),
        processed_fastq_identity="shared-fastp-pair", transcript=transcript, gene=gene,
        star_status=star_status, star_results=star_results)
    if quant_only:
        report = report.replace("</body>",
            "<section><h2>Route identity / 経路</h2>"
            "<p>このrunはFASTQから発現定量のみを実行しました。ゲノムalignment、BAM、splice junction、STAR GeneCountsは生成していません。Salmon定量はCPU処理であり、GPUは使用していません。</p>"
            "<p>This run performed expression quantification directly from FASTQ. Genome alignment, BAM, splice-junction, and STAR GeneCounts artifacts were not generated. Salmon quantification is CPU-based; the GPU was not used in this route.</p>"
            "</section></body>")
    write_new_text(destination / "summary.html", report)
    payload["report_sha256"] = sha256_path(destination / "summary.html")
    atomic_write_json(destination / "manifest.json", payload)


def _single_report(run_dir: Path, plan: Mapping[str, Any]) -> None:
    primary = str(plan["quantification"]["primary_profile_id"])
    quant_only = plan.get("execution_route") == "fastq_quantification_only"
    route_copy = ("<p>このrunはFASTQから発現定量のみを実行しました。ゲノムalignment、BAM、splice junction、STAR GeneCountsは生成していません。Salmon定量はCPU処理であり、GPUは使用していません。</p>"
                  "<p>This run performed expression quantification directly from FASTQ. Genome alignment, BAM, splice-junction, and STAR GeneCounts artifacts were not generated. Salmon quantification is CPU-based; the GPU was not used in this route.</p>"
                  if quant_only else "<p>STAR comparator: AVAILABLE_QUALIFIED</p>")
    html = f"""<!doctype html><html><meta charset='utf-8'><title>Harako-GPU run report</title>
<body><h1>Harako-GPU run report / 実行レポート</h1><p>primary profile: {primary}</p>
{route_copy}<p>Only the primary profile is downstream-eligible.</p>
<p>Research use only; non-diagnostic and non-clinical.</p></body></html>"""
    write_new_text(run_dir / "results/reports/summary.html", html)


def _resume_nextflow_argv(
    frozen_argv: tuple[str, ...], attempt_dir: str,
) -> tuple[str, ...]:
    """Target the frozen session and give its observers attempt-local outputs."""
    positions = [index for index, value in enumerate(frozen_argv) if value == "-name"]
    if len(positions) != 1:
        raise ValueError("Frozen Nextflow command must contain exactly one -name")
    position = positions[0]
    if position + 1 >= len(frozen_argv) or not frozen_argv[position + 1]:
        raise ValueError("Frozen Nextflow command has no run name")
    run_name = frozen_argv[position + 1]
    resumed = list(frozen_argv[:position] + frozen_argv[position + 2:])
    for flag, filename in (
        ("-with-report", "report.html"),
        ("-with-timeline", "timeline.html"),
        ("-with-trace", "trace.tsv"),
        ("-with-dag", "dag.html"),
    ):
        matches = [index for index, value in enumerate(resumed) if value == flag]
        if len(matches) != 1 or matches[0] + 1 >= len(resumed):
            raise ValueError(f"Frozen Nextflow command must contain exactly one {flag}")
        resumed[matches[0] + 1] = f"{attempt_dir}/{filename}"
    return tuple(resumed) + ("-resume", run_name)


def _run_nfcore(run_dir: Path, run_dir_linux: str, execution: ExecutionContext, attempt: Path,
                store: RunStateStore, attempt_id: str, runner: ProcessRunner, resume: bool) -> None:
    stdout, stderr = attempt / "stdout.log", attempt / "stderr.log"
    plan = _load(run_dir / "frozen/plan.json")
    workflow = workflow_backend_for_plan(plan)
    task_id = "harako-native-alignment" if workflow.workflow_backend == HARAKO_NATIVE_V1 else "nfcore-alignment"
    task = _begin_task(store, task_id, attempt_id, stdout, stderr)
    if task.state is TaskState.CACHED:
        return
    source = _load(run_dir / "frozen/command.json")
    frozen_argv = tuple(source["argv"])
    linux_attempt = f"{run_dir_linux}/execution/attempts/{attempt_id}"
    argv = _resume_nextflow_argv(frozen_argv, linux_attempt) if resume else frozen_argv
    spec = CommandSpec(argv, source["cwd"], source["env"], f"{run_dir_linux}/execution/attempts/{attempt_id}/linux.pid")
    write_command_spec(attempt / "command.json", spec)
    monitor = ResourceMonitor(execution=execution, work_root=str(_identity(run_dir)["work_root"]),
                              result_root=run_dir_linux, log_path=attempt / "resource-monitor.tsv", runner=runner)
    monitor.start()
    heartbeat = lambda: _update_status(store, stage=task.stage_id, task=task.task_id,
                                       attempt_id=attempt_id, resources=monitor.snapshot)
    if execution.is_native_linux:
        result = run_native_streaming(
            spec, runner=runner, stdout_path=stdout, stderr_path=stderr,
            on_started=lambda pid: store.update_lock_pids(linux_pid=pid), on_heartbeat=heartbeat,
        )
    else:
        command = wsl_exec_argv(
            distribution=str(execution.distribution),
            runner_path=f"{run_dir_linux}/frozen/wsl_exec_runner.py",
            spec_path=f"{linux_attempt}/command.json",
        )
        result = runner.run_streaming(
            command, cwd=run_dir, env=None, stdout_path=stdout, stderr_path=stderr,
            on_started=lambda pid: store.update_lock_pids(wsl_pid=pid), on_heartbeat=heartbeat,
        )
    monitor.stop()
    linux_pid = attempt / "linux.pid"
    if linux_pid.is_file() and linux_pid.read_text(encoding="utf-8").strip().isdigit():
        store.update_lock_pids(linux_pid=int(linux_pid.read_text(encoding="utf-8")))
    for current, name in (("current-trace.tsv", "trace.tsv"), ("current-report.html", "report.html"),
                          ("current-timeline.html", "timeline.html"), ("current-dag.html", "dag.html")):
        path = run_dir / "execution" / current
        if resume:
            if (attempt / name).exists(): shutil.copy2(attempt / name, path)
        elif path.exists():
            shutil.copy2(path, attempt / name)
    nextflow_log = run_dir / ".nextflow.log"
    if nextflow_log.exists(): shutil.copy2(nextflow_log, attempt / "nextflow.log")
    if result.exception == "INTERRUPTED":
        raise KeyboardInterrupt
    if not result.ok:
        if (attempt / "trace.tsv").is_file():
            try:
                work_local = execution.host_path(str(_identity(run_dir)["work_root"]))
                collect_failed_task_evidence(trace=attempt / "trace.tsv", work_root=work_local,
                                             destination=run_dir / "tasks")
            except (OSError, ValueError) as evidence_error:
                _log(attempt, f"failed task evidence unavailable: {evidence_error}")
        raise RuntimeError(f"Nextflow failed: {result.returncode}/{result.exception}")
    trace = attempt / "trace.tsv"
    counts = parse_trace_counts(trace.read_text(encoding="utf-8")) if trace.is_file() else {}
    names = []
    if trace.is_file():
        with trace.open(encoding="utf-8") as handle:
            names = [row.get("name", "") for row in csv.DictReader(handle, delimiter="\t")]
    parabricks = [
        name for name in names
        if ("PARABRICKS_RNA_FQ2BAM" in name
            and (workflow.workflow_backend == HARAKO_NATIVE_V1 or "ALIGN_STAR:" in name))
    ]
    forbidden = [name for name in names if "QUANTIFY_BAM_SALMON:SALMON_QUANT" in name or
                 "QUANTIFY_PSEUDO_ALIGNMENT:SALMON_QUANT" in name or ":STAR_ALIGN" in name]
    if not parabricks or forbidden:
        raise RuntimeError(f"Unexpected pipeline process identity; parabricks={len(parabricks)}, forbidden={forbidden}")
    _update_status(store, stage=task.stage_id, task=task.task_id, attempt_id=attempt_id,
                   resources=monitor.snapshot, processes=counts)
    _finish_task(
        store,
        task,
        expected=("results/alignment", "results/preprocessing/fastp", "results/reports/multiqc")
        if workflow.workflow_backend == HARAKO_NATIVE_V1 else ("results/nfcore",),
    )


def execute_run(*, run_dir: Path, approval_hash: str, resume: bool = False,
                distribution: str = "Ubuntu", execution_context: str = "wsl2",
                runner: ProcessRunner | None = None) -> RunStatus:
    run_dir = run_dir.resolve(); store = RunStateStore(run_dir); process = runner or ProcessRunner()
    verify_frozen(run_dir)
    identity = _identity(run_dir); plan = _load(run_dir / "frozen/plan.json")
    execution = require_context_match(
        requested=execution_context, frozen=str(identity["execution_context"]), distribution=distribution,
    )
    if approval_hash != identity["approval_hash"]:
        raise ValueError("Approval hash mismatch")
    current = store.status()
    lock_state = store.inspect_lock(distribution=execution.distribution, runner=process)
    if lock_state == "LIVE": raise ValueError("A live run lock already exists")
    if lock_state == "STALE":
        store.archive_stale_lock()
        if current.state is RunState.RUNNING:
            current = store.transition(RunState.INTERRUPTED, resumable=True,
                                       failure={"classification": "INTERRUPTION",
                                                "message": "Stale controller lock archived"})
    if resume:
        if current.state not in {RunState.FAILED, RunState.INTERRUPTED}:
            raise ValueError("Only FAILED or INTERRUPTED runs may resume")
    elif current.state is not RunState.PREPARED:
        raise ValueError("A run may start exactly once from PREPARED")
    attempt_id, attempt = _attempt_dir(run_dir)
    source_command = _load(run_dir / "frozen/command.json")
    store.create_lock(attempt_id=attempt_id, execution_context=identity["execution_context"],
                      command_identity=source_command["argv_sha256"])
    store.transition(RunState.RUNNING, resume=resume, attempt_id=attempt_id, started_at=current.started_at or utc_now(),
                     ended_at=None, failure=None, resumable=False, next_actions=("run status",))
    _set_attempt(attempt, AttemptState.RUNNING, started_at=utc_now())
    _log(attempt, f"attempt started resume={resume}")
    active: TaskRecord | None = None
    monitor: ResourceMonitor | None = None
    try:
        pre = _begin_task(store, "preflight", attempt_id, attempt / "preflight.stdout.log", attempt / "preflight.stderr.log")
        _finish_task(store, pre)
        quant_only = plan.get("execution_route") == "fastq_quantification_only"
        samples = tuple(str(item["sample"]) for item in plan["samples"])
        if quant_only:
            monitor = ResourceMonitor(execution=execution, work_root=str(identity["work_root"]),
                                      result_root=str(identity["launch_directory"]),
                                      log_path=attempt / "resource-monitor.tsv", runner=process)
            monitor.start()
            for raw_sample in plan["samples"]:
                sample = str(raw_sample["sample"])
                task_id = f"input-validation:{sample}"
                active = _begin_task(store, task_id, attempt_id, attempt / f"{task_id}.stdout.log", attempt / f"{task_id}.stderr.log")
                if active.state is not TaskState.CACHED:
                    for role in ("fastq_1", "fastq_2"):
                        source = execution.host_path(str(raw_sample[role]))
                        if not source.is_file() or source.stat().st_size == 0:
                            raise ValueError(f"Raw FASTQ input invalid: {sample}/{role}")
                    _finish_task(store, active)
                active = next(item for item in store.read_tasks() if item.task_id == f"fastp:{sample}")
                _run_fastp(run_dir=run_dir, run_dir_linux=str(identity["launch_directory"]), execution=execution,
                           plan=plan, sample=raw_sample, attempt=attempt, store=store,
                           attempt_id=attempt_id, runner=process, monitor=monitor)
                task_id = f"processed-fastq-validation:{sample}"
                active = _begin_task(store, task_id, attempt_id, attempt / f"{task_id}.stdout.log", attempt / f"{task_id}.stderr.log")
                if active.state is not TaskState.CACHED:
                    _processed_pair(run_dir, sample, str(plan["quantification"]["explicit_library_type"]))
                    _finish_task(store, active)
        else:
            alignment_task_id = (
                "harako-native-alignment"
                if workflow_backend_for_plan(plan).workflow_backend == HARAKO_NATIVE_V1
                else "nfcore-alignment"
            )
            active = next(item for item in store.read_tasks() if item.task_id == alignment_task_id)
            _run_nfcore(run_dir, str(identity["launch_directory"]), execution,
                        attempt, store, attempt_id, process, resume)
            for sample in samples:
                task_id = f"alignment-validation:{sample}"
                active = _begin_task(store, task_id, attempt_id, attempt / f"{task_id}.stdout.log", attempt / f"{task_id}.stderr.log")
                if active.state is not TaskState.CACHED:
                    alignment = _copy_alignment_artifacts(run_dir, sample)
                    bam_linux = f"{identity['launch_directory']}/results/alignment/{sample}/{alignment['bam'].name}"
                    bai_linux = f"{identity['launch_directory']}/results/alignment/{sample}/{alignment['bai'].name}"
                    validator = resolve_frozen_bam_validator_contract(run_dir)
                    bam = validate_bam(
                        execution=execution,
                        bam=bam_linux,
                        bai=bai_linux,
                        image_contract=validator.contract,
                        runner=process,
                    )
                    if not bam.valid:
                        raise ValueError("BAM structural/scientific validation failed")
                    atomic_write_json(run_dir / "results/alignment" / sample / "bam-validation.json", asdict(bam))
                    _finish_task(store, active)
        primary = str(plan["quantification"]["primary_profile_id"])
        secondary = plan["quantification"].get("secondary_profile_id")
        for sample in samples:
            active = next(item for item in store.read_tasks() if item.task_id == f"salmon-primary:{sample}")
            _run_salmon(run_dir=run_dir, run_dir_linux=str(identity["launch_directory"]), execution=execution,
                plan=plan, profile_id=primary, sample=sample, attempt=attempt, store=store, attempt_id=attempt_id, runner=process, monitor=monitor)
        if secondary:
            for sample in samples:
                active = next(item for item in store.read_tasks() if item.task_id == f"salmon-secondary:{sample}")
                _run_salmon(run_dir=run_dir, run_dir_linux=str(identity["launch_directory"]), execution=execution,
                    plan=plan, profile_id=str(secondary), sample=sample, attempt=attempt, store=store, attempt_id=attempt_id, runner=process, monitor=monitor)
        for profile_id in (primary, secondary):
            if not profile_id: continue
            task_id = f"matrices:{profile_id}"; active = _begin_task(store, task_id, attempt_id, attempt / f"{task_id}.stdout.log", attempt / f"{task_id}.stderr.log")
            if active.state is not TaskState.CACHED:
                build_profile_matrices(run_dir=run_dir, profile_id=str(profile_id), samples=samples); _finish_task(store, active)
        if not quant_only:
            for sample in samples:
                task_id = f"star-counts:{sample}"; active = _begin_task(store, task_id, attempt_id, attempt / f"{task_id}.stdout.log", attempt / f"{task_id}.stderr.log")
                if active.state is not TaskState.CACHED: _select_star(run_dir, plan, sample, execution); _finish_task(store, active)
        if secondary:
            active = _begin_task(store, "concordance", attempt_id, attempt / "concordance.stdout.log", attempt / "concordance.stderr.log")
            if active.state is not TaskState.CACHED: _build_concordance(run_dir, plan, samples[0], execution); _finish_task(store, active)
        active = _begin_task(store, "report", attempt_id, attempt / "report.stdout.log", attempt / "report.stderr.log")
        if active.state is not TaskState.CACHED:
            if secondary: shutil.copy2(run_dir / "results/concordance/summary.html", run_dir / "results/reports/summary.html")
            else: _single_report(run_dir, plan)
            _finish_task(store, active)
        active = _begin_task(store, "artifacts", attempt_id, attempt / "artifacts.stdout.log", attempt / "artifacts.stderr.log")
        verification = verify_artifacts(run_dir=run_dir, deep=False, distribution=distribution, runner=process)
        if not verification["complete"]:
            raise ValueError("Required artifact verification failed")
        _finish_task(store, active)
        if monitor:
            monitor.stop()
            monitor = None
        active = _begin_task(store, "terminal", attempt_id, attempt / "terminal.stdout.log", attempt / "terminal.stderr.log")
        _finish_task(store, active)
        _set_attempt(attempt, AttemptState.SUCCEEDED, ended_at=utc_now())
        store.release_lock()
        return store.transition(RunState.COMPLETED, ended_at=utc_now(), resumable=False,
                                current_stage=StageId.TERMINAL.value, current_task=None,
                                task_counts=_task_counts(store.read_tasks()), next_actions=("artifacts verify",))
    except KeyboardInterrupt:
        if monitor: monitor.stop()
        _fail(store, attempt, active, FailureClassification.INTERRUPTION, "Execution interrupted", "Controller received Ctrl+C", interrupted=True)
        store.release_lock(); return store.status()
    except Exception as exc:
        if monitor: monitor.stop()
        classification = FailureClassification.UNKNOWN
        if active and active.task_id.startswith("fastp:"): classification = FailureClassification.PREPROCESSING
        elif active and active.stage_id == StageId.NFCORE.value: classification = FailureClassification.NEXTFLOW
        elif active and active.stage_id == StageId.ALIGNMENT_VALIDATION.value: classification = FailureClassification.BAM_VALIDATION
        elif active and active.stage_id == StageId.SALMON_PRIMARY.value: classification = FailureClassification.SALMON_PRIMARY
        elif active and active.stage_id == StageId.SALMON_SECONDARY.value: classification = FailureClassification.SALMON_SECONDARY
        elif active and active.stage_id == StageId.MATRICES.value: classification = FailureClassification.MATRIX
        elif active and active.stage_id == StageId.STAR_COUNTS.value: classification = FailureClassification.STAR_GENECOUNTS
        elif active and active.stage_id == StageId.CONCORDANCE.value: classification = FailureClassification.CONCORDANCE
        elif active and active.stage_id == StageId.ARTIFACTS.value: classification = FailureClassification.ARTIFACT_VALIDATION
        _fail(store, attempt, active, classification, str(exc), repr(exc)); store.release_lock(); return store.status()
