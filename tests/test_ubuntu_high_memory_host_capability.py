from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from harako_gpu.adapters.docker import DockerImageContract
from harako_gpu.adapters.execution_context import parse_execution_context
from harako_gpu.core.capabilities import BamOutputMode, CapabilityStatus
from harako_gpu.services.alignment_profiles import ONE_PASS_PROFILE_ID, TWO_PASS_PROFILE_ID
from harako_gpu.services.capabilities import (
    FULL_HUMAN_REFERENCE_PACK_ID, FULL_HUMAN_SHA, SMALL_REFERENCE_PACK_ID,
    SMALL_REFERENCE_SHA, evaluate_capability, validate_capability_snapshot_version,
)
from harako_gpu.services.host_profiles import (
    FULL_HUMAN_TASK_IMAGES, HOST_PROFILES, ONE_PASS_REPORT_ID, ONE_PASS_REPORT_SHA256,
    ONE_PASS_RESOURCE_CONTRACT_ID, PARABRICKS_AMD64_MANIFEST_DIGEST,
    PARABRICKS_CONFIG_IMAGE_ID, PARABRICKS_MANIFEST_LIST_DIGEST,
    PARABRICKS_SOURCE_REFERENCE, PLUGIN_CLOSURE_ID, SALMON_251_INDEX_ID,
    STAR_INDEX_ID, TASK_IMAGE_CLOSURE_ID, TERMINAL_RESULTS_ARCHIVE_POLICY,
    TWO_PASS_REPORT_ID, TWO_PASS_REPORT_SHA256, TWO_PASS_RESOURCE_CONTRACT_ID,
    UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID, WINDOWS_HOST_PROFILE_ID,
    HostQualificationReceipt, OfflinePlatformImageProvenance, PluginClosureReceipt,
    featurecounts_contract, get_host_profile, select_resource_contract,
    runtime_quantification_image_contract, task_image_contract_for_role,
    validate_task_image_closure,
)
from harako_gpu.services import host_profiles
from harako_gpu.services.runtime_validation_images import (
    bam_validator_freeze_payload,
    resolve_frozen_bam_validator_contract,
)
from harako_gpu.services.run_preparation import (
    PreparationContext, RuntimeRequirements, _alignment_params, _execution_config,
    validate_offline_runtime_closure,
)
from harako_gpu.commands.root import app


REPORT_ROOT = Path(__file__).resolve().parents[1] / "docs/qualification"
PROVENANCE_RECEIPT_SHA = "a" * 64
ARCHIVE_SHA = "b" * 64


def receipt(**changes: object) -> HostQualificationReceipt:
    values: dict[str, object] = {
        "schema_version": 1,
        "host_profile_id": UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
        "evidence_version": "ubuntu-high-memory-host-capability-v1",
        "qualification_report_sha256": {
            ONE_PASS_REPORT_ID: ONE_PASS_REPORT_SHA256,
            TWO_PASS_REPORT_ID: TWO_PASS_REPORT_SHA256,
        },
        "repository_commit": "27706b9fb65b3c3ccf965e39a582e7947be9482b",
        "repository_tree": "e2efd73c0ed85b5d8f3e4b5f9190167de10c16f2",
        "operating_system_family": "linux",
        "execution_context": "native_linux",
        "minimum_physical_ram_bytes": 128_000_000_000,
        "gpu_model": "NVIDIA GeForce RTX 3090",
        "minimum_vram_mib": 24_576,
        "resource_contract_ids": (ONE_PASS_RESOURCE_CONTRACT_ID, TWO_PASS_RESOURCE_CONTRACT_ID),
        "reference_pack_id": FULL_HUMAN_REFERENCE_PACK_ID,
        "star_index_id": STAR_INDEX_ID,
        "salmon_index_id": SALMON_251_INDEX_ID,
        "pipeline_version": "3.26.0",
        "pipeline_commit": "e7ca46272c8f9d5ceee3f71759f4ba551d3217a4",
        "plugin_closure_id": PLUGIN_CLOSURE_ID,
        "plugin_cache_inventory_sha256": "629fcd902958e2cb42a36ca77d083f4860800a984d67aa3f9f72e5f4fa93cd35",
        "task_image_closure_id": TASK_IMAGE_CLOSURE_ID,
        "task_image_closure_sha256": "4fc56c8eb1a0a7c7eea75f8dfbffbc459a9d0698e20313e094105e714a3c31bb",
        "archive_receipt_sha256": (
            "91c2afbbefbd0968f60d59df3ac57966d17c335fd2438edcd3f10ec5d000b68e",
            "71d5a3fa60c569d3ddf84c6696acf0d338379e012205a6c845ac69df5a5ad711",
        ),
        "parabricks_archive_sha256": ARCHIVE_SHA,
        "parabricks_provenance_receipt_sha256": PROVENANCE_RECEIPT_SHA,
        "product_docker_provenance_status": "VERIFIED",
        "created_at": "2026-08-19T00:00:00Z",
        "product_cli_verified": False,
    }
    values.update(changes)
    return HostQualificationReceipt.from_mapping(values)


def provenance(**changes: object) -> OfflinePlatformImageProvenance:
    values: dict[str, object] = {
        "schema_version": 1,
        "source_reference": PARABRICKS_SOURCE_REFERENCE,
        "source_manifest_list_digest": PARABRICKS_MANIFEST_LIST_DIGEST,
        "selected_platform": "linux/amd64",
        "platform_manifest_digest": PARABRICKS_AMD64_MANIFEST_DIGEST,
        "config_image_id": PARABRICKS_CONFIG_IMAGE_ID,
        "archive_sha256": ARCHIVE_SHA,
        "image_version_output": "pbrun 4.6.0-1",
        "executable_probe": "PASS",
        "provenance_receipt_sha256": PROVENANCE_RECEIPT_SHA,
    }
    values.update(changes)
    return OfflinePlatformImageProvenance.from_mapping(values)


def plugin() -> PluginClosureReceipt:
    return PluginClosureReceipt(
        1, "nf-schema", "2.5.1", "25.04.3",
        "629fcd902958e2cb42a36ca77d083f4860800a984d67aa3f9f72e5f4fa93cd35",
        "78285a59f38118ecaa3b875620f01c1f1712c97a834e17cb603f6c5e64f8d2e6", "PASS",
    )


def image_inspections() -> dict[str, dict[str, object]]:
    observed = {}
    for item in FULL_HUMAN_TASK_IMAGES:
        contract = item.contract
        observed[contract.reference] = {
            "Id": contract.identity if contract.identity_kind == "image_id" else "sha256:" + "0" * 64,
            "RepoDigests": (
                [f"{contract.repository}@{contract.identity}"]
                if contract.identity_kind == "repo_digest" else []
            ),
        }
    return observed


def ubuntu_capability(profile_id: str, *, installed: bool = True,
                      p: OfflinePlatformImageProvenance | None = None,
                      execution_context: str = "native_linux") -> CapabilityStatus:
    result = evaluate_capability(
        reference={**FULL_HUMAN_SHA, "reference_pack_id": FULL_HUMAN_REFERENCE_PACK_ID},
        bam_output_mode=BamOutputMode.KEEP, alignment_profile_id=profile_id,
        quantification_mode="recommended_only", primary_profile_id="salmon_2_5_1_deterministic",
        secondary_profile_id=None, execution_context=execution_context,
        host_profile_id=UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
        host_receipt=receipt() if installed else None, report_root=REPORT_ROOT,
        parabricks_provenance=p if p is not None else (provenance() if installed else None),
        observed_parabricks_image={"Id": PARABRICKS_CONFIG_IMAGE_ID},
    )
    return result.status


def test_fixed_host_catalog_and_hardware_alone_does_not_qualify() -> None:
    assert set(HOST_PROFILES) == {WINDOWS_HOST_PROFILE_ID, UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID}
    assert get_host_profile(WINDOWS_HOST_PROFILE_ID).execution_context == "wsl2:Ubuntu"
    assert get_host_profile(UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID).minimum_physical_ram_bytes == 128_000_000_000
    assert ubuntu_capability(ONE_PASS_PROFILE_ID, installed=False) is CapabilityStatus.BLOCKED_PROVENANCE
    native_small_without_receipt = evaluate_capability(
        reference=SMALL_REFERENCE_SHA, bam_output_mode=BamOutputMode.KEEP,
        alignment_profile_id=ONE_PASS_PROFILE_ID, quantification_mode="recommended_only",
        primary_profile_id="salmon_2_5_1_deterministic", secondary_profile_id=None,
        execution_context="native_linux", host_profile_id=UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
    )
    assert native_small_without_receipt.status is CapabilityStatus.BLOCKED_PROVENANCE
    with pytest.raises(ValueError, match="Unknown host profile"):
        get_host_profile("ram-is-not-a-qualification")


def test_ubuntu_bam_validator_contract_is_the_unique_samtools_closure_role() -> None:
    contract = task_image_contract_for_role(UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID, "SAMTOOLS")
    assert contract is not None
    assert contract.reference == "community.wave.seqera.io/library/htslib_samtools:1.23.1--5b6bb4ede7e612e5"
    assert contract.identity == "sha256:b762af53a769d82aa0111bfbc4574c8bb8c07f9257a8e09c8403c4f540a10a07"
    assert contract.identity_kind == "image_id"
    assert contract.execution_reference == contract.identity


def test_ubuntu_bam_validator_contract_rejects_missing_and_duplicate_roles(monkeypatch) -> None:
    original = host_profiles.FULL_HUMAN_TASK_IMAGES
    without = tuple(item for item in original if item.process_role != "SAMTOOLS")
    monkeypatch.setattr(host_profiles, "FULL_HUMAN_TASK_IMAGES", without)
    with pytest.raises(ValueError, match="exactly one SAMTOOLS"):
        task_image_contract_for_role(UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID, "SAMTOOLS")
    samtools = next(item for item in original if item.process_role == "SAMTOOLS")
    monkeypatch.setattr(host_profiles, "FULL_HUMAN_TASK_IMAGES", (*original, samtools))
    with pytest.raises(ValueError, match="exactly one SAMTOOLS"):
        task_image_contract_for_role(UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID, "SAMTOOLS")


def test_ubuntu_bam_validator_contract_rejects_wrong_identity_and_kind(monkeypatch) -> None:
    original = host_profiles.FULL_HUMAN_TASK_IMAGES
    for contract in (
        DockerImageContract(
            "community.wave.seqera.io/library/htslib_samtools:1.23.1--5b6bb4ede7e612e5",
            "sha256:" + "0" * 64,
            "image_id",
        ),
        DockerImageContract(
            "community.wave.seqera.io/library/htslib_samtools:1.23.1--5b6bb4ede7e612e5",
            "sha256:b762af53a769d82aa0111bfbc4574c8bb8c07f9257a8e09c8403c4f540a10a07",
            "repo_digest",
        ),
    ):
        replacement = tuple(
            host_profiles.TaskImageRequirement("SAMTOOLS", contract)
            if item.process_role == "SAMTOOLS" else item
            for item in original
        )
        monkeypatch.setattr(host_profiles, "FULL_HUMAN_TASK_IMAGES", replacement)
        with pytest.raises(ValueError, match="identity mismatch"):
            task_image_contract_for_role(UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID, "SAMTOOLS")


def test_runtime_validation_freeze_and_retained_ubuntu_fail_closed(tmp_path: Path) -> None:
    payload = bam_validator_freeze_payload(UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID)
    assert payload["bam_validator"]["identity"] == (
        "sha256:b762af53a769d82aa0111bfbc4574c8bb8c07f9257a8e09c8403c4f540a10a07"
    )
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    (frozen / "plan.json").write_text(json.dumps({
        "capability_snapshot": {"result": {"host_profile_id": UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID}}
    }))
    with pytest.raises(ValueError, match="lacks a frozen SAMTOOLS closure"):
        resolve_frozen_bam_validator_contract(tmp_path)
    (frozen / "runtime-validation-images.json").write_text(json.dumps(payload))
    resolved = resolve_frozen_bam_validator_contract(tmp_path)
    assert resolved.contract.identity == payload["bam_validator"]["identity"]
    assert resolved.resolution_source == "dedicated_frozen_runtime_validation_images"


def test_receipt_is_exact_and_invalid_identity_is_blocked() -> None:
    receipt().validate(report_root=REPORT_ROOT)
    with pytest.raises(ValueError, match="repository identity"):
        receipt(repository_commit="0" * 40).validate(report_root=REPORT_ROOT)


@pytest.mark.parametrize("profile_id", (ONE_PASS_PROFILE_ID, TWO_PASS_PROFILE_ID))
def test_ubuntu_full_human_alignment_is_available_only_with_receipts(profile_id: str) -> None:
    assert ubuntu_capability(profile_id) is CapabilityStatus.AVAILABLE_QUALIFIED


@pytest.mark.parametrize("profile_id", (ONE_PASS_PROFILE_ID, TWO_PASS_PROFILE_ID))
def test_public_native_linux_execution_context_is_normalized(profile_id: str) -> None:
    assert ubuntu_capability(
        profile_id, execution_context="native-linux",
    ) is CapabilityStatus.AVAILABLE_QUALIFIED


def test_windows_full_human_bam_remains_unsupported_and_small_reference_unchanged() -> None:
    for profile_id in (ONE_PASS_PROFILE_ID, TWO_PASS_PROFILE_ID):
        result = evaluate_capability(
            reference=FULL_HUMAN_SHA, bam_output_mode=BamOutputMode.KEEP,
            alignment_profile_id=profile_id, quantification_mode="recommended_only",
            primary_profile_id="salmon_2_5_1_deterministic", secondary_profile_id=None,
        )
        assert result.status is CapabilityStatus.UNSUPPORTED_HOST_MEMORY
        assert "no CPU STAR fallback" in result.forbidden_fallback
    small = evaluate_capability(
        reference={**SMALL_REFERENCE_SHA, "reference_pack_id": SMALL_REFERENCE_PACK_ID},
        bam_output_mode=BamOutputMode.KEEP, alignment_profile_id=ONE_PASS_PROFILE_ID,
        quantification_mode="recommended_only", primary_profile_id="salmon_2_5_1_deterministic",
        secondary_profile_id=None,
    )
    assert small.status is CapabilityStatus.AVAILABLE_QUALIFIED


def test_ubuntu_quantification_only_compatibility_routes_are_limited() -> None:
    base = dict(
        reference=FULL_HUMAN_SHA, bam_output_mode=BamOutputMode.NONE,
        alignment_profile_id=None, execution_context="native_linux",
        host_profile_id=UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID, host_receipt=receipt(),
        report_root=REPORT_ROOT, primary_profile_id="salmon_2_5_1_deterministic",
    )
    result = evaluate_capability(**base, quantification_mode="recommended_only", secondary_profile_id=None)
    assert result.status is CapabilityStatus.AVAILABLE_QUALIFIED and not result.gpu_used
    comparison = evaluate_capability(
        **base, quantification_mode="compare_both", secondary_profile_id="salmon_1_10_3_compatibility",
    )
    assert comparison.status is CapabilityStatus.AVAILABLE_WITH_LIMITATION
    assert "bounded numerical" in comparison.explanation
    assert "not byte-exact" in comparison.explanation


def test_resource_contracts_are_host_reference_and_profile_specific() -> None:
    one = select_resource_contract(UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID, FULL_HUMAN_REFERENCE_PACK_ID, ONE_PASS_PROFILE_ID)
    two = select_resource_contract(UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID, FULL_HUMAN_REFERENCE_PACK_ID, TWO_PASS_PROFILE_ID)
    assert (one.memory_gb, one.cpus, one.memory_bytes) == (42, 12, 45_097_156_608)
    assert (two.memory_gb, two.cpus, two.memory_bytes) == (96, 12, 103_079_215_104)
    assert one.process_selector == two.process_selector == "NFCORE_RNASEQ:RNASEQ:ALIGN_STAR:PARABRICKS_RNA_FQ2BAM"
    assert select_resource_contract(WINDOWS_HOST_PROFILE_ID, FULL_HUMAN_REFERENCE_PACK_ID, TWO_PASS_PROFILE_ID) is None


def test_two_pass_execution_config_has_one_scoped_96gb_override() -> None:
    plan = {
        "backend_profile": {"gpu_selection": "all", "qualification_debug_mode": "disabled"},
        "alignment_profile_id": TWO_PASS_PROFILE_ID,
        "quantification": {"qualification_resource_contract": TWO_PASS_RESOURCE_CONTRACT_ID},
        "capability_snapshot": {"result": {
            "host_profile_id": UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
            "reference_pack_id": FULL_HUMAN_REFERENCE_PACK_ID,
        }},
    }
    config = _execution_config(plan)
    assert config.count("96.GB") == 1 and "cpus = 12" in config
    assert config.count("NFCORE_RNASEQ:RNASEQ:ALIGN_STAR:PARABRICKS_RNA_FQ2BAM") == 1
    assert "42.GB" not in config
    plan["backend_profile"]["qualification_debug_mode"] = "x3"
    with pytest.raises(ValueError, match="cannot be replaced"):
        _execution_config(plan)


def test_gencode_49_featurecounts_is_fixed_without_gencode_flag() -> None:
    assert featurecounts_contract(FULL_HUMAN_REFERENCE_PACK_ID, group_type="gene_type") == ("exon", "gene_type")
    with pytest.raises(ValueError, match="GENCODE 49"):
        featurecounts_contract(FULL_HUMAN_REFERENCE_PACK_ID, group_type="gene_id")
    assert featurecounts_contract("other", feature_type="gene", group_type="gene_id") == ("gene", "gene_id")
    params = _alignment_params({
        "reference": {"assembly": "GRCh38.p14", "annotation_provider": "GENCODE",
                      "annotation_release": "49", "fasta_path": "/ref.fa", "gtf_path": "/ref.gtf"},
        "backend_profile": {"qualification_debug_mode": "disabled"},
        "quantification": {"parabricks_star_sjdb_overhang": 74},
        "alignment_profile_id": ONE_PASS_PROFILE_ID,
    }, {}, run_dir="/run", work_dir="/work")
    assert params["featurecounts_feature_type"] == "exon"
    assert params["featurecounts_group_type"] == "gene_type"
    assert "gencode" not in params


def test_pinned_plugin_closure_has_no_unversioned_fallback() -> None:
    plugin().validate()
    with pytest.raises(ValueError, match="Pinned nf-schema"):
        replace(plugin(), plugin_version="latest").validate()


@pytest.mark.parametrize("missing_index", range(18))
def test_each_missing_task_image_is_blocked_before_launch(missing_index: int) -> None:
    observed = image_inspections()
    del observed[FULL_HUMAN_TASK_IMAGES[missing_index].contract.reference]
    with pytest.raises(ValueError, match="closure mismatch"):
        validate_task_image_closure(observed)


def test_complete_18_image_closure_and_required_late_images() -> None:
    validate_task_image_closure(image_inspections())
    roles = {item.process_role for item in FULL_HUMAN_TASK_IMAGES}
    assert len(FULL_HUMAN_TASK_IMAGES) == 18
    assert {"SUBREAD_FEATURECOUNTS", "UCSC_BEDCLIP", "QUALIMAP", "STRINGTIE"} <= roles
    overlay = runtime_quantification_image_contract(
        UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID, "salmon_2_5_1_deterministic",
    )
    assert overlay.identity == "sha256:6ec01c872926f446b20933ed8c948cd66eca2b49c93427d77370fb4a2e403cfe"
    assert runtime_quantification_image_contract(
        WINDOWS_HOST_PROFILE_ID, "salmon_2_5_1_deterministic",
    ) is None


@pytest.mark.parametrize(("change", "message"), (
    ({"selected_platform": "linux/arm64"}, "platform provenance"),
    ({"config_image_id": "sha256:" + "0" * 64}, "platform provenance"),
    ({"archive_sha256": "c" * 64}, "archive identity"),
    ({"image_version_output": "pbrun 4.7.0"}, "version/executable"),
))
def test_parabricks_provenance_keeps_manifest_platform_config_and_archive_distinct(
    change: dict[str, object], message: str,
) -> None:
    assert len({PARABRICKS_MANIFEST_LIST_DIGEST, PARABRICKS_AMD64_MANIFEST_DIGEST,
                PARABRICKS_CONFIG_IMAGE_ID}) == 3
    with pytest.raises(ValueError, match=message):
        provenance(**change).validate(
            observed_image={"Id": PARABRICKS_CONFIG_IMAGE_ID},
            expected_receipt_sha256=PROVENANCE_RECEIPT_SHA,
            expected_archive_sha256=ARCHIVE_SHA,
        )


def test_parabricks_runtime_image_id_and_receipt_identity_are_checked() -> None:
    with pytest.raises(ValueError, match="image ID identity mismatch"):
        provenance().validate(
            observed_image={"Id": "sha256:" + "0" * 64},
            expected_receipt_sha256=PROVENANCE_RECEIPT_SHA,
            expected_archive_sha256=ARCHIVE_SHA,
        )
    with pytest.raises(ValueError, match="receipt identity"):
        provenance().validate(
            observed_image={"Id": PARABRICKS_CONFIG_IMAGE_ID},
            expected_receipt_sha256="d" * 64,
            expected_archive_sha256=ARCHIVE_SHA,
        )


def test_offline_prepare_closure_missing_plugin_fails_closed() -> None:
    requirements = RuntimeRequirements(
        "gpu_bam_alignment", ("parabricks", "fastp", "salmon_2_5_1_deterministic"),
        True, True, True, True, True, True, UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID, True,
    )
    context = PreparationContext(
        parse_execution_context("native-linux"), "/pipeline", "/nextflow", {}, {},
        Path(__file__).resolve().parents[1], Mock(), host_receipt=receipt(),
        plugin_receipt=None, task_image_inspections=image_inspections(),
        parabricks_provenance=provenance(),
        parabricks_image_inspection={"Id": PARABRICKS_CONFIG_IMAGE_ID},
    )
    with pytest.raises(ValueError, match="installed host/plugin/image provenance receipts"):
        validate_offline_runtime_closure(requirements, context)


def test_terminal_archive_policy_never_authorizes_automatic_deletion() -> None:
    policy = TERMINAL_RESULTS_ARCHIVE_POLICY
    assert policy.active_work_storage == "local_ext4_ssd"
    assert policy.successful_terminal_storage == "verified_pax_archive_on_wd_gold"
    assert policy.failed_or_resumable_work == "retain_on_ssd"
    assert policy.deletion_mode == "explicit_only"


def test_v1_capability_snapshots_remain_parseable() -> None:
    assert validate_capability_snapshot_version("reference-aware-capability-v1") == "reference-aware-capability-v1"
    assert validate_capability_snapshot_version("reference-aware-capability-v2") == "reference-aware-capability-v2"
    with pytest.raises(ValueError, match="Unsupported capability matrix"):
        validate_capability_snapshot_version("v3")


def test_public_host_profile_provisioning_command_exists() -> None:
    result = CliRunner().invoke(app, ["host-profile", "--help"])
    assert result.exit_code == 0
    assert "provision" in result.stdout
