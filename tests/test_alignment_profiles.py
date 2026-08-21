from __future__ import annotations

import pytest

from harako_gpu.services.alignment_profiles import (
    ONE_PASS_LIMITATION_EN,
    ONE_PASS_PROFILE_ID,
    TWO_PASS_PROFILE_ID,
    OnePassResourceObservation,
    WorkstationResourceClass,
    alignment_profiles,
    classify_one_pass_resources,
    fixed_parabricks_extra_args,
    may_progress_from,
    scientific_parameter_diff,
    validate_alignment_profile_selection,
)


GIB = 1024**3


def observation(*, ram: float = 0.5, available_gib: int = 20, swap_gib: int = 0,
                vram: float = 0.5, success: bool = True, artifacts: bool = True,
                killed: bool = False) -> OnePassResourceObservation:
    return OnePassResourceObservation(
        success, artifacts, int(ram * 1000), 1000, available_gib * GIB, swap_gib * GIB,
        vram * 1000, 1000, True, killed,
    )


def test_catalog_separates_workstation_and_high_memory_profiles() -> None:
    one, two = alignment_profiles()
    assert one.profile_id == ONE_PASS_PROFILE_ID and not one.two_pass
    assert one.host_qualification_status == "evaluated_by_host_capability_matrix"
    assert ONE_PASS_LIMITATION_EN in one.limitations
    assert two.profile_id == TWO_PASS_PROFILE_ID and two.two_pass
    assert two.host_qualification_status == "evaluated_by_host_capability_matrix"


def test_alignment_profile_catalog_is_host_neutral() -> None:
    assert validate_alignment_profile_selection(TWO_PASS_PROFILE_ID).profile_id == TWO_PASS_PROFILE_ID
    assert validate_alignment_profile_selection(ONE_PASS_PROFILE_ID).profile_id == ONE_PASS_PROFILE_ID
    assert validate_alignment_profile_selection(
        ONE_PASS_PROFILE_ID, allow_qualification_candidate=True,
    ).profile_id == ONE_PASS_PROFILE_ID


def test_one_pass_parameter_is_explicit_and_only_scientific_delta() -> None:
    one = fixed_parabricks_extra_args(ONE_PASS_PROFILE_ID)
    two = fixed_parabricks_extra_args(TWO_PASS_PROFILE_ID)
    assert "--two-pass-mode None" in one and "--two-pass-mode Basic" not in one
    assert "--two-pass-mode Basic" in two
    for fixed in ("--low-memory", "--quantMode TranscriptomeSAM GeneCounts", "--sjdb-overhang 74"):
        assert fixed in one and fixed in two
    assert scientific_parameter_diff() == {
        "--two-pass-mode": {TWO_PASS_PROFILE_ID: "Basic", ONE_PASS_PROFILE_ID: "None"}
    }
    small = fixed_parabricks_extra_args(ONE_PASS_PROFILE_ID, sjdb_overhang=100, qualification_debug_x3=True)
    assert "--sjdb-overhang 100" in small and "--two-pass-mode None" in small
    with pytest.raises(ValueError, match="explicitly qualified"):
        fixed_parabricks_extra_args(ONE_PASS_PROFILE_ID, sjdb_overhang=75)


@pytest.mark.parametrize(("value", "expected"), (
    (observation(), WorkstationResourceClass.COMFORTABLE),
    (observation(ram=0.80), WorkstationResourceClass.CONSTRAINED),
    (observation(available_gib=7), WorkstationResourceClass.CONSTRAINED),
    (observation(swap_gib=1), WorkstationResourceClass.CONSTRAINED),
    (observation(ram=0.90), WorkstationResourceClass.UNSAFE),
    (observation(available_gib=3), WorkstationResourceClass.UNSAFE),
    (observation(swap_gib=4), WorkstationResourceClass.UNSAFE),
    (observation(success=False, killed=True), WorkstationResourceClass.RESOURCE_FAILED),
))
def test_resource_classification(value: OnePassResourceObservation, expected: WorkstationResourceClass) -> None:
    assert classify_one_pass_resources(value) is expected


def test_progression_requires_comfortable_and_c4_stricter_gate() -> None:
    value = observation(ram=0.70, available_gib=12)
    assert may_progress_from("C1_1M", WorkstationResourceClass.COMFORTABLE, value)
    assert may_progress_from("C2_5M", WorkstationResourceClass.COMFORTABLE, value)
    assert may_progress_from("C3_10M", WorkstationResourceClass.COMFORTABLE, value)
    assert not may_progress_from("C3_10M", WorkstationResourceClass.COMFORTABLE, observation(ram=0.76))
    assert not may_progress_from("C1_1M", WorkstationResourceClass.CONSTRAINED, value)
