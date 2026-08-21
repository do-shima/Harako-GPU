from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest

from harako_gpu.services.independent_fastq_salmon import (
    BAM_SALMON_PROCESS,
    FASTQ_SALMON_PROCESS,
)
from harako_gpu.services.salmon_reproducibility import (
    ExpressionComparison,
    SalmonMetadataIdentity,
    StratumComparison,
    TpmStratum,
    compare_expression_tables,
    compare_quant_tables,
    parse_quant_sf,
    ExpressionRow,
    ExpressionTable,
)
from harako_gpu.services.salmon_upgrade_qualification import (
    BASE_IMAGE_DIGEST,
    CANDIDATE_ASSET_SHA256,
    CANDIDATE_LOCAL_IMAGE,
    CANDIDATE_SOURCE_COMMIT,
    CANDIDATE_VERSION,
    SALMON_INDEX_PROCESS,
    CandidateImageIdentity,
    CandidateIndexIdentity,
    CandidateResumeIdentity,
    CandidateStatus,
    ReleaseScope,
    build_non_regression_report,
    candidate_mapping_argv,
    candidate_nfcore_override,
    pinned_candidate_release,
    release_scope,
    validate_asset_sha256,
    validate_resume_identity,
)


SHA = "a" * 64
IMAGE_ID = "sha256:" + "b" * 64


def _index_id(**overrides: object) -> CandidateIndexIdentity:
    values: dict[str, object] = {
        "salmon_index_id": "",
        "index_builder_version": CANDIDATE_VERSION,
        "index_builder_image_id": IMAGE_ID,
        "transcript_fasta_sha256": SHA,
        "genome_fasta_sha256": SHA,
        "gentrome_sha256": SHA,
        "decoys_sha256": SHA,
        "kmer_size": 31,
        "index_manifest_sha256": SHA,
    }
    values.update(overrides)
    candidate = CandidateIndexIdentity(**values)  # type: ignore[arg-type]
    import hashlib
    import json

    payload = {
        "builder_version": candidate.index_builder_version,
        "builder_image": candidate.index_builder_image_id,
        "transcript_fasta": candidate.transcript_fasta_sha256,
        "genome_fasta": candidate.genome_fasta_sha256,
        "gentrome": candidate.gentrome_sha256,
        "decoys": candidate.decoys_sha256,
        "kmer_size": candidate.kmer_size,
        "manifest": candidate.index_manifest_sha256,
    }
    return replace(
        candidate,
        salmon_index_id=hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    )


def _quant(tpm: str = "10", reads: str = "5"):
    return parse_quant_sf(
        "Name\tLength\tEffectiveLength\tTPM\tNumReads\n"
        f"tx1\t100\t80\t{tpm}\t{reads}\n"
    )


def _meta(*, version: str, processed: int = 100, mapped: int = 80) -> SalmonMetadataIdentity:
    return SalmonMetadataIdentity(version, "mapping", ("ISR",), processed, mapped, 1, False, False)


def test_candidate_release_and_asset_are_exactly_pinned() -> None:
    identity = pinned_candidate_release()
    identity.validate()
    assert identity.source_commit == CANDIDATE_SOURCE_COMMIT
    assert identity.asset_sha256 == CANDIDATE_ASSET_SHA256
    assert identity.base_image_digest == BASE_IMAGE_DIGEST
    validate_asset_sha256(CANDIDATE_ASSET_SHA256)
    with pytest.raises(ValueError, match="asset SHA"):
        validate_asset_sha256(SHA)
    with pytest.raises(ValueError, match="pinned 1.12.1"):
        replace(identity, version="latest").validate()


def test_candidate_image_requires_local_tag_digest_and_binary_version() -> None:
    image = CandidateImageIdentity(CANDIDATE_LOCAL_IMAGE, IMAGE_ID, IMAGE_ID, SHA, "salmon 1.12.1")
    image.validate()
    with pytest.raises(ValueError, match="did not report"):
        replace(image, salmon_version_output="salmon 1.10.3").validate()
    with pytest.raises(ValueError, match="qualification-only"):
        replace(image, image="salmon:latest").validate()


def test_committed_candidate_manifest_matches_the_pinned_release() -> None:
    container = Path(__file__).parents[1] / "containers" / "salmon-1.12.1-qualification"
    manifest = json.loads((container / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["candidate_version"] == CANDIDATE_VERSION
    assert manifest["source_commit"] == CANDIDATE_SOURCE_COMMIT
    validate_asset_sha256(manifest["asset_sha256"])
    CandidateImageIdentity(
        manifest["local_tag"],
        manifest["built_image_id"],
        manifest["built_image_config_digest"],
        manifest["dockerfile_sha256"],
        manifest["salmon_version_output"],
    ).validate()
    assert manifest["dockerfile_sha256"] == hashlib.sha256(
        (container / "Dockerfile").read_bytes()
    ).hexdigest()
    assert manifest["entrypoint_sha256"] == hashlib.sha256(
        (container / "entrypoint.sh").read_bytes()
    ).hexdigest()
    assert manifest["published"] is False


def test_candidate_index_is_version_specific_and_rejects_mismatch() -> None:
    identity = _index_id()
    identity.validate()
    with pytest.raises(ValueError, match="both be 1.12.1"):
        identity.validate(salmon_version="1.10.3")
    with pytest.raises(ValueError, match="both be 1.12.1"):
        _index_id(index_builder_version="1.10.3").validate()
    with pytest.raises(ValueError, match="k=31"):
        _index_id(kmer_size=23).validate()


def test_candidate_command_is_structured_and_accepts_no_extra_arguments() -> None:
    argv = candidate_mapping_argv(index="idx", gene_map="g.gtf", r1="r1", r2="r2", output="out")
    assert argv == (
        "salmon", "quant", "--geneMap", "g.gtf", "--threads", "6", "--libType=ISR",
        "--index", "idx", "-1", "r1", "-2", "r2", "-o", "out",
    )
    assert "-a" not in argv and not any("eval" in token or ";" in token for token in argv)
    with pytest.raises(ValueError, match="exactly 6"):
        candidate_mapping_argv(index="i", gene_map="g", r1="1", r2="2", output="o", threads=4)
    with pytest.raises(TypeError):
        candidate_mapping_argv(index="i", gene_map="g", r1="1", r2="2", output="o", extra="--seqBias")  # type: ignore[call-arg]


def test_nfcore_override_is_precise_and_fail_closed_before_qualification() -> None:
    with pytest.raises(ValueError, match="forbidden"):
        candidate_nfcore_override(image_identity=IMAGE_ID, status=CandidateStatus.REJECTED_NUMERICAL_GATE)
    fragment = candidate_nfcore_override(
        image_identity=IMAGE_ID, status=CandidateStatus.QUALIFIED_SMALL_FIXTURE
    )
    assert f"withName: '{SALMON_INDEX_PROCESS}'" in fragment
    assert f"withName: '{FASTQ_SALMON_PROCESS}'" in fragment
    assert BAM_SALMON_PROCESS not in fragment
    assert fragment.count("container =") == 2
    assert "Parabricks" not in fragment and "MULTIQC" not in fragment


def test_release_scope_does_not_claim_disabled_options() -> None:
    scope = release_scope()
    assert scope["sshash_kmer_orientation_fix"] is ReleaseScope.DIRECTLY_RELEVANT
    assert scope["seq_bias_training_fix"] is ReleaseScope.RELEVANT_ONLY_IF_OPTION_ENABLED
    assert scope["alignment_mode_mate_pairing_fix"] is ReleaseScope.ALIGNMENT_MODE_ONLY
    assert scope["mapping_output_flush_fix"] is ReleaseScope.NOT_EXERCISED_BY_CURRENT_PROFILE
    assert scope["residual_fld_feedback_variability"] is ReleaseScope.UNKNOWN_REQUIRES_TEST


def test_quant_schema_rejects_invalid_and_non_finite_candidate_output() -> None:
    assert _quant().ids == ("tx1",)
    with pytest.raises(ValueError, match="header"):
        parse_quant_sf("Name\tTPM\ntx1\t1\n")
    with pytest.raises(ValueError, match="Invalid TPM"):
        _quant(tpm="NaN")
    with pytest.raises(ValueError, match="Duplicate"):
        parse_quant_sf(
            "Name\tLength\tEffectiveLength\tTPM\tNumReads\n"
            "tx1\t100\t80\t1\t1\n"
            "tx1\t100\t80\t1\t1\n"
        )


def test_non_regression_gate_enforces_mapping_rate_and_correlations() -> None:
    transcript = compare_quant_tables(_quant(), _quant())
    gene = compare_expression_tables(
        ExpressionTable((ExpressionRow("g1", Decimal("10"), Decimal("5")),)),
        ExpressionTable((ExpressionRow("g1", Decimal("10"), Decimal("5")),)),
    )
    passing = build_non_regression_report(
        transcript=transcript,
        gene=gene,
        baseline_metadata=_meta(version="1.10.3"),
        candidate_metadata=_meta(version="1.12.1", mapped=79),
    )
    assert passing.passed
    failing = build_non_regression_report(
        transcript=transcript,
        gene=gene,
        baseline_metadata=_meta(version="1.10.3", mapped=80),
        candidate_metadata=_meta(version="1.12.1", mapped=10),
    )
    assert failing.mapping_rate_absolute_percentage_point_difference == Decimal("70")
    assert not failing.passed


def test_candidate_status_never_changes_the_default_salmon_contract() -> None:
    from harako_gpu.services.independent_fastq_salmon import SALMON_VERSION

    assert SALMON_VERSION == "1.10.3"
    assert CandidateStatus.QUALIFICATION_CANDIDATE != CandidateStatus.QUALIFIED_SMALL_FIXTURE


def test_resume_requires_exact_candidate_image_index_input_and_quant_identity() -> None:
    identity = CandidateResumeIdentity("plan-1", IMAGE_ID, SHA, SHA, SHA, SHA)
    validate_resume_identity(identity, identity)
    with pytest.raises(ValueError, match="changed"):
        validate_resume_identity(identity, replace(identity, salmon_index_id="c" * 64))
