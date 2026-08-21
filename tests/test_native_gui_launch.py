from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from harako_gpu.adapters.execution_context import ExecutionContext, NATIVE_LINUX
from harako_gpu.adapters.gui_launcher import controller_argv
from harako_gpu.services import gui
from harako_gpu.services.alignment_profiles import ONE_PASS_PROFILE_ID, TWO_PASS_PROFILE_ID
from harako_gpu.services.capabilities import FULL_HUMAN_REFERENCE_PACK_ID
from harako_gpu.services.host_profiles import (
    ONE_PASS_RESOURCE_CONTRACT_ID,
    TWO_PASS_RESOURCE_CONTRACT_ID,
    UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
    WINDOWS_HOST_PROFILE_ID,
)
from harako_gpu.services.workflow_backends import HARAKO_NATIVE_V1, NFCORE_REFERENCE
from harako_gpu.ui import state
from harako_gpu.ui.pages import reference_capability, review_prepare


ROOT = Path(__file__).resolve().parents[1]


def _draft(**overrides: object) -> gui.GuiDraft:
    values = {
        "project_slug": "native-gui-test",
        "samples": ({
            "sample": "S1", "condition": "test",
            "fastq_1": "/runtime/inputs/S1_R1.fastq.gz",
            "fastq_2": "/runtime/inputs/S1_R2.fastq.gz",
            "strandedness": "unstranded", "library_protocol": "explicit",
        },),
        "reference_pack_id": FULL_HUMAN_REFERENCE_PACK_ID,
        "bam_output_mode": "keep",
        "alignment_profile_id": ONE_PASS_PROFILE_ID,
        "quantification_mode": "recommended_only",
        "primary_profile_id": "salmon_2_5_1_deterministic",
        "explicit_library_type": "U",
        "runtime_root": "/runtime",
        "output_root": "/runtime/results/native-gui-test",
        "work_root": "/runtime/work/native-gui-test",
        "execution_context": NATIVE_LINUX,
        "host_profile_id": UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
        "workflow_backend": HARAKO_NATIVE_V1,
    }
    values.update(overrides)
    return gui.GuiDraft(**values)


def _enable_valid_native_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    receipt = SimpleNamespace(product_cli_verified=True, validate=lambda **_kwargs: None)
    monkeypatch.setattr(
        gui.HostQualificationReceipt, "load",
        classmethod(lambda _cls, _path: receipt),
    )
    monkeypatch.setattr(gui, "harako_native_parity_evidence_valid", lambda: True)
    monkeypatch.setattr(gui, "get_reference", lambda *_args, **_kwargs: SimpleNamespace(
        reference_pack_id=FULL_HUMAN_REFERENCE_PACK_ID,
        reference_assets_cached=True,
        star_index_cached=True,
        salmon_251_index_cached=True,
        salmon_1103_index_cached=True,
    ))
    monkeypatch.setattr(gui, "validate_offline_runtime_closure", lambda *_args: None)
    monkeypatch.setattr(gui, "capability_for", lambda **_kwargs: SimpleNamespace(
        status=SimpleNamespace(value="AVAILABLE_QUALIFIED"),
        reason_code="NATIVE_HIGH_MEMORY_QUALIFIED", explanation="qualified",
    ))


def _context() -> SimpleNamespace:
    return SimpleNamespace(
        execution=ExecutionContext(NATIVE_LINUX, None),
        hardware_report={
            "host_ram_bytes": 128_000_000_000,
            "nvidia_gpus": ({
                "name": "NVIDIA GeForce RTX 3090",
                "total_vram_bytes": 24_576 * 1024**2,
            },),
        },
        host_receipt=SimpleNamespace(product_cli_verified=True),
        parabricks_provenance=SimpleNamespace(),
        parabricks_image_inspection={"Id": "sha256:fixed"},
    )


def _ready_storage() -> dict[str, object]:
    return {
        "status": "READY", "filesystems": ("ext4",),
        "free_bytes": 500 * 1024**3, "estimated_required_bytes": 100 * 1024**3,
        "operational_reserve_bytes": 5 * 1024**3,
        "active_output_root": "/runtime/results/native-gui-test",
        "active_work_root": "/runtime/work/native-gui-test",
    }


def test_native_gui_eligibility_requires_every_fixed_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_valid_native_contract(monkeypatch)
    result = gui.scientific_launch_eligibility(
        _draft(), context=_context(), storage_readiness=_ready_storage(),
        host_system="Linux", kernel_release="6.8.0-generic",
    )
    assert result.allowed
    assert result.workflow_backend == HARAKO_NATIVE_V1
    assert result.resource_contract_id == ONE_PASS_RESOURCE_CONTRACT_ID
    assert result.host_receipt_status == "VALID"
    assert result.asset_readiness["salmon_2_5_1_index"] is True
    assert result.matches(_draft())


@pytest.mark.parametrize(
    ("draft", "system", "release", "code"),
    (
        (_draft(execution_context="wsl2:Ubuntu"), "Windows", "10", "NATIVE_EXECUTION_CONTEXT_REQUIRED"),
        (_draft(host_profile_id=WINDOWS_HOST_PROFILE_ID), "Linux", "6.8", "HOST_PROFILE_UNQUALIFIED"),
        (_draft(), "Windows", "10", "GENUINE_NATIVE_LINUX_REQUIRED"),
        (_draft(), "Linux", "5.15.0-microsoft-standard", "GENUINE_NATIVE_LINUX_REQUIRED"),
    ),
)
def test_native_gui_eligibility_never_uses_ram_or_profile_string_alone(
    draft: gui.GuiDraft, system: str, release: str, code: str,
) -> None:
    result = gui.scientific_launch_eligibility(
        draft, host_system=system, kernel_release=release,
    )
    assert not result.allowed and result.blocker_code == code


def test_native_gui_missing_or_invalid_receipt_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gui.HostQualificationReceipt, "load",
        classmethod(lambda _cls, _path: (_ for _ in ()).throw(ValueError("receipt missing"))),
    )
    result = gui.scientific_launch_eligibility(
        _draft(), host_system="Linux", kernel_release="6.8",
    )
    assert not result.allowed
    assert result.blocker_code == "HOST_RECEIPT_INVALID"
    assert "receipt missing" in result.blocker_explanation


def test_native_gui_accepts_exact_product_cli_evidence_without_mutating_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = SimpleNamespace(product_cli_verified=False, validate=lambda **_kwargs: None)
    monkeypatch.setattr(
        gui.HostQualificationReceipt, "load",
        classmethod(lambda _cls, _path: receipt),
    )
    monkeypatch.setattr(gui, "product_cli_qualification_evidence_valid", lambda **_kwargs: True)
    monkeypatch.setattr(gui, "harako_native_parity_evidence_valid", lambda: True)
    monkeypatch.setattr(gui, "get_reference", lambda *_args, **_kwargs: SimpleNamespace(
        reference_pack_id=FULL_HUMAN_REFERENCE_PACK_ID,
        reference_assets_cached=True,
        star_index_cached=True,
        salmon_251_index_cached=True,
        salmon_1103_index_cached=True,
    ))
    monkeypatch.setattr(gui, "validate_offline_runtime_closure", lambda *_args: None)
    monkeypatch.setattr(gui, "capability_for", lambda **_kwargs: SimpleNamespace(
        status=SimpleNamespace(value="AVAILABLE_QUALIFIED"),
        reason_code="NATIVE_HIGH_MEMORY_QUALIFIED", explanation="qualified",
    ))
    result = gui.scientific_launch_eligibility(
        _draft(), context=_context(), storage_readiness=_ready_storage(),
        host_system="Linux", kernel_release="6.8",
    )
    assert result.allowed


def test_native_gui_changed_parity_report_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_valid_native_contract(monkeypatch)
    monkeypatch.setattr(gui, "harako_native_parity_evidence_valid", lambda: False)
    result = gui.scientific_launch_eligibility(
        _draft(), context=_context(), storage_readiness=_ready_storage(),
        host_system="Linux", kernel_release="6.8",
    )
    assert not result.allowed and result.blocker_code == "PARITY_EVIDENCE_INVALID"


@pytest.mark.parametrize(
    "hardware_report",
    (
        {
            "host_ram_bytes": 64 * 1024**3,
            "nvidia_gpus": ({
                "name": "NVIDIA GeForce RTX 3090", "total_vram_bytes": 24_576 * 1024**2,
            },),
        },
        {
            "host_ram_bytes": 128_000_000_000,
            "nvidia_gpus": ({
                "name": "NVIDIA GeForce RTX 4090", "total_vram_bytes": 24_576 * 1024**2,
            },),
        },
        {
            "host_ram_bytes": 128_000_000_000,
            "nvidia_gpus": ({
                "name": "NVIDIA GeForce RTX 3090", "total_vram_bytes": 20_000 * 1024**2,
            },),
        },
    ),
)
def test_native_gui_receipt_cannot_qualify_different_observed_hardware(
    monkeypatch: pytest.MonkeyPatch, hardware_report: dict[str, object],
) -> None:
    _enable_valid_native_contract(monkeypatch)
    context = _context()
    context.hardware_report = hardware_report
    result = gui.scientific_launch_eligibility(
        _draft(), context=context, storage_readiness=_ready_storage(),
        host_system="Linux", kernel_release="6.8",
    )
    assert not result.allowed
    assert result.blocker_code == "HOST_HARDWARE_MISMATCH"
    assert "Observed" in result.blocker_explanation


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    (
        ("Selected Salmon 2.5.1 index is unavailable", "ASSET_OR_RUNTIME_CLOSURE_UNAVAILABLE"),
        ("Required image identity validation failed", "ASSET_OR_RUNTIME_CLOSURE_UNAVAILABLE"),
        ("Offline Parabricks provenance mismatch", "PROVENANCE_INVALID"),
    ),
)
def test_native_gui_asset_image_and_provenance_fail_closed(
    monkeypatch: pytest.MonkeyPatch, failure: str, expected_code: str,
) -> None:
    _enable_valid_native_contract(monkeypatch)
    monkeypatch.setattr(
        gui, "validate_offline_runtime_closure",
        lambda *_args: (_ for _ in ()).throw(ValueError(failure)),
    )
    result = gui.scientific_launch_eligibility(
        _draft(), context=_context(), storage_readiness=_ready_storage(),
        host_system="Linux", kernel_release="6.8",
    )
    assert not result.allowed and result.blocker_code == expected_code


def test_native_gui_storage_and_controller_lock_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_valid_native_contract(monkeypatch)
    storage = {**_ready_storage(), "status": "BLOCKED", "explanation": "insufficient disk"}
    blocked = gui.scientific_launch_eligibility(
        _draft(), context=_context(), storage_readiness=storage,
        host_system="Linux", kernel_release="6.8",
    )
    assert not blocked.allowed and blocked.blocker_code == "ACTIVE_STORAGE_UNAVAILABLE"
    locked = gui.scientific_launch_eligibility(
        _draft(), context=_context(), storage_readiness=_ready_storage(), active_lock=True,
        host_system="Linux", kernel_release="6.8",
    )
    assert not locked.allowed and locked.blocker_code == "ACTIVE_RUN_CONFLICT"


def test_native_active_storage_accepts_ext4_and_rejects_archive_or_network() -> None:
    ready = gui.validate_native_storage_contract(
        runtime_root="/runtime", output_root="/runtime/results", work_root="/runtime/work",
        filesystems=("ext4", "ext4"), free_bytes=200, estimated_required_bytes=100,
        operational_reserve_bytes=10,
    )
    assert ready["status"] == "READY"
    assert ready["archive_policy"]["contract_id"] == "harako-gpu-terminal-results-archive-v1"
    with pytest.raises(ValueError, match="terminal archive storage"):
        gui.validate_native_storage_contract(
            runtime_root="/mnt/WDgold", output_root="/mnt/WDgold/results",
            work_root="/mnt/WDgold/work", filesystems=("ext4",), free_bytes=200,
            estimated_required_bytes=100, operational_reserve_bytes=10,
        )
    with pytest.raises(ValueError, match="Unsupported active-storage filesystem: cifs"):
        gui.validate_native_storage_contract(
            runtime_root="/runtime", output_root="/runtime/results", work_root="/runtime/work",
            filesystems=("cifs",), free_bytes=200, estimated_required_bytes=100,
            operational_reserve_bytes=10,
        )
    with pytest.raises(ValueError, match="Insufficient active-storage disk"):
        gui.validate_native_storage_contract(
            runtime_root="/runtime", output_root="/runtime/results", work_root="/runtime/work",
            filesystems=("ext4",), free_bytes=109, estimated_required_bytes=100,
            operational_reserve_bytes=10,
        )


def test_native_gui_backend_defaults_and_structured_controller_transport() -> None:
    native = gui.gui_environment_defaults(host_system="Linux", kernel_release="6.8")
    assert native == {
        "execution_context": NATIVE_LINUX,
        "host_profile_id": UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
        "workflow_backend": HARAKO_NATIVE_V1,
    }
    windows = gui.gui_environment_defaults(host_system="Windows", kernel_release="10")
    assert windows["workflow_backend"] == NFCORE_REFERENCE
    argv = controller_argv(
        action="start", run_dir="/runtime/runs/r1", approval_hash="a" * 64,
        execution_context="native-linux", python_executable="python-fixed",
    )
    assert "wsl.exe" not in argv
    assert argv[-2:] == ("--execution-context", "native-linux")
    assert "--distribution" not in argv


def test_gui_accepts_backend_aware_capability_snapshot() -> None:
    capability = SimpleNamespace(as_dict=lambda: {"status": "AVAILABLE_QUALIFIED"})
    snapshot = {
        "capability_matrix_version": gui.CAPABILITY_MATRIX_VERSION,
        "result": capability.as_dict(),
        "workflow_backend": gui.parse_workflow_backend(HARAKO_NATIVE_V1).as_dict(),
        "evaluated_at": "plan_creation",
    }
    gui._validate_gui_capability_snapshot(
        snapshot,
        capability=capability,
        workflow_backend=HARAKO_NATIVE_V1,
    )


def test_native_gui_start_reuses_frozen_run_and_controller_adapter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    (frozen / "plan.json").write_text(
        '{"workflow_backend":"harako_native_v1","capability_snapshot":{"result":'
        '{"host_profile_id":"ubuntu_native_rtx3090_ram128_v1"}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(gui, "inspect_run", lambda _path: {"run": {"identity": {
        "execution_context": NATIVE_LINUX, "approval_hash": "a" * 64,
    }}})
    monkeypatch.setattr(gui, "verify_frozen", lambda _path: None)

    class Store:
        def __init__(self, _path: Path) -> None:
            pass

        def inspect_lock(self, **_kwargs: object) -> str:
            return "ABSENT"

    monkeypatch.setattr(gui, "RunStateStore", Store)
    observed: dict[str, object] = {}

    def launch(*, argv: tuple[str, ...], run_dir_host: Path) -> SimpleNamespace:
        observed.update(argv=argv, run_dir_host=run_dir_host)
        return SimpleNamespace(pid=1234)

    monkeypatch.setattr(gui, "launch_controller", launch)
    launched = gui.launch_gui_controller(
        action="start", run_directory=str(tmp_path), approval_hash="a" * 64,
    )
    assert launched.pid == 1234
    assert "wsl.exe" not in observed["argv"]
    assert tuple(observed["argv"])[-2:] == ("--execution-context", "native-linux")


def test_native_gui_start_validates_frozen_inventory_not_plan_source_siblings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    (frozen / "plan.json").write_text(
        '{"workflow_backend":"harako_native_v1","capability_snapshot":{"result":'
        '{"host_profile_id":"ubuntu_native_rtx3090_ram128_v1"}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(gui, "inspect_run", lambda _path: {"run": {"identity": {
        "execution_context": NATIVE_LINUX, "approval_hash": "a" * 64,
    }}})
    observed: list[Path] = []
    monkeypatch.setattr(gui, "verify_frozen", lambda path: observed.append(path))
    monkeypatch.setattr(
        gui, "validate_plan_file",
        lambda _path: pytest.fail("frozen plan must not require source-plan sibling files"),
    )

    class Store:
        def __init__(self, _path: Path) -> None:
            pass

        def inspect_lock(self, **_kwargs: object) -> str:
            return "ABSENT"

    monkeypatch.setattr(gui, "RunStateStore", Store)
    monkeypatch.setattr(
        gui, "launch_controller",
        lambda **_kwargs: SimpleNamespace(pid=1234),
    )
    gui.launch_gui_controller(
        action="start", run_directory=str(tmp_path), approval_hash="a" * 64,
    )
    assert observed == [tmp_path]


def test_alignment_and_salmon_selections_map_only_to_fixed_runtime_contracts() -> None:
    one = gui.scientific_launch_eligibility(
        _draft(), host_system="Windows", kernel_release="10",
    )
    assert not one.allowed
    assert gui.select_resource_contract(
        UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID, FULL_HUMAN_REFERENCE_PACK_ID, ONE_PASS_PROFILE_ID,
    ).contract_id == ONE_PASS_RESOURCE_CONTRACT_ID
    assert gui.select_resource_contract(
        UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID, FULL_HUMAN_REFERENCE_PACK_ID, TWO_PASS_PROFILE_ID,
    ).contract_id == TWO_PASS_RESOURCE_CONTRACT_ID
    recommended = gui._requirements_for_draft(_draft())
    compatibility = gui._requirements_for_draft(_draft(
        quantification_mode="compatibility_only",
        primary_profile_id="salmon_1_10_3_compatibility",
    ))
    compared = gui._requirements_for_draft(_draft(quantification_mode="compare_both"))
    assert "salmon_2_5_1_deterministic" in recommended.required_image_roles
    assert "salmon_1_10_3_compatibility" not in recommended.required_image_roles
    assert "salmon_1_10_3_compatibility" in compatibility.required_image_roles
    assert set(compared.required_image_roles) >= {
        "salmon_2_5_1_deterministic", "salmon_1_10_3_compatibility",
    }


def test_eligibility_cannot_be_reused_after_scientific_selection_changes() -> None:
    result = gui.GuiScientificLaunchEligibility(
        True, NATIVE_LINUX, UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID, "VALID",
        "AVAILABLE_QUALIFIED", HARAKO_NATIVE_V1, ONE_PASS_PROFILE_ID,
        ONE_PASS_RESOURCE_CONTRACT_ID,
        {
            "reference_pack_id": FULL_HUMAN_REFERENCE_PACK_ID,
            "quantification_mode": "recommended_only",
            "primary_profile_id": "salmon_2_5_1_deterministic",
        },
        _ready_storage(), None, "", (),
    )
    assert result.matches(_draft())
    assert not result.matches(_draft(workflow_backend=NFCORE_REFERENCE))
    assert not result.matches(_draft(alignment_profile_id=TWO_PASS_PROFILE_ID))
    assert not result.matches(_draft(quantification_mode="compare_both"))


def _prime_native_app(test: AppTest, eligibility: dict[str, object]) -> None:
    test.session_state[state.PROJECT_SLUG] = "native-gui-test"
    test.session_state[state.SAMPLES] = list(_draft().samples)
    test.session_state[state.SAMPLES_VALID] = True
    test.session_state[state.REFERENCE] = FULL_HUMAN_REFERENCE_PACK_ID
    test.session_state[state.BAM_MODE] = "keep"
    test.session_state[state.ALIGNMENT_PROFILE] = ONE_PASS_PROFILE_ID
    test.session_state[state.QUANT_MODE] = "recommended_only"
    test.session_state[state.PRIMARY_PROFILE] = "salmon_2_5_1_deterministic"
    test.session_state[state.EXECUTION_CONTEXT] = NATIVE_LINUX
    test.session_state[state.HOST_PROFILE_ID] = UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID
    test.session_state[state.WORKFLOW_BACKEND] = HARAKO_NATIVE_V1
    test.session_state[state.RUNTIME_ROOT] = "/runtime"
    test.session_state[state.OUTPUT_ROOT] = "/runtime/results/native-gui-test"
    test.session_state[state.WORK_ROOT] = "/runtime/work/native-gui-test"
    test.session_state[state.LAUNCH_ELIGIBILITY] = eligibility


def test_app_test_renders_qualified_ubuntu_backend_profile_and_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    option = SimpleNamespace(
        reference_pack_id=FULL_HUMAN_REFERENCE_PACK_ID,
        display_name="Human GRCh38.p14 / GENCODE 49",
        as_dict=lambda: {
            "reference_pack_id": FULL_HUMAN_REFERENCE_PACK_ID,
            "species": "human", "assembly": "GRCh38.p14",
            "annotation_release": "49", "resource_class": "full_human",
            "qualification_status": "QUALIFIED",
        },
    )
    monkeypatch.setattr(reference_capability, "reference_catalog", lambda **_kwargs: (option,))
    eligibility = gui.GuiScientificLaunchEligibility(
        True, NATIVE_LINUX, UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID, "VALID",
        "AVAILABLE_QUALIFIED", HARAKO_NATIVE_V1, ONE_PASS_PROFILE_ID,
        ONE_PASS_RESOURCE_CONTRACT_ID,
        {
            "reference_pack_id": FULL_HUMAN_REFERENCE_PACK_ID,
            "quantification_mode": "recommended_only",
            "primary_profile_id": "salmon_2_5_1_deterministic",
            "salmon_2_5_1_index": True,
        }, _ready_storage(), None, "", ("research use only",),
    ).as_dict()
    tested = AppTest.from_file(str(ROOT / "src/harako_gpu/ui/app.py")).run(timeout=10)
    _prime_native_app(tested, eligibility)
    tested.session_state[state.PAGE] = "Reference & capability"
    tested.run(timeout=10)
    assert not tested.exception
    select_values = {item.value for item in tested.selectbox}
    assert HARAKO_NATIVE_V1 in select_values
    assert ONE_PASS_PROFILE_ID in select_values
    assert any("Validate native launch eligibility" == item.label for item in tested.button)
    rendered = " ".join(str(item.value) for item in tested.json)
    assert "AVAILABLE_QUALIFIED" in rendered
    assert "salmon_2_5_1_index" in rendered


def test_app_test_plan_review_requires_matching_eligibility(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    eligibility = gui.GuiScientificLaunchEligibility(
        True, NATIVE_LINUX, UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID, "VALID",
        "AVAILABLE_QUALIFIED", HARAKO_NATIVE_V1, ONE_PASS_PROFILE_ID,
        ONE_PASS_RESOURCE_CONTRACT_ID,
        {
            "reference_pack_id": FULL_HUMAN_REFERENCE_PACK_ID,
            "quantification_mode": "recommended_only",
            "primary_profile_id": "salmon_2_5_1_deterministic",
        }, _ready_storage(), None, "", (),
    ).as_dict()
    tested = AppTest.from_file(str(ROOT / "src/harako_gpu/ui/app.py")).run(timeout=10)
    _prime_native_app(tested, eligibility)
    tested.session_state[state.CAPABILITY_RESULT] = {"status": "AVAILABLE_QUALIFIED"}
    tested.session_state[state.PAGE] = "Review & prepare"
    tested.run(timeout=10)
    create = next(item for item in tested.button if item.label == "Create immutable plan")
    prepare = next(item for item in tested.button if item.label == "Prepare immutable run")
    assert not create.disabled and prepare.disabled
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        '{"plan_id":"p1","approval_hash":"' + "a" * 64 +
        '","workflow_backend":"harako_native_v1","alignment_profile_id":'
        '"parabricks_star_one_pass_workstation","execution_context":"native_linux",'
        '"quantification":{},"capability_snapshot":{"result":{"host_profile_id":'
        '"ubuntu_native_rtx3090_ram128_v1"}},"reference":{},'
        '"output_root":"/runtime/results","work_root":"/runtime/work"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(review_prepare, "create_gui_plan", lambda _draft: plan_path)
    create.click().run(timeout=10)
    assert not tested.exception
    assert any("approval_hash" in str(item.value) for item in tested.json)
    review = next(
        item for item in tested.checkbox
        if item.label == "I reviewed the immutable plan and approval hash"
    )
    review.set_value(True).run(timeout=10)
    prepare = next(item for item in tested.button if item.label == "Prepare immutable run")
    assert not prepare.disabled
    tested.session_state[state.WORKFLOW_BACKEND] = NFCORE_REFERENCE
    tested.run(timeout=10)
    prepare = next(item for item in tested.button if item.label == "Prepare immutable run")
    assert prepare.disabled
