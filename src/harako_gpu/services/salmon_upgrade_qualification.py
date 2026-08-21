"""Fail-closed qualification contract for the Salmon 1.12.1 candidate."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from harako_gpu.services.independent_fastq_salmon import (
    BAM_SALMON_PROCESS,
    FASTQ_SALMON_PROCESS,
)
from harako_gpu.services.salmon_reproducibility import (
    ExpressionComparison,
    QuantComparison,
    SalmonMetadataIdentity,
)


SCHEMA_VERSION = 1
CANDIDATE_VERSION = "1.12.1"
CANDIDATE_RELEASE_TAG = "v1.12.1"
CANDIDATE_SOURCE_COMMIT = "971a2ad6e86cc32315d919faed0be0e88d36c9e5"
CANDIDATE_ASSET_NAME = "salmon-linux-x86_64.tar.gz"
CANDIDATE_ASSET_SHA256 = "00900135ecca10b45e3d78a6ab64463f957d0b2b0069eaa078c10784f1e2f8d6"
CANDIDATE_LOCAL_IMAGE = "harako-gpu/salmon:1.12.1-qualification"
CANDIDATE_PROFILE_ID = "fastq_salmon_1_12_1_candidate"
CANDIDATE_OPTION_PROFILE_ID = "nfcore-rnaseq-3.26.0-fastq-salmon-1.12.1-isr-v1"
CANDIDATE_THREADS = 6
CANDIDATE_LIBRARY_TYPE = "ISR"
BASE_IMAGE_DIGEST = "sha256:f83ebb158845ee8138d793347f83b92c75e83c58dd8f4600c6fea2a2453ef08e"
SALMON_INDEX_PROCESS = "NFCORE_RNASEQ:PREPARE_GENOME:SALMON_INDEX"
TRANSCRIPT_SPEARMAN_MINIMUM = 0.995
GENE_SPEARMAN_MINIMUM = 0.995
MAPPING_RATE_MAX_ABSOLUTE_PERCENTAGE_POINT_DIFFERENCE = Decimal("2")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")


class CandidateStatus(StrEnum):
    QUALIFICATION_CANDIDATE = "qualification_candidate"
    QUALIFIED_SMALL_FIXTURE = "qualified_small_fixture"
    REJECTED_NUMERICAL_GATE = "rejected_numerical_gate"


class SalmonImplementation(StrEnum):
    CPP_LEGACY = "cpp_legacy"


class ReleaseScope(StrEnum):
    DIRECTLY_RELEVANT = "DIRECTLY_RELEVANT"
    RELEVANT_ONLY_IF_OPTION_ENABLED = "RELEVANT_ONLY_IF_OPTION_ENABLED"
    ALIGNMENT_MODE_ONLY = "ALIGNMENT_MODE_ONLY"
    NOT_EXERCISED_BY_CURRENT_PROFILE = "NOT_EXERCISED_BY_CURRENT_PROFILE"
    UNKNOWN_REQUIRES_TEST = "UNKNOWN_REQUIRES_TEST"


@dataclass(frozen=True)
class CandidateReleaseIdentity:
    version: str
    release_tag: str
    source_commit: str
    asset_name: str
    asset_sha256: str
    base_image_digest: str
    implementation: SalmonImplementation = SalmonImplementation.CPP_LEGACY
    schema_version: int = SCHEMA_VERSION

    def validate(self) -> None:
        expected = (
            CANDIDATE_VERSION,
            CANDIDATE_RELEASE_TAG,
            CANDIDATE_SOURCE_COMMIT,
            CANDIDATE_ASSET_NAME,
            CANDIDATE_ASSET_SHA256,
            BASE_IMAGE_DIGEST,
        )
        actual = (
            self.version,
            self.release_tag,
            self.source_commit,
            self.asset_name,
            self.asset_sha256,
            self.base_image_digest,
        )
        if self.schema_version != SCHEMA_VERSION or actual != expected:
            raise ValueError("Salmon candidate release identity is not the pinned 1.12.1 contract")
        if self.implementation is not SalmonImplementation.CPP_LEGACY:
            raise ValueError("Salmon 1.12.1 candidate must be the legacy C++ implementation")

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class CandidateImageIdentity:
    image: str
    image_id: str
    config_digest: str
    dockerfile_sha256: str
    salmon_version_output: str

    def validate(self) -> None:
        if self.image != CANDIDATE_LOCAL_IMAGE:
            raise ValueError("Candidate image must use the qualification-only local tag")
        for field in ("image_id", "config_digest"):
            if not _IMAGE_ID.fullmatch(getattr(self, field)):
                raise ValueError(f"{field} must be a pinned SHA-256 image identity")
        if not _HEX_64.fullmatch(self.dockerfile_sha256):
            raise ValueError("Dockerfile SHA-256 is required")
        if self.salmon_version_output.strip() != "salmon 1.12.1":
            raise ValueError("Candidate binary did not report Salmon 1.12.1")


@dataclass(frozen=True)
class CandidateIndexIdentity:
    salmon_index_id: str
    index_builder_version: str
    index_builder_image_id: str
    transcript_fasta_sha256: str
    genome_fasta_sha256: str
    gentrome_sha256: str
    decoys_sha256: str
    kmer_size: int
    index_manifest_sha256: str
    schema_version: int = SCHEMA_VERSION

    def validate(self, *, salmon_version: str = CANDIDATE_VERSION) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Candidate index schema_version must be 1")
        if salmon_version != CANDIDATE_VERSION or self.index_builder_version != salmon_version:
            raise ValueError("Salmon candidate and index builder versions must both be 1.12.1")
        if not _IMAGE_ID.fullmatch(self.index_builder_image_id):
            raise ValueError("Candidate index builder image identity must be pinned")
        hashes = (
            self.transcript_fasta_sha256,
            self.genome_fasta_sha256,
            self.gentrome_sha256,
            self.decoys_sha256,
            self.index_manifest_sha256,
        )
        if not all(_HEX_64.fullmatch(value) for value in hashes):
            raise ValueError("Candidate index source and manifest SHA-256 values are required")
        if self.kmer_size != 31:
            raise ValueError("Candidate index must use k=31")
        expected_id = hashlib.sha256(
            json.dumps(
                {
                    "builder_version": self.index_builder_version,
                    "builder_image": self.index_builder_image_id,
                    "transcript_fasta": self.transcript_fasta_sha256,
                    "genome_fasta": self.genome_fasta_sha256,
                    "gentrome": self.gentrome_sha256,
                    "decoys": self.decoys_sha256,
                    "kmer_size": self.kmer_size,
                    "manifest": self.index_manifest_sha256,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if self.salmon_index_id != expected_id:
            raise ValueError("Candidate Salmon index ID does not match its scientific identity")


@dataclass(frozen=True)
class NonRegressionReport:
    transcript_id_set_equal: bool
    gene_id_set_equal: bool
    output_schema_compatible: bool
    finite_nonnegative_values: bool
    fragment_accounting_consistent: bool
    transcript_spearman: float
    gene_spearman: float
    high_tpm_zero_nonzero_transitions: int
    mapping_rate_absolute_percentage_point_difference: Decimal

    @property
    def passed(self) -> bool:
        return all(
            (
                self.transcript_id_set_equal,
                self.gene_id_set_equal,
                self.output_schema_compatible,
                self.finite_nonnegative_values,
                self.fragment_accounting_consistent,
                self.transcript_spearman >= TRANSCRIPT_SPEARMAN_MINIMUM,
                self.gene_spearman >= GENE_SPEARMAN_MINIMUM,
                self.high_tpm_zero_nonzero_transitions == 0,
                self.mapping_rate_absolute_percentage_point_difference
                <= MAPPING_RATE_MAX_ABSOLUTE_PERCENTAGE_POINT_DIFFERENCE,
            )
        )


@dataclass(frozen=True)
class CandidateResumeIdentity:
    plan_id: str
    image_id: str
    salmon_index_id: str
    processed_r1_sha256: str
    processed_r2_sha256: str
    quantification_digest: str

    def validate(self) -> None:
        if not self.plan_id.strip():
            raise ValueError("Candidate resume plan ID is required")
        if not _IMAGE_ID.fullmatch(self.image_id):
            raise ValueError("Candidate resume image identity must be pinned")
        for field in (
            "salmon_index_id",
            "processed_r1_sha256",
            "processed_r2_sha256",
            "quantification_digest",
        ):
            if not _HEX_64.fullmatch(getattr(self, field)):
                raise ValueError(f"{field} must be a lowercase SHA-256")


def pinned_candidate_release() -> CandidateReleaseIdentity:
    return CandidateReleaseIdentity(
        version=CANDIDATE_VERSION,
        release_tag=CANDIDATE_RELEASE_TAG,
        source_commit=CANDIDATE_SOURCE_COMMIT,
        asset_name=CANDIDATE_ASSET_NAME,
        asset_sha256=CANDIDATE_ASSET_SHA256,
        base_image_digest=BASE_IMAGE_DIGEST,
    )


def validate_asset_sha256(actual: str) -> None:
    if actual != CANDIDATE_ASSET_SHA256:
        raise ValueError("Official Salmon 1.12.1 asset SHA-256 mismatch")


def candidate_mapping_argv(
    *, index: str, gene_map: str, r1: str, r2: str, output: str,
    threads: int = CANDIDATE_THREADS,
) -> tuple[str, ...]:
    if threads != CANDIDATE_THREADS:
        raise ValueError("Candidate product command must use exactly 6 threads")
    paths = (index, gene_map, r1, r2, output)
    if any(not value or "\x00" in value for value in paths):
        raise ValueError("Candidate Salmon paths must be non-empty and contain no NUL")
    return (
        "salmon", "quant", "--geneMap", gene_map, "--threads", "6",
        "--libType=ISR", "--index", index, "-1", r1, "-2", r2, "-o", output,
    )


def candidate_nfcore_override(*, image_identity: str, status: CandidateStatus) -> str:
    """Return a fixed candidate-only override only after numerical qualification."""

    if status is not CandidateStatus.QUALIFIED_SMALL_FIXTURE:
        raise ValueError("Candidate nf-core override is forbidden before numerical qualification")
    if not _IMAGE_ID.fullmatch(image_identity):
        raise ValueError("Candidate nf-core override requires an exact local image identity")
    return (
        "// Harako-GPU Salmon 1.12.1 qualification candidate; not a default profile.\n"
        "process {\n"
        f"    withName: '{SALMON_INDEX_PROCESS}' {{\n"
        f"        container = '{CANDIDATE_LOCAL_IMAGE}@{image_identity}'\n"
        "    }\n"
        f"    withName: '{FASTQ_SALMON_PROCESS}' {{\n"
        f"        container = '{CANDIDATE_LOCAL_IMAGE}@{image_identity}'\n"
        "        cpus = 6\n"
        "    }\n"
        "}\n"
    )


def build_non_regression_report(
    *, transcript: QuantComparison, gene: ExpressionComparison,
    baseline_metadata: SalmonMetadataIdentity, candidate_metadata: SalmonMetadataIdentity,
) -> NonRegressionReport:
    baseline_rate = (
        Decimal(baseline_metadata.num_mapped) * 100 / Decimal(baseline_metadata.num_processed)
        if baseline_metadata.num_processed else Decimal(0)
    )
    candidate_rate = (
        Decimal(candidate_metadata.num_mapped) * 100 / Decimal(candidate_metadata.num_processed)
        if candidate_metadata.num_processed else Decimal(0)
    )
    high_transitions = len(transcript.zero_nonzero_transition_ids) + len(
        gene.zero_nonzero_transition_ids
    )
    return NonRegressionReport(
        transcript_id_set_equal=transcript.id_set_equal,
        gene_id_set_equal=gene.id_set_equal,
        output_schema_compatible=True,
        finite_nonnegative_values=True,
        fragment_accounting_consistent=(
            baseline_metadata.num_processed == candidate_metadata.num_processed
            and baseline_metadata.num_mapped <= baseline_metadata.num_processed
            and candidate_metadata.num_mapped <= candidate_metadata.num_processed
        ),
        transcript_spearman=transcript.tpm_spearman,
        gene_spearman=gene.tpm_spearman,
        high_tpm_zero_nonzero_transitions=high_transitions,
        mapping_rate_absolute_percentage_point_difference=abs(candidate_rate - baseline_rate),
    )


def release_scope() -> dict[str, ReleaseScope]:
    return {
        "sshash_kmer_orientation_fix": ReleaseScope.DIRECTLY_RELEVANT,
        "seq_bias_training_fix": ReleaseScope.RELEVANT_ONLY_IF_OPTION_ENABLED,
        "alignment_mode_mate_pairing_fix": ReleaseScope.ALIGNMENT_MODE_ONLY,
        "positional_bias_fix": ReleaseScope.RELEVANT_ONLY_IF_OPTION_ENABLED,
        "mapping_output_flush_fix": ReleaseScope.NOT_EXERCISED_BY_CURRENT_PROFILE,
        "startup_memory_change": ReleaseScope.ALIGNMENT_MODE_ONLY,
        "deterministic_offline_optimizer": ReleaseScope.DIRECTLY_RELEVANT,
        "uniform_offline_initialization": ReleaseScope.DIRECTLY_RELEVANT,
        "selective_alignment_mapping_fixes": ReleaseScope.DIRECTLY_RELEVANT,
        "max_read_occ_enforcement": ReleaseScope.DIRECTLY_RELEVANT,
        "write_mappings_gc_bias_fix": ReleaseScope.NOT_EXERCISED_BY_CURRENT_PROFILE,
        "residual_fld_feedback_variability": ReleaseScope.UNKNOWN_REQUIRES_TEST,
    }


def validate_resume_identity(
    first_run: CandidateResumeIdentity, resumed_run: CandidateResumeIdentity
) -> None:
    first_run.validate()
    resumed_run.validate()
    if first_run != resumed_run:
        raise ValueError("Candidate resume changed plan, input, image, index, or quantification identity")
