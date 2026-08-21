from __future__ import annotations

import csv
import json
import hashlib
import platform
from types import SimpleNamespace
from pathlib import Path

import pytest

from harako_gpu.adapters.nextflow import reject_mixed_path_context
from harako_gpu.core.contracts import BamRetention, MemoryMode
from harako_gpu.services.planning import create_plan, validate_plan_file
from harako_gpu.services.quantification_profiles import get_profile
from harako_gpu.services.run_contract import execution_payload
from harako_gpu.core.provenance import approval_hash_for, plan_id_for
from harako_gpu.services.workflow_backends import (
    HARAKO_NATIVE_V1, NFCORE_REFERENCE, default_workflow_backend_for_new_plan,
)


IS_GENUINE_NATIVE_LINUX = (
    platform.system() == "Linux"
    and "microsoft" not in platform.release().casefold()
)
native_linux_planning = pytest.mark.skipif(
    not IS_GENUINE_NATIVE_LINUX,
    reason="requires genuine native Linux filesystem/path semantics",
)


def fixture_files(tmp_path: Path):
    reads = tmp_path / "reads"
    reads.mkdir()
    for name in ("A_R1.fastq.gz", "A_R2.fastq.gz", "B_R1.fastq.gz", "B_R2.fastq.gz"):
        (reads / name).write_bytes(b"fixture")
    samplesheet = tmp_path / "samples.csv"
    with samplesheet.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sample", "condition", "fastq_1", "fastq_2", "strandedness", "library_protocol"])
        writer.writeheader()
        writer.writerow({"sample": "A", "condition": "control", "fastq_1": "reads/A_R1.fastq.gz", "fastq_2": "reads/A_R2.fastq.gz", "strandedness": "auto", "library_protocol": "full_length"})
        writer.writerow({"sample": "B", "condition": "treated", "fastq_1": "reads/B_R1.fastq.gz", "fastq_2": "reads/B_R2.fastq.gz", "strandedness": "auto", "library_protocol": "full_length"})
    fasta = tmp_path / "genome.fa"
    gtf = tmp_path / "genes.gtf"
    transcript_fasta = tmp_path / "transcripts.fa"
    fasta.write_text(">chr1\nACGT\n", encoding="utf-8")
    gtf.write_text("chr1\ttest\texon\t1\t4\t.\t+\t.\tgene_id \"g1\";\n", encoding="utf-8")
    transcript_fasta.write_text(">tx1\nACGT\n", encoding="utf-8")
    index = tmp_path / "salmon-index"
    index.mkdir()
    manifest = tmp_path / "salmon-index-manifest.json"
    manifest.write_text(json.dumps({"identity": {
        "salmon_index_id": "fixture-index",
        "index_path": str(index),
        "index_builder_version": "1.10.3",
        "index_builder_image_digest": "sha256:f83ebb158845ee8138d793347f83b92c75e83c58dd8f4600c6fea2a2453ef08e",
        "transcript_fasta_sha256": hashlib.sha256(transcript_fasta.read_bytes()).hexdigest(),
        "genome_fasta_sha256": hashlib.sha256(fasta.read_bytes()).hexdigest(),
        "decoys_sha256": "c" * 64,
        "index_parameters": ["-k", "31", "decoy_aware_gentrome"],
        "index_manifest_sha256": "d" * 64,
        "schema_version": 1,
    }}), encoding="utf-8")
    return samplesheet, fasta, gtf, transcript_fasta, manifest


def profile_manifest(tmp_path: Path, profile_id: str, fasta: Path, gtf: Path,
                     transcript_fasta: Path) -> Path:
    profile = get_profile(profile_id)
    index = tmp_path / f"{profile_id}-index"
    index.mkdir(exist_ok=True)
    manifest = tmp_path / f"{profile_id}-index.json"
    manifest.write_text(json.dumps({
        "profile_id": profile.profile_id,
        "index_id": f"{profile.profile_id}-fixture",
        "path": str(index),
        "builder_version": profile.version,
        "image_identity": profile.image_identity,
        "transcript_source_sha256": hashlib.sha256(transcript_fasta.read_bytes()).hexdigest(),
        "genome_source_sha256": hashlib.sha256(fasta.read_bytes()).hexdigest(),
        "gtf_sha256": hashlib.sha256(gtf.read_bytes()).hexdigest(),
        "tx2gene_sha256": "e" * 64,
        "manifest_sha256": "f" * 64,
    }), encoding="utf-8")
    return manifest


def create(tmp_path: Path, **overrides):
    samplesheet, fasta, gtf, transcript_fasta, manifest = fixture_files(tmp_path)
    values = dict(
        samplesheet=samplesheet, plan_dir=tmp_path / "plan", output_root=tmp_path / "out",
        work_root=tmp_path / "work", fasta=fasta, gtf=gtf, bam_retention=BamRetention.KEEP,
        gpu_selection="all", memory_mode=MemoryMode.STANDARD, species="mouse", assembly="GRCm39",
        annotation_provider="Ensembl", annotation_release="113", project_slug="study-one", target="windows",
        salmon_index_manifest=manifest, transcript_fasta=transcript_fasta,
        salmon_2_5_1_index_manifest=profile_manifest(
            tmp_path, "salmon_2_5_1_deterministic", fasta, gtf, transcript_fasta,
        ),
    )
    values.update(overrides)
    if values.get("quantification_mode") == "compare-both":
        values.setdefault("salmon_1_10_3_index_manifest", profile_manifest(
            tmp_path, "salmon_1_10_3_compatibility", fasta, gtf, transcript_fasta,
        ))
    return create_plan(**values)


def test_plan_create_writes_required_nonexecuting_artifacts(tmp_path: Path) -> None:
    plan = create(tmp_path)
    destination = tmp_path / "plan"
    assert {path.name for path in destination.iterdir()} == {
        "plan.json", "nf-params.json", "nextflow.config", "command-preview.txt",
        "warnings.json", "nf-samplesheet.csv",
    }
    params = json.loads((destination / "nf-params.json").read_text(encoding="utf-8"))
    assert params["use_parabricks_star"] is True
    assert params["skip_pseudo_alignment"] is True
    assert "pseudo_aligner" not in params
    assert plan.quantification["backend"] == "fastq_salmon"
    assert plan.quantification["mode"] == "recommended_only"
    assert plan.quantification["primary_profile_id"] == "salmon_2_5_1_deterministic"
    assert plan.quantification["downstream_primary_profile_id"] == "salmon_2_5_1_deterministic"
    assert "genome" not in params
    assert plan.plan_id != plan.approval_hash
    assert validate_plan_file(destination / "plan.json")["valid"] is True


def test_workflow_backend_is_explicit_and_changes_approval_identity(tmp_path: Path) -> None:
    reference_root = tmp_path / "reference"
    native_root = tmp_path / "native"
    reference_root.mkdir()
    native_root.mkdir()
    reference = create(reference_root)
    star_index = native_root / "star-index"
    star_index.mkdir()
    native = create(
        native_root,
        workflow_backend="harako-native-v1",
        star_index=star_index,
    )
    assert reference.workflow_backend == NFCORE_REFERENCE
    assert reference.runtime_image_closure == "nfcore-rnaseq-3.26.0-full-human-images-v1"
    assert native.workflow_backend == HARAKO_NATIVE_V1
    assert native.alignment_backend == "parabricks_star"
    assert native.processed_fastq_contract == "harako-fastp-1.0.1-fixed-v1"
    assert native.runtime_image_closure == "harako-native-v1-minimal-images-v1"
    assert native.approval_hash != reference.approval_hash
    validated = validate_plan_file(native_root / "plan/plan.json")
    assert validated["workflow_backend"] == HARAKO_NATIVE_V1


def test_historical_plan_without_backend_retains_nfcore_hash_semantics(tmp_path: Path) -> None:
    create(tmp_path)
    path = tmp_path / "plan/plan.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in (
        "workflow_backend", "alignment_backend", "processed_fastq_contract",
        "output_artifact_contract", "runtime_image_closure", "resource_contract_id",
    ):
        payload.pop(key)
    execution = execution_payload(payload)
    payload["plan_id"] = plan_id_for(execution)
    payload["approval_hash"] = approval_hash_for(execution)
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = validate_plan_file(path)
    assert result["workflow_backend"] == NFCORE_REFERENCE
    assert result["alignment_backend"] == "parabricks_star"


def test_new_plan_backend_selector_is_platform_neutral() -> None:
    report_root = Path(__file__).resolve().parents[1] / "docs/qualification"

    native = default_workflow_backend_for_new_plan(
        requested=None,
        target="linux",
        host_profile_id="ubuntu_native_rtx3090_ram128_v1",
        host_receipt_validated=True,
        qualification_report_root=report_root,
    )
    assert native.workflow_backend == HARAKO_NATIVE_V1

    explicit_reference = default_workflow_backend_for_new_plan(
        requested="nfcore-rnaseq-3-26-reference",
        target="linux",
        host_profile_id="ubuntu_native_rtx3090_ram128_v1",
        host_receipt_validated=True,
        qualification_report_root=report_root,
    )
    assert explicit_reference.workflow_backend == NFCORE_REFERENCE

    windows_default = default_workflow_backend_for_new_plan(
        requested=None,
        target="windows",
        host_profile_id="ubuntu_native_rtx3090_ram128_v1",
        host_receipt_validated=True,
        qualification_report_root=report_root,
    )
    assert windows_default.workflow_backend == NFCORE_REFERENCE

    missing_receipt = default_workflow_backend_for_new_plan(
        requested=None,
        target="linux",
        host_profile_id="ubuntu_native_rtx3090_ram128_v1",
        host_receipt_validated=False,
        qualification_report_root=report_root,
    )
    assert missing_receipt.workflow_backend == NFCORE_REFERENCE


@native_linux_planning
def test_new_qualified_ubuntu_plan_defaults_native_on_genuine_linux(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import harako_gpu.services.planning as planning

    monkeypatch.setattr(planning, "evaluate_capability", lambda **_kwargs: SimpleNamespace(
        status=planning.CapabilityStatus.AVAILABLE_QUALIFIED,
        reference_pack_id="fixture-reference",
        as_dict=lambda: {
            "status": "AVAILABLE_QUALIFIED",
            "host_profile_id": "ubuntu_native_rtx3090_ram128_v1",
        },
    ))
    receipt = SimpleNamespace(validate=lambda **_kwargs: None)

    native_root = tmp_path / "native"
    native_root.mkdir()
    native_star = native_root / "star-index"
    native_star.mkdir()
    native = create(
        native_root,
        target="linux",
        host_profile_id="ubuntu_native_rtx3090_ram128_v1",
        host_qualification_receipt=receipt,
        qualification_report_root=Path(__file__).resolve().parents[1] / "docs/qualification",
        star_index=native_star,
    )
    assert native.workflow_backend == HARAKO_NATIVE_V1

    reference_root = tmp_path / "reference"
    reference_root.mkdir()
    explicit_reference = create(
        reference_root,
        target="linux",
        host_profile_id="ubuntu_native_rtx3090_ram128_v1",
        host_qualification_receipt=receipt,
        qualification_report_root=Path(__file__).resolve().parents[1] / "docs/qualification",
        workflow_backend="nfcore-rnaseq-3-26-reference",
    )
    assert explicit_reference.workflow_backend == NFCORE_REFERENCE


def test_native_linux_target_rejects_windows_paths() -> None:
    with pytest.raises(
        ValueError,
        match="Windows paths require explicit WSL conversion before Linux/WSL planning",
    ):
        reject_mixed_path_context(
            {"read_1": r"C:\harako-fixture\reads\R1.fastq.gz"},
            target="linux",
        )

    assert reject_mixed_path_context(
        {"read_1": "/harako-fixture/reads/R1.fastq.gz"},
        target="linux",
    ) is None


def test_unknown_workflow_backend_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown workflow backend"):
        create(tmp_path, workflow_backend="arbitrary-backend")


def test_compare_both_requires_and_freezes_primary_profile(tmp_path: Path) -> None:
    (tmp_path / "missing").mkdir()
    with pytest.raises(ValueError, match="explicit primary"):
        create(tmp_path / "missing", quantification_mode="compare-both")
    (tmp_path / "valid").mkdir()
    plan = create(tmp_path / "valid", quantification_mode="compare-both",
                  primary_quantification_profile="salmon_1_10_3_compatibility")
    assert plan.quantification["secondary_profile_id"] == "salmon_2_5_1_deterministic"
    assert plan.quantification["downstream_primary_profile_id"] == "salmon_1_10_3_compatibility"


def test_capacity_plan_freezes_unstranded_index_and_resource_contract(tmp_path: Path) -> None:
    plan = create(
        tmp_path, explicit_library_type="U", star_index=tmp_path / "star-index",
        star_index_sjdb_overhang=74, qualification_resource_contract="full_human_47gib_probe_v1",
    )
    assert plan.quantification["explicit_library_type"] == "U"
    assert plan.quantification["parabricks_star_sjdb_overhang"] == 74
    assert plan.quantification["qualification_resource_contract"] == "full_human_47gib_probe_v1"


def test_full_human_plan_derives_fixed_star_overhang_without_cli_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    digests = {
        "genome.fa": "e49b92b3e4f321bf254c042f25b726d9931c4d74c7523e8b6bb530e63b0cfd4b",
        "genes.gtf": "8eb596086228540c93ccf56fbb6601fd99f19a6df2cecdde239af423e5db0729",
        "transcripts.fa": "c41a37f792b10399838246200dbaf54a334ec3f514cd36545bb2f9c9995b27ac",
    }
    import harako_gpu.services.planning as planning
    real_sha = planning.sha256_path
    monkeypatch.setattr(planning, "sha256_path", lambda path: digests.get(path.name, real_sha(path)))
    monkeypatch.setattr(planning, "_profile_index_from_manifest", lambda path, profile_id: planning.ProfileIndex(
        profile_id=profile_id, index_id="fixed-full-human", path=str(tmp_path / f"{profile_id}-index"),
        builder_version=get_profile(profile_id).version,
        image_identity=get_profile(profile_id).image_identity,
        transcript_source_sha256=digests["transcripts.fa"],
        genome_source_sha256=digests["genome.fa"], gtf_sha256=digests["genes.gtf"],
        tx2gene_sha256="e" * 64, manifest_sha256="f" * 64,
    ))
    monkeypatch.setattr(planning, "evaluate_capability", lambda **_kwargs: SimpleNamespace(
        status=planning.CapabilityStatus.AVAILABLE_QUALIFIED,
        reference_pack_id="human_grch38p14_gencode49_harako_gpu_v1",
        as_dict=lambda: {"status": "AVAILABLE_QUALIFIED"},
    ))
    star = tmp_path / "star-index"
    star.mkdir()
    plan = create(
        tmp_path, star_index=star, star_index_sjdb_overhang=None,
        host_profile_id="ubuntu_native_rtx3090_ram128_v1",
        alignment_profile_id="parabricks_star_one_pass_workstation",
    )
    assert plan.quantification["parabricks_star_sjdb_overhang"] == 74


def test_capacity_plan_rejects_arbitrary_star_and_resource_contracts(tmp_path: Path) -> None:
    (tmp_path / "overhang").mkdir()
    with pytest.raises(ValueError, match="sjdbOverhang"):
        create(tmp_path / "overhang", star_index_sjdb_overhang=100)
    (tmp_path / "resource").mkdir()
    with pytest.raises(ValueError, match="resource contract"):
        create(tmp_path / "resource", qualification_resource_contract="arbitrary")


def test_discard_plan_records_contract_only_warning(tmp_path: Path) -> None:
    plan = create(tmp_path, bam_retention=BamRetention.DISCARD_AFTER_VALIDATION)
    assert plan.backend_profile.profile_id == "gpu_alignment_bam_discard"
    assert any("no deletion" in warning for warning in plan.warnings)


def test_low_memory_candidate_does_not_claim_qualification(tmp_path: Path) -> None:
    plan = create(tmp_path, memory_mode=MemoryMode.LOW_MEMORY_CANDIDATE)
    assert any("scientifically unqualified" in warning for warning in plan.warnings)
    assert "fixed --low-memory mapping" in (tmp_path / "plan" / "nextflow.config").read_text(encoding="utf-8")
    params = json.loads((tmp_path / "plan" / "nf-params.json").read_text(encoding="utf-8"))
    assert params["extra_star_align_args"] == "--low-memory"
    assert params["skip_markduplicates"] is True
    assert plan.nextflow_environment == {"NXF_VER": "25.04.3"}
    assert plan.minimum_nextflow_version == "25.04.3"
    assert plan.qualified_nextflow_version == "25.04.3"


def test_plan_artifacts_are_not_overwritten(tmp_path: Path) -> None:
    create(tmp_path)
    samplesheet, fasta, gtf = tmp_path / "samples.csv", tmp_path / "genome.fa", tmp_path / "genes.gtf"
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        create_plan(
            samplesheet=samplesheet, plan_dir=tmp_path / "plan", output_root=tmp_path / "out",
            work_root=tmp_path / "work", fasta=fasta, gtf=gtf, bam_retention=BamRetention.KEEP,
            gpu_selection="all", memory_mode=MemoryMode.STANDARD, species="mouse", assembly="GRCm39",
            annotation_provider="Ensembl", annotation_release="113", project_slug="study-one", target="windows",
            salmon_index_manifest=tmp_path / "salmon-index-manifest.json",
            salmon_2_5_1_index_manifest=tmp_path / "salmon_2_5_1_deterministic-index.json",
            transcript_fasta=tmp_path / "transcripts.fa",
        )


def test_validation_rejects_tampered_unpinned_revision(tmp_path: Path) -> None:
    create(tmp_path)
    path = tmp_path / "plan" / "plan.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["backend_profile"]["nf_core_revision"] = "latest"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="pinned"):
        validate_plan_file(path)


def _recommended_only_values(tmp_path: Path) -> dict[str, object]:
    samplesheet, fasta, gtf, transcript_fasta, _legacy = fixture_files(tmp_path)
    index = tmp_path / "salmon-2.5.1-index"
    index.mkdir()
    profile = get_profile("salmon_2_5_1_deterministic")
    manifest = tmp_path / "salmon-2.5.1-profile-index.json"
    manifest.write_text(json.dumps({
        "profile_id": profile.profile_id,
        "index_id": "salmon-2.5.1-test",
        "path": str(index),
        "builder_version": profile.version,
        "image_identity": profile.image_identity,
        "transcript_source_sha256": hashlib.sha256(transcript_fasta.read_bytes()).hexdigest(),
        "genome_source_sha256": hashlib.sha256(fasta.read_bytes()).hexdigest(),
        "gtf_sha256": hashlib.sha256(gtf.read_bytes()).hexdigest(),
        "tx2gene_sha256": "e" * 64,
        "manifest_sha256": "f" * 64,
    }), encoding="utf-8")
    return {
        "samplesheet": samplesheet,
        "plan_dir": tmp_path / "plan",
        "output_root": tmp_path / "out",
        "work_root": tmp_path / "work",
        "fasta": fasta,
        "gtf": gtf,
        "transcript_fasta": transcript_fasta,
        "salmon_2_5_1_index_manifest": manifest,
        "quantification_mode": "recommended-only",
        "primary_quantification_profile": "salmon_2_5_1_deterministic",
        "bam_retention": BamRetention.KEEP,
        "gpu_selection": "all",
        "memory_mode": MemoryMode.STANDARD,
        "species": "mouse",
        "assembly": "GRCm39",
        "annotation_provider": "Ensembl",
        "annotation_release": "113",
        "project_slug": "recommended-only",
        "target": "windows",
    }


def test_compatibility_only_requires_only_salmon_1103_profile_manifest(tmp_path: Path) -> None:
    values = _recommended_only_values(tmp_path)
    fasta = values["fasta"]
    gtf = values["gtf"]
    transcript_fasta = values["transcript_fasta"]
    values.update({
        "plan_dir": tmp_path / "compat-plan",
        "quantification_mode": "compatibility-only",
        "primary_quantification_profile": "salmon_1_10_3_compatibility",
        "salmon_2_5_1_index_manifest": tmp_path / "must-not-open-251.json",
        "salmon_1_10_3_index_manifest": profile_manifest(
            tmp_path, "salmon_1_10_3_compatibility", fasta, gtf, transcript_fasta,
        ),
    })
    (tmp_path / "must-not-open-251.json").write_text("not json\n", encoding="utf-8")
    plan = create_plan(**values)
    assert set(plan.quantification["profiles"]) == {"salmon_1_10_3_compatibility"}


def test_compare_both_requires_both_profile_manifests(tmp_path: Path) -> None:
    values = _recommended_only_values(tmp_path)
    values.update({
        "quantification_mode": "compare-both",
        "primary_quantification_profile": "salmon_2_5_1_deterministic",
    })
    with pytest.raises(ValueError, match="requires both"):
        create_plan(**values)


def test_recommended_only_requires_only_salmon_251_profile_manifest(tmp_path: Path) -> None:
    plan = create_plan(**_recommended_only_values(tmp_path))
    assert plan.quantification["primary_profile_id"] == "salmon_2_5_1_deterministic"
    assert plan.quantification["secondary_profile_id"] is None


def test_recommended_only_does_not_open_unselected_legacy_or_1103_manifest(tmp_path: Path) -> None:
    values = _recommended_only_values(tmp_path)
    legacy = tmp_path / "must-not-open-legacy.json"
    compatibility = tmp_path / "must-not-open-1103.json"
    legacy.write_text("not json\n", encoding="utf-8")
    compatibility.write_text("not json\n", encoding="utf-8")
    values.update({
        "salmon_index_manifest": legacy,
        "salmon_1_10_3_index_manifest": compatibility,
    })
    plan = create_plan(**values)
    assert set(plan.quantification["profiles"]) == {"salmon_2_5_1_deterministic"}
