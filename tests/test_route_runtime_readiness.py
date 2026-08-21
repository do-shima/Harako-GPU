from __future__ import annotations

import csv
import gzip
import hashlib
import json
import platform
from dataclasses import replace
from pathlib import Path

import pytest

from harako_gpu.adapters.execution_context import parse_execution_context
from harako_gpu.adapters.process import CommandResult, ProcessRunner
from harako_gpu.core.capabilities import BamOutputMode
from harako_gpu.core.contracts import BamRetention, MemoryMode
from harako_gpu.services.planning import create_plan
from harako_gpu.services.host_profiles import (
    UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
    runtime_quantification_image_contract,
)
from harako_gpu.services.run_preparation import (
    EXPECTED_IMAGES,
    IMAGE_CONTRACTS,
    PreparationContext,
    _prerequisite_applies,
    build_native_linux_preparation_context,
    prepare_run,
    runtime_requirements_for_plan,
    validate_offline_runtime_closure,
)


IS_GENUINE_NATIVE_LINUX = (
    platform.system() == "Linux"
    and "microsoft" not in platform.release().casefold()
)

native_linux_runtime = pytest.mark.skipif(
    not IS_GENUINE_NATIVE_LINUX,
    reason="requires genuine native Linux filesystem/process semantics",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _compatibility_plan(root: Path) -> Path:
    reads = root / "inputs"
    reads.mkdir()
    for name in ("WT_REP1_R1.fastq.gz", "WT_REP1_R2.fastq.gz"):
        with gzip.open(reads / name, "wt", encoding="ascii") as handle:
            handle.write("@read\nACGT\n+\nIIII\n")
    samplesheet = root / "samples.csv"
    with samplesheet.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("sample", "condition", "fastq_1", "fastq_2", "strandedness", "library_protocol"),
        )
        writer.writeheader()
        writer.writerow({
            "sample": "WT_REP1",
            "condition": "WT",
            "fastq_1": str(reads / "WT_REP1_R1.fastq.gz"),
            "fastq_2": str(reads / "WT_REP1_R2.fastq.gz"),
            "strandedness": "reverse",
            "library_protocol": "full_length",
        })
    fasta = root / "genome.fasta"
    transcripts = root / "transcriptome.fasta"
    gtf = root / "genes.gtf"
    fasta.write_text(">chr1\nACGT\n", encoding="utf-8")
    transcripts.write_text(">tx1\nACGT\n", encoding="utf-8")
    gtf.write_text(
        'chr1\ttest\texon\t1\t4\t.\t+\t.\tgene_id "g1"; transcript_id "tx1";\n',
        encoding="utf-8",
    )
    index = root / "salmon-1.10.3-index"
    index.mkdir()
    legacy_manifest = root / "legacy-index.json"
    legacy_manifest.write_text(json.dumps({"identity": {
        "salmon_index_id": "legacy-fixture-index",
        "index_path": str(index),
        "index_builder_version": "1.10.3",
        "index_builder_image_digest": EXPECTED_IMAGES["salmon_1_10_3_compatibility"],
        "transcript_fasta_sha256": _sha(transcripts),
        "genome_fasta_sha256": _sha(fasta),
        "decoys_sha256": "c" * 64,
        "index_parameters": ["-k", "31", "decoy_aware_gentrome"],
        "index_manifest_sha256": "d" * 64,
        "schema_version": 1,
    }}), encoding="utf-8")
    profile_manifest = root / "compatibility-profile-index.json"
    profile_manifest.write_text(json.dumps({
        "profile_id": "salmon_1_10_3_compatibility",
        "index_id": "salmon-1.10.3-fixture",
        "path": str(index),
        "builder_version": "1.10.3",
        "image_identity": EXPECTED_IMAGES["salmon_1_10_3_compatibility"],
        "transcript_source_sha256": _sha(transcripts),
        "genome_source_sha256": _sha(fasta),
        "gtf_sha256": _sha(gtf),
        "tx2gene_sha256": _sha(gtf),
        "manifest_sha256": "e" * 64,
    }), encoding="utf-8")
    create_plan(
        samplesheet=samplesheet,
        plan_dir=root / "plan",
        output_root=root / "runs",
        work_root=root / "work",
        fasta=fasta,
        gtf=gtf,
        transcript_fasta=transcripts,
        salmon_index_manifest=legacy_manifest,
        salmon_1_10_3_index_manifest=profile_manifest,
        quantification_mode="compatibility-only",
        bam_retention=BamRetention.NONE,
        bam_output_mode=BamOutputMode.NONE,
        alignment_profile_id="none",
        gpu_selection="all",
        memory_mode=MemoryMode.STANDARD,
        species="Homo sapiens",
        assembly="test-mini",
        annotation_provider="nf-core-test-datasets",
        annotation_release="626c8fab",
        project_slug="native-cpu-route",
        target="windows",
        explicit_library_type="ISR",
    )
    return root / "plan/plan.json"


def _context(
    root: Path,
    observed: dict[str, str],
    prerequisites: list[dict[str, object]] | None = None,
) -> PreparationContext:
    return PreparationContext(
        execution=parse_execution_context("native-linux"),
        pipeline_source_linux=str(root / "pipeline-not-required"),
        nextflow_executable="NOT_APPLICABLE",
        observed_image_ids=observed,
        hardware_report={
            "disk": {"free_bytes": 10 * 1024**3},
            "prerequisites": prerequisites or [],
        },
        repository_root=Path(__file__).resolve().parents[1],
        runner=ProcessRunner(),
    )


def _cpu_requirements(mode: str, primary: str) -> object:
    return runtime_requirements_for_plan({
        "execution_route": "fastq_quantification_only",
        "quantification": {"mode": mode, "primary_profile_id": primary},
    })


@pytest.mark.parametrize(("mode", "primary", "expected"), (
    ("compatibility_only", "salmon_1_10_3_compatibility", {
        "fastp", "salmon_1_10_3_compatibility",
    }),
    ("recommended_only", "salmon_2_5_1_deterministic", {
        "fastp", "salmon_2_5_1_deterministic",
    }),
    ("compare_both", "salmon_2_5_1_deterministic", {
        "fastp", "salmon_1_10_3_compatibility", "salmon_2_5_1_deterministic",
    }),
))
def test_cpu_route_requires_only_fastp_and_selected_salmon_images(
    mode: str, primary: str, expected: set[str],
) -> None:
    requirements = _cpu_requirements(mode, primary)
    assert set(requirements.required_image_roles) == expected
    assert requirements.requires_gpu is False
    assert requirements.requires_java is False
    assert requirements.requires_nextflow is False
    assert requirements.requires_nfcore_pipeline is False
    assert requirements.requires_star_index is False
    assert requirements.requires_bam_validation is False


def test_gpu_route_retains_parabricks_gpu_java_nextflow_pipeline_and_bam_gates() -> None:
    requirements = runtime_requirements_for_plan({
        "execution_route": "gpu_bam_alignment",
        "quantification": {
            "mode": "recommended_only",
            "primary_profile_id": "salmon_2_5_1_deterministic",
        },
    })
    assert set(requirements.required_image_roles) == {
        "parabricks", "fastp", "salmon_2_5_1_deterministic",
    }
    assert requirements.requires_gpu
    assert requirements.requires_java
    assert requirements.requires_nextflow
    assert requirements.requires_nfcore_pipeline
    assert requirements.requires_star_index
    assert requirements.requires_bam_validation
    for code in (
        "PARABRICKS_IMAGE_UNAVAILABLE", "GPU_UNAVAILABLE", "JAVA_NOT_FOUND", "NEXTFLOW_NOT_FOUND",
    ):
        assert _prerequisite_applies(code, requirements)


@native_linux_runtime
def test_cpu_compatibility_prepare_ignores_unrelated_generic_runtime_blockers(tmp_path: Path) -> None:
    plan = _compatibility_plan(tmp_path)
    context = _context(
        tmp_path,
        {
            "fastp": EXPECTED_IMAGES["fastp"],
            "salmon_1_10_3_compatibility": EXPECTED_IMAGES["salmon_1_10_3_compatibility"],
        },
        [
            {"code": "PARABRICKS_IMAGE_UNAVAILABLE", "severity": "hard_blocker", "active": True},
            {"code": "GPU_UNAVAILABLE", "severity": "hard_blocker", "active": True},
            {"code": "JAVA_NOT_FOUND", "severity": "hard_blocker", "active": True},
            {"code": "NEXTFLOW_NOT_FOUND", "severity": "hard_blocker", "active": True},
        ],
    )

    prepared = prepare_run(plan_path=plan, runtime_root=str(tmp_path), context=context)

    assert prepared.run_dir.is_dir()
    assert not (prepared.run_dir / "pipeline/nf-core-rnaseq-3.26.0").exists()
    frozen = json.loads((prepared.run_dir / "frozen/runtime-requirements.json").read_text())
    assert set(frozen["required_image_roles"]) == {"fastp", "salmon_1_10_3_compatibility"}
    assert frozen["image_contracts"]["fastp"] == {
        "role": "fastp",
        "image_reference": IMAGE_CONTRACTS["fastp"].reference,
        "identity_kind": "repo_digest",
        "expected_identity": EXPECTED_IMAGES["fastp"],
        "observed_canonical_identity": EXPECTED_IMAGES["fastp"],
    }
    assert set(frozen["not_applicable_findings"]) == {
        "PARABRICKS_IMAGE_UNAVAILABLE", "GPU_UNAVAILABLE", "JAVA_NOT_FOUND", "NEXTFLOW_NOT_FOUND",
    }
    pipeline = json.loads((prepared.run_dir / "frozen/pipeline-manifest.json").read_text())
    assert pipeline["commit"] == "NOT_APPLICABLE"


@pytest.mark.parametrize("missing_role", ("fastp", "salmon_1_10_3_compatibility"))
@native_linux_runtime
def test_cpu_compatibility_prepare_rejects_each_missing_required_image(
    tmp_path: Path, missing_role: str,
) -> None:
    plan = _compatibility_plan(tmp_path)
    observed = {
        "fastp": EXPECTED_IMAGES["fastp"],
        "salmon_1_10_3_compatibility": EXPECTED_IMAGES["salmon_1_10_3_compatibility"],
    }
    del observed[missing_role]
    with pytest.raises(ValueError, match=f"unavailable: {missing_role}"):
        prepare_run(plan_path=plan, runtime_root=str(tmp_path), context=_context(tmp_path, observed))


@native_linux_runtime
def test_cpu_compatibility_prepare_rejects_required_image_identity_mismatch(tmp_path: Path) -> None:
    plan = _compatibility_plan(tmp_path)
    observed = {
        "fastp": EXPECTED_IMAGES["fastp"],
        "salmon_1_10_3_compatibility": "sha256:" + "0" * 64,
    }
    with pytest.raises(ValueError, match="identity mismatch: salmon_1_10_3_compatibility"):
        prepare_run(plan_path=plan, runtime_root=str(tmp_path), context=_context(tmp_path, observed))


class _ImageRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...], **_kwargs: object) -> CommandResult:
        command = tuple(argv)
        self.calls.append(command)
        image = command[-1]
        role = next(role for role in ("fastp", "salmon_1_10_3_compatibility")
                    if IMAGE_CONTRACTS[role].execution_reference == image)
        contract = IMAGE_CONTRACTS[role]
        return CommandResult(command, 0, json.dumps([{
            "Id": "sha256:" + "f" * 64,
            "RepoDigests": [f"{contract.repository}@{contract.identity}"],
        }]), "")


def test_native_cpu_context_inspects_only_route_images_without_nextflow() -> None:
    runner = _ImageRunner()
    requirements = _cpu_requirements("compatibility_only", "salmon_1_10_3_compatibility")
    context = build_native_linux_preparation_context(
        runtime_root="/runtime",
        nextflow_executable="/missing-nextflow",
        runner=runner,
        host_system="Linux",
        kernel_release="fixture",
        hardware_report={"schema_version": 1},
        requirements=requirements,
    )
    assert context.nextflow_executable == "NOT_APPLICABLE"
    assert set(context.observed_image_ids) == {"fastp", "salmon_1_10_3_compatibility"}
    assert len(runner.calls) == 2
    assert all("wsl.exe" not in call and "-version" not in call for call in runner.calls)


class _UbuntuComparisonImageRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...], **_kwargs: object) -> CommandResult:
        command = tuple(argv)
        self.calls.append(command)
        image = command[-1]
        contracts = {
            "fastp": IMAGE_CONTRACTS["fastp"],
            "salmon_1_10_3_compatibility": IMAGE_CONTRACTS["salmon_1_10_3_compatibility"],
            "salmon_2_5_1_deterministic": runtime_quantification_image_contract(
                UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID, "salmon_2_5_1_deterministic",
            ),
        }
        contract = next(
            value for value in contracts.values()
            if value and (
                value.execution_reference if value.identity_kind == "repo_digest" else value.reference
            ) == image
        )
        payload = {"Id": contract.identity if contract.identity_kind == "image_id" else "sha256:" + "f" * 64}
        if contract.identity_kind == "repo_digest":
            payload["RepoDigests"] = [f"{contract.repository}@{contract.identity}"]
        return CommandResult(command, 0, json.dumps([payload]), "")


def test_native_ubuntu_compare_both_uses_frozen_runtime_salmon_overlay() -> None:
    runner = _UbuntuComparisonImageRunner()
    requirements = replace(
        _cpu_requirements("compare_both", "salmon_2_5_1_deterministic"),
        host_profile_id=UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
    )

    context = build_native_linux_preparation_context(
        runtime_root="/runtime",
        nextflow_executable="/missing-nextflow",
        runner=runner,
        host_system="Linux",
        kernel_release="fixture",
        hardware_report={"schema_version": 1},
        requirements=requirements,
    )

    overlay = runtime_quantification_image_contract(
        UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID, "salmon_2_5_1_deterministic",
    )
    assert overlay is not None
    assert context.observed_image_ids == {
        "fastp": IMAGE_CONTRACTS["fastp"].identity,
        "salmon_1_10_3_compatibility": IMAGE_CONTRACTS["salmon_1_10_3_compatibility"].identity,
        "salmon_2_5_1_deterministic": overlay.identity,
    }
    assert any(overlay.reference in call for call in runner.calls)
    assert validate_offline_runtime_closure(requirements, context)[
        "salmon_2_5_1_deterministic"
    ] == overlay.identity
