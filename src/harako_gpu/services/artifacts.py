"""Mode-aware artifact discovery and structural/deep verification."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from harako_gpu.adapters.bio_validation import validate_bam
from harako_gpu.adapters.execution_context import parse_execution_context
from harako_gpu.adapters.filesystem import atomic_write_json, ensure_within, sha256_path
from harako_gpu.adapters.process import ProcessRunner
from harako_gpu.adapters.wsl import unc_path_to_linux
from harako_gpu.core.run_lifecycle import ArtifactRecord, ArtifactState, StageId
from harako_gpu.services.concordance import parse_quant_sf
from harako_gpu.services.quantification_profiles import salmon_library_type_for_product
from harako_gpu.services.runtime_validation_images import resolve_frozen_bam_validator_contract
from harako_gpu.services.star_gene_counts import parse_reads_per_gene
from harako_gpu.services.workflow_backends import HARAKO_NATIVE_V1, workflow_backend_for_plan
from harako_gpu.services.backend_outputs import validate_backend_output_manifest


def _load(run_dir: Path, relative: str) -> dict:
    value = json.loads((run_dir / relative).read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _expected(run_dir: Path) -> list[tuple[str, str, str | None, str | None, str, str, bool]]:
    plan = _load(run_dir, "frozen/plan.json")
    quant = dict(plan["quantification"])
    quant_only = plan.get("execution_route") == "fastq_quantification_only"
    backend_contract = "workflow_backend" in plan
    native_backend = workflow_backend_for_plan(plan).workflow_backend == HARAKO_NATIVE_V1
    samples = [str(item["sample"]) for item in plan["samples"]]
    profiles = [quant["primary_profile_id"]] + ([quant["secondary_profile_id"]] if quant.get("secondary_profile_id") else [])
    rows: list[tuple[str, str, str | None, str | None, str, str, bool]] = [
        ("run-manifest", "run_manifest", None, None, "run.json", StageId.PREFLIGHT.value, True),
        ("plan", "plan", None, None, "frozen/plan.json", StageId.PREFLIGHT.value, True),
        ("hardware", "hardware_report", None, None, "frozen/hardware-report.json", StageId.PREFLIGHT.value, True),
        ("versions", "versions", None, None, "frozen/versions.tsv", StageId.PREFLIGHT.value, True),
        ("backend-output-manifest", "backend_output_manifest", None, None,
         "results/backend-output-manifest.json", StageId.ALIGNMENT_VALIDATION.value, not quant_only),
    ]
    attempts = sorted((run_dir / "execution/attempts").glob("[0-9][0-9][0-9][0-9]"))
    evidence_attempts = [item for item in attempts if (item / "report.html").is_file()]
    if evidence_attempts:
        latest_attempt = evidence_attempts[-1]
        latest = latest_attempt.relative_to(run_dir).as_posix()
        for name, role in (("report.html", "nextflow_report"), ("timeline.html", "nextflow_timeline"),
                           ("trace.tsv", "nextflow_trace"), ("dag.html", "nextflow_dag")):
            rows.append((f"{role}:{latest_attempt.name}", role, None, None, f"{latest}/{name}", StageId.NFCORE.value, True))
    for sample in samples:
        prefix = f"results/alignment/{sample}/{sample}"
        rows.extend((
            (f"bam:{sample}", "genomic_bam", None, sample, f"{prefix}.sorted.bam", StageId.NFCORE.value, not quant_only),
            (f"bai:{sample}", "genomic_bai", None, sample, f"{prefix}.sorted.bam.bai", StageId.NFCORE.value, not quant_only),
            (f"star-log:{sample}", "star_log_final", None, sample, f"{prefix}.Log.final.out", StageId.NFCORE.value, not quant_only),
            (f"junction:{sample}", "star_junction", None, sample, f"{prefix}.SJ.out.tab", StageId.NFCORE.value, not quant_only),
            (f"reads-per-gene:{sample}", "star_reads_per_gene", None, sample, f"{prefix}.ReadsPerGene.out.tab", StageId.NFCORE.value, not quant_only),
            (f"selected-star:{sample}", "star_selected_counts", None, sample,
             f"results/alignment/star_gene_counts/{sample}.selected_gene_counts.tsv", StageId.STAR_COUNTS.value, not quant_only),
        ))
        if quant_only or backend_contract:
            fastp = "results/preprocessing/fastp"
            rows.extend((
                (f"processed-r1:{sample}", "processed_fastq_r1", None, sample, f"{fastp}/{sample}_R1.fastp.fastq.gz", StageId.NFCORE.value, True),
                (f"processed-r2:{sample}", "processed_fastq_r2", None, sample, f"{fastp}/{sample}_R2.fastp.fastq.gz", StageId.NFCORE.value, True),
                (f"fastp-json:{sample}", "fastp_json", None, sample, f"{fastp}/{sample}.fastp.json", StageId.NFCORE.value, True),
                (f"fastp-html:{sample}", "fastp_html", None, sample, f"{fastp}/{sample}.fastp.html", StageId.NFCORE.value, True),
            ))
            if quant_only or native_backend:
                rows.append((
                    f"fastp-command:{sample}", "fastp_command", None, sample,
                    f"{fastp}/{sample}.command.json", StageId.NFCORE.value, True,
                ))
        if not quant_only and backend_contract:
            rows.append((
                f"featurecounts:{sample}", "featurecounts_biotype", None, sample,
                f"results/qc/featurecounts/{sample}.featureCounts.txt", StageId.NFCORE.value, True,
            ))
        for profile in profiles:
            stage = StageId.SALMON_PRIMARY.value if profile == profiles[0] else StageId.SALMON_SECONDARY.value
            root = f"results/quantification/{profile}/{sample}"
            rows.extend((
                (f"quant:{profile}:{sample}", "salmon_quant", profile, sample, f"{root}/quant.sf", stage, True),
                (f"quant-gene:{profile}:{sample}", "salmon_gene_quant", profile, sample, f"{root}/quant.genes.sf", stage, True),
                (f"quant-meta:{profile}:{sample}", "salmon_meta", profile, sample, f"{root}/aux_info/meta_info.json", stage, True),
                (f"quant-command:{profile}:{sample}", "salmon_command", profile, sample, f"{root}/command.json", stage, True),
                (f"quant-input:{profile}:{sample}", "salmon_input_manifest", profile, sample, f"{root}/input_manifest.json", stage, True),
                (f"quant-version:{profile}:{sample}", "salmon_versions", profile, sample, f"{root}/versions.json", stage, True),
            ))
    for profile in profiles:
        for role in ("transcript_counts", "transcript_tpm", "transcript_effective_length",
                     "gene_counts", "gene_tpm", "gene_effective_length"):
            rows.append((f"matrix:{profile}:{role}", f"matrix_{role}", profile, None,
                         f"results/matrices/{profile}.{role}.tsv", StageId.MATRICES.value, True))
    multiqc = (
        "results/reports/multiqc/multiqc_report.html"
        if backend_contract
        else "results/nfcore/multiqc/star_salmon/multiqc_report.html"
    )
    rows.append(("multiqc", "multiqc_report", None, None, multiqc, StageId.NFCORE.value, not quant_only))
    rows.append(("run-report", "self_contained_report", profiles[0], None,
                 "results/reports/summary.html", StageId.REPORT.value, True))
    if len(profiles) == 2:
        for relative, role in (
            ("manifest.json", "concordance_manifest"), ("profile_comparison.tsv", "profile_comparison"),
            ("gene_method_sensitive.tsv", "gene_method_sensitive"),
            ("transcript_method_sensitive.tsv", "transcript_method_sensitive"),
            ("summary.html", "concordance_html"),
        ):
            rows.append((f"concordance:{role}", role, None, None, f"results/concordance/{relative}", StageId.CONCORDANCE.value, True))
    return rows


def discover_artifacts(run_dir: Path) -> tuple[ArtifactRecord, ...]:
    root = run_dir.resolve(strict=True)
    plan = _load(root, "frozen/plan.json")
    alignment_profile_id = str(plan.get("alignment_profile_id") or "") or None
    quant_only = plan.get("execution_route") == "fastq_quantification_only"
    not_applicable_roles = {"genomic_bam", "genomic_bai", "star_log_final", "star_junction",
                            "star_reads_per_gene", "star_selected_counts", "multiqc_report"}
    records = []
    for artifact_id, role, profile, sample, relative, stage, required in _expected(root):
        path = ensure_within(root / relative, root)
        state = (ArtifactState.NOT_APPLICABLE if quant_only and role in not_applicable_roles else
                 ArtifactState.PRESENT if path.is_file() and path.stat().st_size > 0 else ArtifactState.MISSING)
        records.append(ArtifactRecord(
            artifact_id, role, profile, sample, "RUN_DIR", relative, _media_type(path),
            path.stat().st_size if path.is_file() else None, stage, stage, required, state,
            alignment_profile_id=alignment_profile_id,
        ))
    return tuple(records)


def _media_type(path: Path) -> str:
    return {
        ".json": "application/json", ".html": "text/html", ".tsv": "text/tab-separated-values",
        ".sf": "text/tab-separated-values", ".bam": "application/x-bam", ".bai": "application/x-bai",
    }.get(path.suffix, "text/plain")


def _validate_matrix(path: Path) -> None:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle, delimiter="\t"))
    if len(rows) < 2 or len(rows[0]) < 2 or rows[0][0] != "feature_id":
        raise ValueError("Matrix schema is invalid")
    width = len(rows[0])
    features = [row[0] for row in rows[1:]]
    if len(features) != len(set(features)) or any(len(row) != width for row in rows[1:]):
        raise ValueError("Matrix feature IDs/width are invalid")
    for row in rows[1:]:
        if any(not math.isfinite(float(value)) or float(value) < 0 for value in row[1:]):
            raise ValueError("Matrix contains invalid values")


def _validate_report(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    lowered = text.lower()
    if "<html" not in lowered or "primary" not in lowered or "http://" in lowered or "https://" in lowered or "<script src=" in lowered:
        raise ValueError("Report is not self-contained or lacks primary identity")


def verify_artifacts(run_dir: Path, *, deep: bool = False, distribution: str = "Ubuntu",
                     runner: ProcessRunner | None = None,
                     progress: Callable[[str], None] | None = None) -> dict:
    root = run_dir.resolve(strict=True)
    run_manifest = root / "run.json"
    if run_manifest.is_file():
        frozen_context = str(_load(root, "run.json").get("identity", {}).get("execution_context") or "")
        execution = parse_execution_context(frozen_context)
    else:
        execution = parse_execution_context("wsl2", distribution=distribution)
    records = list(discover_artifacts(root))
    plan = _load(root, "frozen/plan.json")
    manifest_path = root / "results/backend-output-manifest.json"
    if manifest_path.is_file():
        validate_backend_output_manifest(
            root, workflow_backend_for_plan(plan).workflow_backend,
        )
    profile_contracts = dict(dict(plan.get("quantification") or {}).get("profiles") or {})
    by_id = {item.artifact_id: item for item in records}
    failures = []
    for index, record in enumerate(records):
        path = root / record.relative_path
        structural = "PASS"
        scientific = "NOT_APPLICABLE"
        state = record.state
        digest = None
        digest_status = "NOT_COMPUTED"
        if record.required and state is ArtifactState.MISSING:
            failures.append(f"missing:{record.artifact_id}")
        elif state is ArtifactState.PRESENT:
            try:
                if record.role in {"salmon_quant", "salmon_gene_quant"}:
                    parse_quant_sf(path.read_text(encoding="utf-8"))
                    scientific = "PASS"
                elif record.role == "salmon_meta":
                    meta = json.loads(path.read_text(encoding="utf-8"))
                    expected = profile_contracts[str(record.profile_id)]
                    detected_libraries = meta.get("library_types")
                    if (
                        meta.get("salmon_version") != expected["version"]
                        or not isinstance(detected_libraries, list)
                        or not detected_libraries
                        or not all(isinstance(item, str) and item for item in detected_libraries)
                    ):
                        raise ValueError("Salmon version/detected-library metadata mismatch")
                    processed, mapped = int(meta.get("num_processed", -1)), int(meta.get("num_mapped", -1))
                    if processed < 1 or mapped < 0 or mapped > processed or meta.get("quant_errors"):
                        raise ValueError("Salmon fragment accounting/meta output is invalid")
                    scientific = "PASS"
                elif record.role == "salmon_command":
                    command = json.loads(path.read_text(encoding="utf-8"))
                    expected = profile_contracts[str(record.profile_id)]
                    index_contract = dict(expected["index"])
                    runtime_image = dict(expected.get("runtime_image") or {})
                    expected_image = runtime_image.get("identity") or expected["image_identity"]
                    if command.get("profile_id") != record.profile_id or command.get("image_identity") != expected_image or command.get("index_id") != index_contract["index_id"]:
                        raise ValueError("Salmon command profile/image/index identity mismatch")
                    argv = list(command.get("structured_argv") or [])
                    if not argv or any(part in {"sh", "bash", "-c"} for part in argv):
                        raise ValueError("Salmon command is not structured")
                    expected_library = salmon_library_type_for_product(
                        str(plan["quantification"]["explicit_library_type"])
                    )
                    library_flags = [index for index, part in enumerate(argv) if part == "--libType"]
                    if (
                        len(library_flags) != 1
                        or library_flags[0] + 1 >= len(argv)
                        or argv[library_flags[0] + 1] != expected_library
                    ):
                        raise ValueError("Salmon command requested-library contract mismatch")
                    if expected.get("deterministic") and "--deterministic" not in argv:
                        raise ValueError("Deterministic profile command regressed")
                    scientific = "PASS"
                elif record.role == "salmon_input_manifest":
                    manifest = json.loads(path.read_text(encoding="utf-8"))
                    if not manifest.get("r1_sha256") or not manifest.get("r2_sha256") or int(manifest.get("paired_fragments", 0)) < 1:
                        raise ValueError("Processed FASTQ identity is incomplete")
                    scientific = "PASS"
                elif record.role == "salmon_versions":
                    versions = json.loads(path.read_text(encoding="utf-8"))
                    expected = profile_contracts[str(record.profile_id)]
                    runtime_image = dict(expected.get("runtime_image") or {})
                    expected_image = runtime_image.get("identity") or expected["image_identity"]
                    if versions.get("salmon") != expected["version"] or versions.get("image_identity") != expected_image:
                        raise ValueError("Salmon versions manifest mismatch")
                    scientific = "PASS"
                elif record.role == "star_reads_per_gene":
                    parse_reads_per_gene(path.read_text(encoding="utf-8"))
                    scientific = "PASS"
                elif record.role.startswith("matrix_"):
                    _validate_matrix(path)
                    scientific = "PASS"
                elif record.role in {"self_contained_report", "concordance_html"}:
                    _validate_report(path)
                elif record.role == "genomic_bam":
                    bai = root / by_id[f"bai:{record.sample}"].relative_path
                    bam_path, bai_path = str(path), str(bai)
                    if execution.is_wsl2:
                        try:
                            bam_path = unc_path_to_linux(bam_path, distribution=str(execution.distribution))
                            bai_path = unc_path_to_linux(bai_path, distribution=str(execution.distribution))
                        except ValueError:
                            pass
                    validator = resolve_frozen_bam_validator_contract(root)
                    validation = validate_bam(
                        bam=bam_path,
                        bai=bai_path,
                        execution=execution,
                        image_contract=validator.contract,
                        runner=runner,
                    )
                    if not validation.valid:
                        raise ValueError("BAM structural/scientific validation failed")
                    scientific = "PASS"
                if deep:
                    if progress:
                        progress(f"hashing {index + 1}/{len(records)} {record.relative_path}")
                    digest = sha256_path(path)
                    digest_status = "COMPLETE"
                state = ArtifactState.VALIDATED
            except (OSError, UnicodeError, ValueError, csv.Error) as exc:
                structural = f"FAIL:{exc}"
                state = ArtifactState.INVALID
                failures.append(f"invalid:{record.artifact_id}")
        records[index] = ArtifactRecord(**{
            **asdict(record), "state": state, "structural_validation": structural,
            "scientific_validation": scientific, "sha256_status": digest_status, "sha256": digest,
        })
    payload = {
        "schema_version": 1, "deep": deep, "complete": not failures,
        "failures": failures, "artifacts": [asdict(item) for item in records],
    }
    atomic_write_json(root / "artifacts/manifest.json", {"schema_version": 1, "artifacts": [asdict(item) for item in records]})
    atomic_write_json(root / "artifacts/verification.json", payload)
    return payload


def list_artifacts(run_dir: Path) -> dict:
    manifest = run_dir.resolve() / "artifacts/manifest.json"
    if manifest.is_file():
        return json.loads(manifest.read_text(encoding="utf-8"))
    return {"schema_version": 1, "artifacts": [asdict(item) for item in discover_artifacts(run_dir)]}
