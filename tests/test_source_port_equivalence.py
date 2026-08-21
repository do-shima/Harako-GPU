"""Fixtures frozen from do-shima/harako-rnaseq@9d8628f."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harako_gpu.core.analysis import (
    AnalysisPlanError,
    analysis_plan_from_rows,
    assert_analysis_plan_consistent,
    evaluate_analysis_eligibility,
)
from harako_gpu.core.artifacts import artifact_response
from harako_gpu.core.canonical import canonical_json, sha256_payload
from harako_gpu.core.fastq import infer_pair_candidates, read_side, sample_base, split_read_suffix
from harako_gpu.core.provenance import approval_hash_for, plan_id_for
from harako_gpu.core.samples import validate_samples


FIXTURES = Path(__file__).parent / "fixtures"


def row(sample: str, condition: str) -> dict[str, str]:
    return {"sample": sample, "condition": condition, "fastq1": f"{sample}.fastq.gz" if sample else "", "fastq2": ""}


def test_fastq_filename_parsing_read_side_and_pairing_match_source_fixture() -> None:
    assert split_read_suffix("sample_R1") == ("sample", "1", True, "_")
    assert read_side("x/sample_R2.fastq.gz") == "2"
    assert read_side("x/sample.fastq.gz") == ""
    assert sample_base("nested/A_R1.fastq.gz") == "A"
    assert "dir/sample_R2.fastq.gz" in infer_pair_candidates("dir/sample_R1.fastq.gz")
    assert infer_pair_candidates("sample.fastq.gz") == []


@pytest.mark.parametrize(
    ("rows", "mode", "reason", "counts"),
    [
        ([], "invalid", "no_samples", {}),
        ([row("", "A")], "invalid", "missing_sample", {}),
        ([row("s1", "")], "invalid", "missing_condition", {}),
        ([row("s1", "A"), row("s1", "A")], "invalid", "duplicate_sample", {}),
        ([row("s1", "A")], "qc_only", "single_condition", {"A": 1}),
        ([row("a1", "A"), row("b1", "B")], "qc_only", "insufficient_replicates", {"A": 1, "B": 1}),
        ([row("a1", "A"), row("a2", "A"), row("b1", "B"), row("b2", "B")], "differential", "eligible", {"A": 2, "B": 2}),
    ],
)
def test_analysis_eligibility_matches_source_matrix(rows, mode, reason, counts) -> None:
    result = evaluate_analysis_eligibility(rows)
    assert result.mode == mode
    assert result.reason_code == reason
    assert result.condition_counts == counts


def test_analysis_plan_matches_source_and_detects_mismatch() -> None:
    rows = [row("a1", "A"), row("a2", "A")]
    plan = analysis_plan_from_rows(rows)
    assert plan == {
        "schema_version": 1, "policy_version": 1, "mode": "qc_only", "structurally_valid": True,
        "eligible_for_de": False, "reason_code": "single_condition", "condition_counts": {"A": 2},
        "total_samples": 2, "contrast_allowed": False, "enrichment_allowed": False,
    }
    with pytest.raises(AnalysisPlanError, match="condition_counts"):
        assert_analysis_plan_consistent(plan, [row("a1", "A")])


def test_canonical_json_and_digest_match_source_fixture() -> None:
    payload = {"z": "日本語", "a": [3, {"b": True}]}
    assert canonical_json(payload) == '{"a":[3,{"b":true}],"z":"日本語"}'
    assert sha256_payload(payload) == "7ad06aa2be164d766f8a775c404305335e09ab0e49e19845463c3a2e94b8cfbd"


def test_plan_id_and_approval_hash_match_source_legacy_fixture() -> None:
    plan = json.loads((FIXTURES / "source_agent_plan_v1_legacy.json").read_text(encoding="utf-8"))
    source_execution_payload = {
        key: plan.get(key)
        for key in (
            "schema_version", "harako_version", "input_root", "output_root", "project_name", "samples",
            "reference", "analysis_plan", "contrasts", "enrichment", "resources", "requested_options",
        )
    }
    assert plan_id_for(source_execution_payload) == plan["plan_id"]
    assert approval_hash_for(source_execution_payload) == plan["approval_hash"]


def test_adapted_sample_structural_schema() -> None:
    valid = validate_samples([
        {"sample": "S1", "condition": "A", "fastq_1": "S1_R1.fastq.gz", "fastq_2": "S1_R2.fastq.gz", "strandedness": "auto", "library_protocol": "full_length"}
    ])
    assert valid.schema_version == 1
    assert valid.valid is True
    invalid = validate_samples([
        {"sample": "S1", "condition": "", "fastq_1": "S1_R2.fastq.gz", "fastq_2": "", "strandedness": "sideways", "library_protocol": ""}
    ])
    assert invalid.valid is False
    assert len(invalid.errors) == 4


def test_artifact_response_fields_match_source_fixture(tmp_path: Path) -> None:
    artifact = tmp_path / "salmon" / "S1" / "quant.sf"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"abc")
    assert artifact_response(tmp_path, "salmon_quant", "salmon/S1/quant.sf", "qc_only", "Salmon quantification.") == {
        "artifact_type": "salmon_quant",
        "relative_path": "salmon/S1/quant.sf",
        "exists": True,
        "size_bytes": 3,
        "generated": True,
        "applicable": True,
        "analysis_mode": "qc_only",
        "description": "Salmon quantification.",
    }
