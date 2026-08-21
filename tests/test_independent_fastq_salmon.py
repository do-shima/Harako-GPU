from __future__ import annotations

from dataclasses import replace

import pytest

from harako_gpu.core.artifacts import ArtifactType
from harako_gpu.services.backend_profile import config_fragment, validate_nf_params
from harako_gpu.core.contracts import minimal_feasibility_profile
from harako_gpu.services.independent_fastq_salmon import (
    BAM_SALMON_PROCESS,
    FASTQ_SALMON_PROCESS,
    MATRIX_ARTIFACT_NAMES,
    PSEUDO_TRANSCRIPT_SUMMARIZED_EXPERIMENT_PROCESS,
    AlignmentModeSalmon,
    FastqSalmonQuantificationContract,
    ProcessedFastqIdentity,
    QuantificationInput,
    QuantificationMode,
    SalmonIndexIdentity,
    independent_fastq_nf_params,
    parse_nextflow_trace,
    quantification_manifest,
    salmon_mapping_argv,
    validate_multiqc_salmon_sources,
    validate_salmon_task_argv,
)


DIGEST = "a" * 64
IMAGE_DIGEST = "sha256:f83ebb158845ee8138d793347f83b92c75e83c58dd8f4600c6fea2a2453ef08e"


def index_identity() -> SalmonIndexIdentity:
    return SalmonIndexIdentity(
        salmon_index_id="tiny-decoy-aware-k31",
        index_path="/runtime/index",
        index_builder_version="1.10.3",
        index_builder_image_digest=IMAGE_DIGEST,
        transcript_fasta_sha256=DIGEST,
        genome_fasta_sha256=DIGEST,
        decoys_sha256=DIGEST,
        index_parameters=("-k", "31", "decoy_aware_gentrome"),
        index_manifest_sha256=DIGEST,
    )


def processed_identity() -> ProcessedFastqIdentity:
    return ProcessedFastqIdentity(
        sample_id="WT_REP1",
        r1_sha256=DIGEST,
        r2_sha256=DIGEST,
        r1_read_count=100,
        r2_read_count=100,
        fastp_version="1.0.1",
        fastp_image_digest="sha256:d228dace961ab50d04471e02e7fd2c8f2b8cd5b1b37be2d4039e2db64fcfae45",
        fastp_command_argv=("fastp", "--in1", "r1", "--in2", "r2"),
        strandedness="reverse",
    )


def test_fastq_quantification_contract_rejects_alignment_and_transcriptome_bam() -> None:
    contract = FastqSalmonQuantificationContract(index_identity())
    contract.validate()
    with pytest.raises(ValueError, match="alignment mode"):
        replace(contract, quantification_mode="alignment").validate()  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Transcriptome BAM"):
        replace(contract, quantification_input="transcriptome_bam").validate()  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="disabled_unqualified"):
        replace(contract, alignment_mode_salmon="enabled").validate()  # type: ignore[arg-type]


def test_index_and_processed_fastq_identity_fail_closed() -> None:
    with pytest.raises(ValueError, match="built by"):
        replace(index_identity(), index_builder_version="1.12.1").validate()
    with pytest.raises(ValueError, match="read counts"):
        replace(processed_identity(), r2_read_count=99).validate()
    with pytest.raises(ValueError, match="digest"):
        replace(index_identity(), index_builder_image_digest="latest").validate()


def test_salmon_mapping_argv_is_structured_and_alignment_free() -> None:
    argv = salmon_mapping_argv(index="idx", gene_map="g.gtf", r1="r1.fq", r2="r2.fq", output="out")
    assert argv[:2] == ("salmon", "quant")
    assert "-a" not in argv
    assert "--index" in argv and "-1" in argv and "-2" in argv
    assert "--libType=ISR" in argv
    assert not any("eval" in token or ";" in token for token in argv)
    validate_salmon_task_argv(argv)
    with pytest.raises(ValueError, match="Alignment-mode"):
        validate_salmon_task_argv((*argv, "-a", "tx.bam"))
    with pytest.raises(ValueError, match="fixed option profile"):
        validate_salmon_task_argv((*argv, "--seqBias"))
    with pytest.raises(TypeError):
        salmon_mapping_argv(index="idx", gene_map="g", r1="r1", r2="r2", output="o", extra="bad")  # type: ignore[call-arg]


def test_nfcore_config_disables_only_precise_bam_salmon_process() -> None:
    fragment = config_fragment(minimal_feasibility_profile(), independent_fastq_salmon=True)
    assert f"withName: '{BAM_SALMON_PROCESS}'" in fragment
    assert f"withName: '{FASTQ_SALMON_PROCESS}'" in fragment
    assert fragment.count("ext.when = false") == 2
    assert "QUANTIFY_PSEUDO_ALIGNMENT:SALMON_QUANT' {\n        ext.when = false" not in fragment
    assert "cpus = 6" in fragment
    assert f"withName: '{PSEUDO_TRANSCRIPT_SUMMARIZED_EXPERIMENT_PROCESS}'" in fragment


def test_independent_nf_params_are_fixed_and_arbitrary_args_remain_rejected() -> None:
    params = {
        "input": "s.csv", "outdir": "out", "fasta": "g.fa", "gtf": "g.gtf",
        "aligner": "star_salmon", "use_parabricks_star": True,
        "save_align_intermeds": True, "skip_markduplicates": True,
        **independent_fastq_nf_params(salmon_index="index"),
    }
    validate_nf_params(params)
    with pytest.raises(ValueError, match="Arbitrary"):
        validate_nf_params({**params, "extra_salmon_quant_args": "--deterministic"})
    with pytest.raises(ValueError, match="pinned Salmon index"):
        validate_nf_params({**params, "salmon_index": ""})


def _trace(rows: list[tuple[str, str]]) -> str:
    return "task_id\tprocess\tstatus\n" + "".join(
        f"{index}\t{process} (WT_REP1)\t{status}\n"
        for index, (process, status) in enumerate(rows, start=1)
    )


def test_trace_classifier_distinguishes_pseudo_and_bam_salmon() -> None:
    summary = parse_nextflow_trace(_trace([(FASTQ_SALMON_PROCESS, "COMPLETED")]))
    summary.validate_first_run(samples=1)
    resumed = parse_nextflow_trace(_trace([(FASTQ_SALMON_PROCESS, "CACHED")]))
    resumed.validate_resume(samples=1)
    with pytest.raises(ValueError, match="Alignment-mode"):
        parse_nextflow_trace(_trace([(BAM_SALMON_PROCESS, "COMPLETED")])).validate_first_run(samples=1)
    with pytest.raises(ValueError, match="Unexpected"):
        parse_nextflow_trace(_trace([("OTHER:SALMON_QUANT", "COMPLETED")])).validate_first_run(samples=1)


def test_artifact_names_and_manifest_distinguish_fastq_salmon_from_star() -> None:
    assert len(set(MATRIX_ARTIFACT_NAMES.values())) == 6
    assert not {"counts.tsv", "tpm.tsv", "expression.tsv"} & set(MATRIX_ARTIFACT_NAMES.values())
    assert ArtifactType.FASTQ_SALMON_QUANT != ArtifactType.STAR_GENE_COUNTS
    manifest = quantification_manifest(
        contract=FastqSalmonQuantificationContract(index_identity()),
        processed_fastq=processed_identity(),
        quant_sf_sha256=DIGEST,
        canonical_numerical_digest=DIGEST,
        tx2gene_sha256=DIGEST,
    )
    assert manifest["input_kind"] == "processed_fastq"
    assert manifest["alignment_mode_salmon"] == AlignmentModeSalmon.DISABLED_UNQUALIFIED
    assert len(manifest["manifest_sha256"]) == 64


def test_multiqc_requires_one_fastq_mapping_salmon_source() -> None:
    validate_multiqc_salmon_sources(
        [{"module": "salmon", "sample": "WT_REP1", "mapping_mode": "fastq"}],
        sample_id="WT_REP1",
    )
    with pytest.raises(ValueError, match="exactly one"):
        validate_multiqc_salmon_sources([], sample_id="WT_REP1")
    with pytest.raises(ValueError, match="FASTQ mapping"):
        validate_multiqc_salmon_sources(
            [{"module": "salmon", "sample": "WT_REP1", "mapping_mode": "alignment"}],
            sample_id="WT_REP1",
        )
