from __future__ import annotations

import json
import csv
import hashlib
from pathlib import Path

from typer.testing import CliRunner

from harako_gpu.commands.root import app
from harako_gpu.core.contracts import (
    HardwareReport, NextflowVersionStatus, PrerequisiteFinding, PrerequisiteSeverity,
    ProbeStatus, QualificationStatus,
)


RUNNER = CliRunner()


def hardware_report(**_kwargs) -> HardwareReport:
    absent = ProbeStatus(False, "not_present", "fixture")
    return HardwareReport(
        os="Linux", execution_context="native_linux", wsl_status={"status": "not_applicable"},
        cpu={"logical_count": 8}, host_ram_bytes=16, disk={"free_bytes": 10}, nvidia_gpus=(),
        driver_version=None, nvidia_smi=absent, docker=absent, docker_gpu_runtime=absent,
        docker_gpu_access=absent,
        java=absent, nextflow=absent, nf_core=absent, parabricks_image=absent,
        cuda_test_image=absent, minimum_nextflow_version="25.04.3",
        qualified_nextflow_version="25.04.3", detected_nextflow_version=None,
        nextflow_version_status=NextflowVersionStatus.NEXTFLOW_NOT_FOUND,
        prerequisites=(PrerequisiteFinding("NEXTFLOW_NOT_FOUND", PrerequisiteSeverity.HARD_BLOCKER, True, "fixture"),),
        qualification_status=QualificationStatus.BLOCKED,
        python={"version": "3.12"}, support_details={"replacement_character": "\ufffd"},
    )


def test_version() -> None:
    result = RUNNER.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "0.1.0a1"


def test_restricted_help_surface() -> None:
    result = RUNNER.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("doctor", "inspect", "plan", "contract", "profiles", "concordance", "star-counts", "ui"):
        assert command in result.stdout
    for forbidden in ("run", "resume", "finalize", "archive", "delete-bam", "report"):
        assert f"| {forbidden} " not in result.stdout


def test_documented_command_help_smoke() -> None:
    for argv in (["doctor", "--help"], ["inspect", "--help"], ["plan", "--help"], ["contract", "--help"],
                 ["profiles", "--help"], ["concordance", "--help"], ["star-counts", "--help"], ["ui", "--help"]):
        result = RUNNER.invoke(app, argv)
        assert result.exit_code == 0, result.stdout


def test_profile_catalog_cli_is_json_and_hidden_profile_is_rejected() -> None:
    result = RUNNER.invoke(app, ["profiles", "list", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload["profiles"]) == 2
    hidden = RUNNER.invoke(app, ["profiles", "show", "salmon_1_12_1_rejected_hidden", "--json"])
    assert hidden.exit_code != 0


def test_doctor_json_is_parseable(monkeypatch) -> None:
    monkeypatch.setattr("harako_gpu.commands.doctor.collect_preflight", hardware_report)
    result = RUNNER.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["qualification_status"] == "BLOCKED"
    assert payload["support_details"]["replacement_character"] == "\ufffd"


def test_inspect_json_is_parseable(tmp_path: Path) -> None:
    (tmp_path / "S1_R1.fastq.gz").write_bytes(b"fixture")
    result = RUNNER.invoke(app, ["inspect", str(tmp_path)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["total_fastq_count"] == 1


def test_contract_show_json_is_parseable() -> None:
    result = RUNNER.invoke(app, ["contract", "show"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["bam_deletion_implemented"] is False


def test_plan_create_and_validate_cli_smoke(tmp_path: Path) -> None:
    reads = tmp_path / "reads"
    reads.mkdir()
    for name in ("A_R1.fastq.gz", "A_R2.fastq.gz", "B_R1.fastq.gz", "B_R2.fastq.gz"):
        (reads / name).write_bytes(b"fixture")
    samplesheet = tmp_path / "samples.csv"
    with samplesheet.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sample", "condition", "fastq_1", "fastq_2", "strandedness", "library_protocol"])
        writer.writeheader()
        writer.writerow({"sample": "A", "condition": "control", "fastq_1": str(reads / "A_R1.fastq.gz"), "fastq_2": str(reads / "A_R2.fastq.gz"), "strandedness": "auto", "library_protocol": "full_length"})
        writer.writerow({"sample": "B", "condition": "treated", "fastq_1": str(reads / "B_R1.fastq.gz"), "fastq_2": str(reads / "B_R2.fastq.gz"), "strandedness": "auto", "library_protocol": "full_length"})
    fasta = tmp_path / "genome.fa"
    gtf = tmp_path / "genes.gtf"
    fasta.write_text(">chr1\nACGT\n", encoding="utf-8")
    gtf.write_text("chr1\ttest\texon\t1\t4\t.\t+\t.\tgene_id \"g1\";\n", encoding="utf-8")
    transcript_fasta = tmp_path / "transcripts.fa"
    transcript_fasta.write_text(">tx1\nACGT\n", encoding="utf-8")
    index = tmp_path / "salmon-index"
    index.mkdir()
    index_manifest = tmp_path / "salmon-index-manifest.json"
    index_manifest.write_text(json.dumps({"identity": {
        "salmon_index_id": "fixture-index", "index_path": str(index),
        "index_builder_version": "1.10.3",
        "index_builder_image_digest": "sha256:f83ebb158845ee8138d793347f83b92c75e83c58dd8f4600c6fea2a2453ef08e",
        "transcript_fasta_sha256": hashlib.sha256(transcript_fasta.read_bytes()).hexdigest(),
        "genome_fasta_sha256": hashlib.sha256(fasta.read_bytes()).hexdigest(),
        "decoys_sha256": "c" * 64,
        "index_parameters": ["-k", "31", "decoy_aware_gentrome"],
        "index_manifest_sha256": "d" * 64, "schema_version": 1,
    }}), encoding="utf-8")
    profile_index_manifest = tmp_path / "salmon-2.5.1-profile-index.json"
    profile_index_manifest.write_text(json.dumps({
        "profile_id": "salmon_2_5_1_deterministic",
        "index_id": "salmon-2.5.1-fixture",
        "path": str(index),
        "builder_version": "2.5.1",
        "image_identity": "sha256:e6e64f39a479458ef6f007757498321ee5a3ef8a2227ff2af414fbe3c36e6f7f",
        "transcript_source_sha256": hashlib.sha256(transcript_fasta.read_bytes()).hexdigest(),
        "genome_source_sha256": hashlib.sha256(fasta.read_bytes()).hexdigest(),
        "gtf_sha256": hashlib.sha256(gtf.read_bytes()).hexdigest(),
        "tx2gene_sha256": "e" * 64,
        "manifest_sha256": "f" * 64,
    }), encoding="utf-8")
    plan_dir = tmp_path / "plan"
    result = RUNNER.invoke(app, [
        "plan", "create", "--samplesheet", str(samplesheet), "--plan-dir", str(plan_dir),
        "--output-root", str(tmp_path / "out"), "--work-root", str(tmp_path / "work"),
        "--fasta", str(fasta), "--gtf", str(gtf), "--bam-retention", "keep",
        "--transcript-fasta", str(transcript_fasta),
        "--salmon-index-manifest", str(index_manifest),
        "--salmon-2-5-1-index-manifest", str(profile_index_manifest),
        "--gpu-selection", "all", "--memory-mode", "standard", "--species", "mouse",
        "--assembly", "GRCm39", "--annotation-provider", "Ensembl",
        "--annotation-release", "113", "--project-slug", "cli-smoke", "--target", "windows",
    ])
    assert result.exit_code == 0, result.stdout
    created = json.loads(result.stdout)
    assert created["executed"] is False
    validation = RUNNER.invoke(app, ["plan", "validate", str(plan_dir / "plan.json")])
    assert validation.exit_code == 0, validation.stdout
    assert json.loads(validation.stdout)["valid"] is True
