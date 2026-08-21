from __future__ import annotations

import pytest

from harako_gpu.core.run_lifecycle import (
    ArtifactRecord, ArtifactState, AttemptState, FailureClassification, FailureRecord,
    RunIdentity, RunState, StageId, TaskRecord, transition_attempt, transition_run,
)


SHA = "a" * 64


def identity(**updates) -> RunIdentity:
    values = dict(
        run_id="20260817T010203Z-1234abcd", project_slug="p", plan_id=SHA,
        approval_hash="b" * 64, analysis_series_id="series", primary_profile_id="p1",
        secondary_profile_id="p2", comparison_mode="compare_both", reference_pack_id="ref",
        fasta_sha256=SHA, gtf_sha256=SHA, tx2gene_sha256=SHA, samplesheet_sha256=SHA,
        processed_input_contract="shared", nf_core_revision="3.26.0",
        resolved_pipeline_commit="e7ca46272c8f9d5ceee3f71759f4ba551d3217a4",
        nextflow_version="25.04.3", parabricks_image_identity="sha256:" + SHA,
        patch_set_identity=SHA, salmon_image_identities={"p1": "sha256:" + SHA},
        salmon_index_identities={"p1": "index"}, gene_counts_contract_version="v1",
        created_at="2026-08-17T01:02:03Z", execution_context="wsl2:Ubuntu",
        output_root="/home/u/runtime/runs", work_root="/home/u/runtime/work/run",
        launch_directory="/home/u/runtime/runs/p/run",
    )
    values.update(updates)
    return RunIdentity(**values)


def test_run_identity_is_canonical_and_rejects_windows_mounts() -> None:
    first = identity()
    assert first.identity_digest == identity().identity_digest
    with pytest.raises(ValueError, match="Windows mounts"):
        identity(work_root="/mnt/d/work").validate()


def test_run_state_transitions_are_explicit_and_resume_guarded() -> None:
    assert transition_run(RunState.PREPARED, RunState.RUNNING) is RunState.RUNNING
    assert transition_run(RunState.RUNNING, RunState.FAILED) is RunState.FAILED
    assert transition_run(RunState.FAILED, RunState.RUNNING, resume=True) is RunState.RUNNING
    with pytest.raises(ValueError, match="only through resume"):
        transition_run(RunState.FAILED, RunState.RUNNING)
    with pytest.raises(ValueError, match="Forbidden"):
        transition_run(RunState.COMPLETED, RunState.RUNNING, resume=True)


def test_attempt_transitions_preserve_terminal_states() -> None:
    assert transition_attempt(AttemptState.CREATED, AttemptState.RUNNING) is AttemptState.RUNNING
    assert transition_attempt(AttemptState.RUNNING, AttemptState.SUCCEEDED) is AttemptState.SUCCEEDED
    with pytest.raises(ValueError):
        transition_attempt(AttemptState.SUCCEEDED, AttemptState.RUNNING)


def test_task_artifact_and_failure_contracts_fail_closed() -> None:
    task = TaskRecord("t", StageId.SALMON_PRIMARY.value, "S", "p", SHA, SHA, "sha256:" + SHA)
    task.validate()
    artifact = ArtifactRecord("a", "quant", "p", "S", "RUN_DIR", "results/p/S/quant.sf",
                              "text/tab-separated-values", None, StageId.SALMON_PRIMARY.value,
                              "t", True, ArtifactState.EXPECTED)
    artifact.validate()
    with pytest.raises(ValueError, match="safe relative"):
        ArtifactRecord("a", "x", None, None, "RUN", "../secret", "text/plain", None,
                       StageId.ARTIFACTS.value, "t", True, ArtifactState.EXPECTED).validate()
    failure = FailureRecord(FailureClassification.NEXTFLOW, StageId.NFCORE.value, "t", "P", 1,
                            "failed", "Nextflow failed", "detail", ("stderr.log",), True,
                            "Inspect logs and resume after correcting the prerequisite")
    failure.validate()
    with pytest.raises(ValueError, match="CPU fallback"):
        FailureRecord(FailureClassification.PARABRICKS, "s", None, None, 1, "x", "x", "x", (), True,
                      "Use CPU fallback").validate()
