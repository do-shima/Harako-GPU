from __future__ import annotations

import pytest

from harako_gpu.adapters.nextflow import build_nextflow_argv, build_nextflow_environment, quote_argv, reject_mixed_path_context
from harako_gpu.core.contracts import (
    BackendProfile, BamRetention, MemoryMode, QualificationDebugMode,
    minimal_feasibility_profile, qualified_backend_profile,
)
from harako_gpu.services.backend_profile import build_nf_params, config_fragment, validate_nf_params


def profile(retention=BamRetention.KEEP):
    return qualified_backend_profile(bam_retention=retention, gpu_selection="all", memory_mode=MemoryMode.STANDARD)


def test_fixed_profile_is_pinned_and_parabricks_enabled() -> None:
    value = profile()
    assert value.nf_core_revision == "3.26.0"
    assert value.aligner == "star_salmon"
    assert value.use_parabricks_star is True
    assert value.container_engine == "docker"


@pytest.mark.parametrize("revision", ["latest", "dev", "3.25.0"])
def test_unpinned_or_wrong_revision_is_rejected(revision) -> None:
    with pytest.raises(ValueError, match="pinned"):
        BackendProfile("bad", nf_core_revision=revision).validate()


def test_cpu_fallback_is_rejected() -> None:
    with pytest.raises(ValueError, match="CPU fallback"):
        BackendProfile("bad", use_parabricks_star=False).validate()


@pytest.mark.parametrize(("fasta", "gtf", "message"), [("", "g.gtf", "FASTA"), ("g.fa", "", "GTF")])
def test_fasta_and_gtf_are_required(fasta, gtf, message) -> None:
    with pytest.raises(ValueError, match=message):
        build_nf_params(profile(), samplesheet="samples.csv", outdir="out", fasta=fasta, gtf=gtf)


def test_genome_and_arbitrary_parameters_are_rejected() -> None:
    params = build_nf_params(profile(), samplesheet="samples.csv", outdir="out", fasta="g.fa", gtf="g.gtf")
    with pytest.raises(ValueError, match="Arbitrary"):
        validate_nf_params({**params, "genome": "GRCh38"})
    with pytest.raises(ValueError, match="restricted"):
        validate_nf_params({**params, "extra_star_align_args": "$(bad)"})


def test_bam_keep_and_discard_profiles_keep_alignment_bam_generation_enabled() -> None:
    for retention in BamRetention:
        value = profile(retention)
        params = build_nf_params(value, samplesheet="s.csv", outdir="out", fasta="g.fa", gtf="g.gtf")
        assert params["save_align_intermeds"] is True
        assert value.bam_retention is retention


def test_low_memory_maps_to_fixed_star_args_and_skips_markduplicates() -> None:
    value = minimal_feasibility_profile()
    params = build_nf_params(value, samplesheet="s.csv", outdir="out", fasta="g.fa", gtf="g.gtf")
    assert params["extra_star_align_args"] == "--low-memory"
    assert params["skip_markduplicates"] is True
    assert params["use_parabricks_star"] is True
    assert params["aligner"] == "star_salmon"


def test_low_memory_debug_mode_has_only_fixed_x3_mapping() -> None:
    value = minimal_feasibility_profile(qualification_debug_mode=QualificationDebugMode.X3)
    params = build_nf_params(value, samplesheet="s.csv", outdir="out", fasta="g.fa", gtf="g.gtf")
    assert params["extra_star_align_args"] == "--low-memory --x3"
    fragment = config_fragment(value)
    assert "cpus: 8" in fragment
    assert "memory: '30.GB'" in fragment
    assert "time: '2.h'" in fragment
    with pytest.raises(ValueError, match="only valid"):
        qualified_backend_profile(
            bam_retention=BamRetention.KEEP,
            gpu_selection="all",
            memory_mode=MemoryMode.STANDARD,
            qualification_debug_mode=QualificationDebugMode.X3,
        )


def test_minimal_fixture_parameters_are_fixed_and_validated() -> None:
    value = minimal_feasibility_profile(qualification_debug_mode=QualificationDebugMode.X3)
    params = build_nf_params(
        value,
        samplesheet="s.csv",
        outdir="out",
        fasta="g.fa",
        gtf="g.gtf",
        transcript_fasta="tx.fa",
        save_reference=True,
        skip_pseudo_alignment=True,
    )
    validate_nf_params(params)
    assert params["transcript_fasta"] == "tx.fa"
    assert params["save_reference"] is True
    assert params["skip_pseudo_alignment"] is True
    assert params["extra_star_align_args"] == "--low-memory --x3"


def test_standard_profile_is_retained_without_claiming_low_memory_mapping() -> None:
    params = build_nf_params(profile(), samplesheet="s.csv", outdir="out", fasta="g.fa", gtf="g.gtf")
    assert "extra_star_align_args" not in params
    assert params["skip_markduplicates"] is False


def test_structured_argv_and_platform_quoting() -> None:
    argv = build_nextflow_argv(
        samplesheet="a b/samples.csv", outdir="a b/out", fasta="ref/g.fa", gtf="ref/g.gtf",
        params_file="a b/nf-params.json", work_dir="a b/work",
    )
    assert argv[:6] == ["nextflow", "run", "nf-core/rnaseq", "-r", "3.26.0", "-profile"]
    assert "--genome" not in argv
    assert build_nextflow_environment() == {"NXF_VER": "25.04.3"}
    assert quote_argv(argv, target="windows").startswith("nextflow run nf-core/rnaseq")
    assert "'a b/samples.csv'" in quote_argv(argv, target="linux")


def test_gpu_selection_is_grammar_checked_not_injected() -> None:
    malicious = qualified_backend_profile(
        bam_retention=BamRetention.KEEP, gpu_selection="all; touch bad", memory_mode=MemoryMode.STANDARD
    )
    with pytest.raises(ValueError, match="gpu_selection"):
        config_fragment(malicious)


def test_gpu_selection_maps_to_process_gpu_container_options() -> None:
    selected = qualified_backend_profile(
        bam_retention=BamRetention.KEEP, gpu_selection="0", memory_mode=MemoryMode.LOW_MEMORY_CANDIDATE
    )
    fragment = config_fragment(selected)
    assert "params.gpu_container_options = '--gpus \"device=0\"'" in fragment
    assert "runOptions" not in fragment


def test_windows_paths_require_explicit_wsl_conversion() -> None:
    with pytest.raises(ValueError, match="explicit WSL conversion"):
        reject_mixed_path_context({"fasta": r"C:\refs\g.fa"}, target="wsl")
