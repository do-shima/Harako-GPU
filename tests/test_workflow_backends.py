from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner
from typer.main import get_command

from harako_gpu.commands.root import app
from harako_gpu.services.backend_outputs import (
    ALIGNMENT_FILENAMES,
    GLOBAL_FILENAMES,
    NATIVE_COMMAND_FILENAMES,
    SUPPORT_FILENAMES,
    update_backend_output_manifest,
    validate_backend_output_manifest,
)
from harako_gpu.services.host_profiles import (
    FULL_HUMAN_REFERENCE_PACK_ID,
    ONE_PASS_RESOURCE_CONTRACT_ID,
    TWO_PASS_RESOURCE_CONTRACT_ID,
    UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
    PARABRICKS_CONFIG_IMAGE_ID,
)
from harako_gpu.services.run_preparation import (
    _alignment_params,
    _execution_config,
    _nextflow_argv,
    runtime_requirements_for_plan,
)
from harako_gpu.services.run_execution import _copy_alignment_artifacts, _resume_nextflow_argv
from harako_gpu.services.workflow_backends import (
    AlignmentBackend,
    HARAKO_NATIVE_V1,
    HISTORICAL_MISSING_WORKFLOW_BACKEND,
    NFCORE_REFERENCE,
    default_workflow_backend_for_new_plan,
    parse_workflow_backend,
    validate_backend_alignment,
    workflow_backend_for_plan,
)


def _runtime_plan(profile: str = "salmon_2_5_1_deterministic") -> dict:
    return {
        "workflow_backend": HARAKO_NATIVE_V1,
        "execution_route": "gpu_bam_alignment",
        "quantification": {
            "mode": "recommended_only",
            "primary_profile_id": profile,
            "secondary_profile_id": None,
        },
        "capability_snapshot": {"result": {"host_profile_id": UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID}},
    }


def _resource_plan(profile_id: str, contract_id: str) -> dict:
    return {
        "workflow_backend": HARAKO_NATIVE_V1,
        "backend_profile": {"gpu_selection": "all", "qualification_debug_mode": "disabled"},
        "quantification": {"qualification_resource_contract": contract_id},
        "capability_snapshot": {"result": {
            "host_profile_id": UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
            "reference_pack_id": FULL_HUMAN_REFERENCE_PACK_ID,
        }},
        "alignment_profile_id": profile_id,
    }


def test_fixed_backend_and_alignment_catalog() -> None:
    assert parse_workflow_backend("harako-native-v1").workflow_backend == HARAKO_NATIVE_V1
    assert parse_workflow_backend("nfcore-rnaseq-3-26-reference").workflow_backend == NFCORE_REFERENCE
    assert workflow_backend_for_plan({}).workflow_backend == NFCORE_REFERENCE
    assert HISTORICAL_MISSING_WORKFLOW_BACKEND == NFCORE_REFERENCE
    assert parse_workflow_backend("harako-native-v1").qualification_state == (
        "AVAILABLE_QUALIFIED_UBUNTU_HIGH_MEMORY"
    )
    with pytest.raises(ValueError, match="NOT_QUALIFIED"):
        validate_backend_alignment(HARAKO_NATIVE_V1, AlignmentBackend.STAR_CPU.value)


def test_new_plan_default_is_host_receipt_and_parity_evidence_gated(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    qualified = default_workflow_backend_for_new_plan(
        requested=None,
        target="linux",
        host_profile_id=UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
        host_receipt_validated=True,
        qualification_report_root=repository / "docs/qualification",
    )
    assert qualified.workflow_backend == HARAKO_NATIVE_V1

    for changes in (
        {"host_receipt_validated": False},
        {"target": "wsl"},
        {"host_profile_id": "windows_wsl2_rtx3090_ram64_v1"},
        {"qualification_report_root": tmp_path},
    ):
        values = {
            "requested": None,
            "target": "linux",
            "host_profile_id": UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
            "host_receipt_validated": True,
            "qualification_report_root": repository / "docs/qualification",
        }
        values.update(changes)
        assert default_workflow_backend_for_new_plan(**values).workflow_backend == NFCORE_REFERENCE

    explicit = default_workflow_backend_for_new_plan(
        requested="nfcore-rnaseq-3-26-reference",
        target="linux",
        host_profile_id=UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
        host_receipt_validated=True,
        qualification_report_root=repository / "docs/qualification",
    )
    assert explicit.workflow_backend == NFCORE_REFERENCE


def test_harako_native_runtime_is_minimal_and_has_no_nf_schema() -> None:
    requirements = runtime_requirements_for_plan(_runtime_plan())
    assert requirements.required_image_roles == (
        "parabricks", "fastp", "samtools", "subread_featurecounts", "multiqc",
        "salmon_2_5_1_deterministic",
    )
    assert requirements.requires_nfcore_pipeline is False
    assert requirements.requires_nf_schema is False
    assert requirements.requires_nextflow is True
    assert len(requirements.required_image_roles) == 6


@pytest.mark.parametrize(("profile_id", "contract_id", "memory"), (
    ("parabricks_star_one_pass_workstation", ONE_PASS_RESOURCE_CONTRACT_ID, "memory = 42.GB"),
    ("parabricks_star_two_pass_high_memory", TWO_PASS_RESOURCE_CONTRACT_ID, "memory = 96.GB"),
))
def test_native_resource_contract_applies_only_to_parabricks(
    profile_id: str, contract_id: str, memory: str,
) -> None:
    config = _execution_config(_resource_plan(profile_id, contract_id))
    assert "withName: 'PARABRICKS_RNA_FQ2BAM'" in config
    assert memory in config
    assert "cpus = 12" in config
    assert config.count("memory =") == 1
    assert "NFCORE_RNASEQ" not in config


def test_native_nextflow_argv_does_not_request_nfcore_docker_profile() -> None:
    native = _nextflow_argv(
        executable="nextflow", pipeline="/pipeline", run_dir="/run",
        work_dir="/work", run_id="n1", profile=None,
    )
    reference = _nextflow_argv(
        executable="nextflow", pipeline="/pipeline", run_dir="/run",
        work_dir="/work", run_id="r1",
    )
    assert "-profile" not in native
    assert reference[3:5] == ("-profile", "docker")


def test_nextflow_resume_targets_frozen_run_name_without_redeclaring_it() -> None:
    frozen = (
        "nextflow", "run", "/pipeline", "-name", "h-immutable-run",
        "-work-dir", "/work",
        "-with-report", "/run/execution/current-report.html",
        "-with-timeline", "/run/execution/current-timeline.html",
        "-with-trace", "/run/execution/current-trace.tsv",
        "-with-dag", "/run/execution/current-dag.html",
    )

    resumed = _resume_nextflow_argv(frozen, "/run/execution/attempts/0002")

    assert resumed == (
        "nextflow", "run", "/pipeline", "-work-dir", "/work",
        "-with-report", "/run/execution/attempts/0002/report.html",
        "-with-timeline", "/run/execution/attempts/0002/timeline.html",
        "-with-trace", "/run/execution/attempts/0002/trace.tsv",
        "-with-dag", "/run/execution/attempts/0002/dag.html",
        "-resume", "h-immutable-run",
    )
    assert "-name" not in resumed


def test_native_frozen_params_use_only_immutable_execution_images() -> None:
    plan = {
        **_resource_plan(
            "parabricks_star_one_pass_workstation", ONE_PASS_RESOURCE_CONTRACT_ID,
        ),
        "execution_route": "gpu_bam_alignment",
        "reference": {
            "assembly": "GRCh38.p14",
            "annotation_provider": "GENCODE",
            "annotation_release": "49",
            "reference_pack_id": FULL_HUMAN_REFERENCE_PACK_ID,
            "fasta_path": "/reference/genome.fa",
            "gtf_path": "/reference/genes.gtf",
        },
        "quantification": {
            "mode": "recommended_only",
            "primary_profile_id": "salmon_2_5_1_deterministic",
            "secondary_profile_id": None,
            "explicit_library_type": "ISR",
            "parabricks_star_sjdb_overhang": 74,
            "parabricks_star_index": "/reference/star",
            "qualification_resource_contract": ONE_PASS_RESOURCE_CONTRACT_ID,
        },
    }
    params = _alignment_params(plan, {}, run_dir="/runtime/run", work_dir="/runtime/work")
    assert set(params["images"]) == {
        "fastp", "parabricks", "samtools", "subread_featurecounts", "multiqc",
    }
    assert all(
        value.startswith("sha256:") or "@sha256:" in value
        for value in params["images"].values()
    )
    assert params["parabricks_extra_args"].endswith("--two-pass-mode None")
    assert params["images"]["parabricks"] == PARABRICKS_CONFIG_IMAGE_ID


def test_pipeline_has_fixed_dag_without_plugin_salmon_or_online_fetch() -> None:
    root = Path(__file__).resolve().parents[1] / "pipelines/harako-native-v1"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.nf"))
    config = (root / "nextflow.config").read_text(encoding="utf-8")
    assert all(name in text for name in (
        "FASTP", "PARABRICKS_RNA_FQ2BAM", "PUBLISH_ALIGNMENT_CONTRACT",
        "FEATURECOUNTS_BIOTYPE_QC", "MULTIQC",
    ))
    assert "salmon" not in text.casefold()
    assert "nf-schema" not in (text + config).casefold()
    assert "docker.pullPolicy = 'never'" in config
    assert "--low-memory --quantMode TranscriptomeSAM GeneCounts" in text
    assert all(f"container params.images.{role}" in text for role in (
        "fastp", "parabricks", "samtools", "subread_featurecounts", "multiqc",
    ))
    assert "container 'nvcr.io" not in text
    assert "container 'quay.io" not in text
    assert "${params.parabricks_extra_args}" in text
    assert "samtools index" not in text
    publication = (root / "modules/local/publish_alignment_contract.nf").read_text(
        encoding="utf-8",
    )
    assert "path(star_log)" in publication
    assert "path(log)" not in publication
    assert "cp --" not in publication
    assert "samtools quickcheck" in publication
    assert "-t ${params.featurecounts_feature_type}" in text
    assert "-g ${params.featurecounts_group_type}" in text
    assert "-B -C -p" in text
    assert "-s ${strandedness}" in text
    assert "-T 6" in text
    multiqc = (root / "modules/local/multiqc.nf").read_text(encoding="utf-8")
    assert "path 'multiqc_report_data'" in multiqc
    assert "path 'multiqc_data'" not in multiqc


def test_backend_output_manifest_is_explicit_and_identity_checked(tmp_path: Path) -> None:
    artifacts = {}
    root = tmp_path / "results/alignment/A"
    root.mkdir(parents=True)
    for role, template in ALIGNMENT_FILENAMES.items():
        path = root / template.format(sample="A")
        path.write_bytes((role + "\n").encode())
        artifacts[role] = path
    for role, template in SUPPORT_FILENAMES.items():
        path = tmp_path / "results" / template.format(sample="A")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((role + "\n").encode())
    for role, template in NATIVE_COMMAND_FILENAMES.items():
        path = tmp_path / "results" / template.format(sample="A")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((role + "\n").encode())
    for role, relative in GLOBAL_FILENAMES.items():
        path = tmp_path / "results" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((role + "\n").encode())
    manifest = update_backend_output_manifest(
        tmp_path, workflow_backend=HARAKO_NATIVE_V1, sample="A", artifacts=artifacts,
    )
    payload = validate_backend_output_manifest(tmp_path, HARAKO_NATIVE_V1)
    assert manifest == tmp_path / "results/backend-output-manifest.json"
    assert len(payload["artifacts"]) == 13
    assert {item["role"] for item in payload["artifacts"]} == {
        *ALIGNMENT_FILENAMES, *SUPPORT_FILENAMES, *NATIVE_COMMAND_FILENAMES,
        *GLOBAL_FILENAMES,
    }
    artifacts["bam"].write_bytes(b"tampered")
    with pytest.raises(ValueError, match="identity mismatch"):
        validate_backend_output_manifest(tmp_path, HARAKO_NATIVE_V1)


def test_reference_backend_normalizes_exact_paths_without_recursive_discovery(tmp_path: Path) -> None:
    sample = "A"
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    (frozen / "plan.json").write_text(json.dumps({
        "workflow_backend": NFCORE_REFERENCE,
    }), encoding="utf-8")
    source = tmp_path / "results/nfcore/star_salmon"
    for relative in (
        f"{sample}.sorted.bam", f"{sample}.sorted.bam.bai",
        f"{sample}.Aligned.toTranscriptome.out.bam",
        f"log/{sample}.Log.final.out", f"log/{sample}.SJ.out.tab",
        f"log/{sample}.ReadsPerGene.out.tab",
        f"featurecounts/{sample}.featureCounts.tsv",
    ):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((relative + "\n").encode())
    for name in (
        f"{sample}_R1.fastp.fastq.gz", f"{sample}_R2.fastp.fastq.gz",
        f"{sample}.fastp.json", f"{sample}.fastp.html",
    ):
        path = tmp_path / "results/nfcore/fastp" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((name + "\n").encode())
    multiqc = tmp_path / "results/nfcore/multiqc/star_salmon/multiqc_report.html"
    multiqc.parent.mkdir(parents=True)
    multiqc.write_text("report\n", encoding="utf-8")

    artifacts = _copy_alignment_artifacts(tmp_path, sample)

    assert artifacts["star_log"] == tmp_path / f"results/alignment/{sample}/{sample}.Log.final.out"
    payload = validate_backend_output_manifest(tmp_path, NFCORE_REFERENCE)
    assert len(payload["artifacts"]) == 12
    assert (tmp_path / f"results/preprocessing/fastp/{sample}_R1.fastp.fastq.gz").is_file()
    assert (tmp_path / f"results/qc/featurecounts/{sample}.featureCounts.txt").is_file()
    assert (tmp_path / "results/reports/multiqc/multiqc_report.html").is_file()


def test_public_cli_exposes_host_aware_backend_default() -> None:
    runner = CliRunner()
    command = get_command(app).commands["plan"].commands["create"]
    workflow_option = next(item for item in command.params if item.name == "workflow_backend")
    assert "--workflow-backend" in workflow_option.opts
    assert workflow_option.default is None
    result = runner.invoke(app, ["capabilities", "inspect", "--json", "--workflow-backend", "harako-native-v1"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["workflow_backend"] == HARAKO_NATIVE_V1
    assert payload["workflow_backend_qualification_state"] == (
        "AVAILABLE_QUALIFIED_UBUNTU_HIGH_MEMORY"
    )
