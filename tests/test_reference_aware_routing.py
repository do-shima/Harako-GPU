from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from harako_gpu.commands.root import app
from harako_gpu.core.capabilities import BamOutputMode, CapabilityStatus, ExecutionRoute, ReferenceResourceClass
from harako_gpu.core.contracts import BamRetention, MemoryMode, qualified_backend_profile
from harako_gpu.services.artifacts import discover_artifacts
from harako_gpu.services.capabilities import (
    FULL_HUMAN_REFERENCE_PACK_ID, FULL_HUMAN_SHA, SMALL_REFERENCE_PACK_ID, SMALL_REFERENCE_SHA, capability_matrix,
    classify_reference, evaluate_capability, high_memory_handoff,
)
from harako_gpu.services.run_preparation import FASTP_IMAGE_IDENTITY, FASTP_IMAGE_REFERENCE
from harako_gpu.adapters.filesystem import atomic_write_text


HUMAN = {**FULL_HUMAN_SHA, "reference_pack_id": FULL_HUMAN_REFERENCE_PACK_ID}
SMALL = {**SMALL_REFERENCE_SHA, "reference_pack_id": SMALL_REFERENCE_PACK_ID,
         "assembly": "test-mini", "annotation_provider": "nf-core-test-datasets"}


def evaluate(reference: dict, bam: BamOutputMode, alignment: str | None = None,
             secondary: str | None = None, runtime_qualified: bool | None = None):
    return evaluate_capability(reference=reference, bam_output_mode=bam,
        alignment_profile_id=alignment, quantification_mode="compare_both" if secondary else "recommended_only",
        primary_profile_id="salmon_2_5_1_deterministic", secondary_profile_id=secondary,
        runtime_qualified=runtime_qualified)


def test_exact_human_reference_classification() -> None:
    value = classify_reference(HUMAN)
    assert value.reference_pack_id == FULL_HUMAN_REFERENCE_PACK_ID
    assert value.resource_class is ReferenceResourceClass.FULL_MAMMALIAN_HIGH_MEMORY


def test_species_label_alone_does_not_classify_reference() -> None:
    assert classify_reference({"species": "Homo sapiens"}).resource_class is ReferenceResourceClass.CUSTOM_UNQUALIFIED


def test_small_reference_labels_without_exact_assets_are_not_qualified() -> None:
    reference = {"assembly": "test-mini", "annotation_provider": "nf-core-test-datasets"}
    assert classify_reference(reference).resource_class is ReferenceResourceClass.CUSTOM_UNQUALIFIED


@pytest.mark.parametrize("profile", ["parabricks_star_one_pass_workstation", "parabricks_star_two_pass_high_memory"])
def test_human_bam_is_blocked_by_observed_host_memory(profile: str) -> None:
    result = evaluate(HUMAN, BamOutputMode.KEEP, profile)
    assert result.status is CapabilityStatus.UNSUPPORTED_HOST_MEMORY
    assert result.gpu_used and result.bam_generated


def test_discard_after_validation_still_requires_bam() -> None:
    result = evaluate(HUMAN, BamOutputMode.DISCARD_AFTER_VALIDATION, "parabricks_star_one_pass_workstation")
    assert result.status is CapabilityStatus.UNSUPPORTED_HOST_MEMORY
    assert result.requested_route is ExecutionRoute.GPU_BAM_ALIGNMENT


def test_human_quantification_route_starts_as_candidate() -> None:
    result = evaluate(HUMAN, BamOutputMode.NONE, runtime_qualified=False)
    assert result.status is CapabilityStatus.CANDIDATE_REQUIRES_RUNTIME_QUALIFICATION
    assert not result.gpu_used and not result.bam_generated


def test_quantification_route_rejects_alignment_profile() -> None:
    result = evaluate(HUMAN, BamOutputMode.NONE, "parabricks_star_one_pass_workstation")
    assert result.status is CapabilityStatus.BLOCKED_IDENTITY_MISMATCH


@pytest.mark.parametrize("profile", ["parabricks_star_one_pass_workstation", "parabricks_star_two_pass_high_memory"])
def test_small_reference_gpu_bam_remains_available(profile: str) -> None:
    assert evaluate(SMALL, BamOutputMode.KEEP, profile).status is CapabilityStatus.AVAILABLE_QUALIFIED


def test_runtime_qualification_promotes_cpu_route_only() -> None:
    result = evaluate_capability(reference=HUMAN, bam_output_mode=BamOutputMode.NONE,
        alignment_profile_id=None, quantification_mode="recommended_only",
        primary_profile_id="salmon_2_5_1_deterministic", secondary_profile_id=None,
        runtime_qualified=True)
    assert result.status is CapabilityStatus.AVAILABLE_QUALIFIED
    assert not result.gpu_used


def test_compare_both_promotion_retains_limitation() -> None:
    result = evaluate_capability(reference=HUMAN, bam_output_mode=BamOutputMode.NONE,
        alignment_profile_id=None, quantification_mode="compare_both",
        primary_profile_id="salmon_2_5_1_deterministic",
        secondary_profile_id="salmon_1_10_3_compatibility", runtime_qualified=True)
    assert result.status is CapabilityStatus.AVAILABLE_WITH_LIMITATION


def test_quantification_backend_explicitly_disables_gpu_alignment() -> None:
    profile = qualified_backend_profile(bam_retention=BamRetention.NONE, gpu_selection="all",
                                        memory_mode=MemoryMode.LOW_MEMORY_CANDIDATE)
    assert profile.profile_id == "cpu_fastq_quantification_only_v1"
    assert not profile.use_parabricks_star and profile.gpu_selection == "none"


def test_quantification_only_artifacts_are_not_missing_alignment(tmp_path: Path) -> None:
    (tmp_path / "frozen").mkdir(); (tmp_path / "execution/attempts").mkdir(parents=True)
    plan = {"execution_route": "fastq_quantification_only", "alignment_profile_id": "none",
            "samples": [{"sample": "S1"}], "quantification": {
                "primary_profile_id": "salmon_2_5_1_deterministic", "secondary_profile_id": None}}
    (tmp_path / "frozen/plan.json").write_text(json.dumps(plan), encoding="utf-8")
    records = discover_artifacts(tmp_path)
    states = {item.role: item.state.value for item in records}
    assert states["genomic_bam"] == "NOT_APPLICABLE"
    assert states["star_reads_per_gene"] == "NOT_APPLICABLE"
    assert states["multiqc_report"] == "NOT_APPLICABLE"
    assert states["processed_fastq_r1"] == "MISSING"


def test_fixed_fastp_identity_is_pinned() -> None:
    assert FASTP_IMAGE_REFERENCE.endswith("fastp:1.0.1--c8b87fe62dcc103c")
    assert FASTP_IMAGE_IDENTITY == "sha256:d228dace961ab50d04471e02e7fd2c8f2b8cd5b1b37be2d4039e2db64fcfae45"


def test_handoff_contains_no_data_or_credentials() -> None:
    handoff = high_memory_handoff()
    assert handoff["contains_biological_data"] is False
    assert handoff["contains_credentials"] is False
    assert handoff["expected_host_class"].startswith("NVIDIA GPU host")


def test_capability_matrix_has_all_fixed_entries() -> None:
    assert len(capability_matrix()["entries"]) == 7


def test_capability_cli_is_machine_readable() -> None:
    result = CliRunner().invoke(app, ["capabilities", "matrix", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["capability_matrix_version"] == "reference-aware-capability-v2"


def test_human_explain_never_silently_changes_bam_mode() -> None:
    result = CliRunner().invoke(app, ["capabilities", "explain", "--reference-pack",
        FULL_HUMAN_REFERENCE_PACK_ID, "--bam-mode", "keep", "--alignment-profile",
        "parabricks_star_one_pass_workstation", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["bam_output_mode"] == "keep"
    assert payload["status"] == "UNSUPPORTED_HOST_MEMORY"


def test_plan_cli_bam_none_does_not_inherit_keep_default(tmp_path: Path, monkeypatch) -> None:
    import harako_gpu.commands.plan as plan_command

    captured = {}
    monkeypatch.setattr(plan_command, "create_plan", lambda **kwargs: (
        captured.update(kwargs) or SimpleNamespace(plan_id="fixed-plan")
    ))
    files = {}
    for name in ("samples.csv", "genome.fa", "genes.gtf", "transcripts.fa", "salmon.json"):
        path = tmp_path / name
        path.write_text("x\n", encoding="utf-8")
        files[name] = path
    result = CliRunner().invoke(app, [
        "plan", "create", "--samplesheet", str(files["samples.csv"]),
        "--plan-dir", str(tmp_path / "plan"), "--output-root", str(tmp_path / "out"),
        "--work-root", str(tmp_path / "work"), "--fasta", str(files["genome.fa"]),
        "--gtf", str(files["genes.gtf"]), "--transcript-fasta", str(files["transcripts.fa"]),
        "--salmon-index-manifest", str(files["salmon.json"]), "--bam-output-mode", "none",
        "--alignment-profile", "none", "--species", "Homo sapiens", "--assembly", "GRCh38.p14",
        "--annotation-provider", "GENCODE", "--annotation-release", "49", "--project-slug", "test",
    ])
    assert result.exit_code == 0, result.output
    assert captured["bam_retention"] is BamRetention.NONE
    assert captured["bam_output_mode"] is BamOutputMode.NONE


def test_atomic_state_replace_retries_transient_windows_denial(tmp_path: Path, monkeypatch) -> None:
    import harako_gpu.adapters.filesystem as filesystem
    real_replace = filesystem.os.replace
    attempts = {"count": 0}

    def flaky(source, destination):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise PermissionError("transient UNC sharing denial")
        return real_replace(source, destination)

    monkeypatch.setattr(filesystem.os, "replace", flaky)
    target = tmp_path / "status.json"
    atomic_write_text(target, "stable\n")
    assert target.read_text(encoding="utf-8") == "stable\n"
    assert attempts["count"] == 3
