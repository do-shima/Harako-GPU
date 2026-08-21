from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from harako_gpu.services.capacity import (
    GIB, CapacityClassification, DiskGate, ResourceObservation,
    classify_capacity, create_nested_prefix_subset, may_run_next_scale,
    observed_ratio_estimate, select_paired_orientation, validate_paired_fastq,
)


REPOSITORY = Path(__file__).resolve().parents[1]


def _fastq(path: Path, names: list[str], mate: int) -> None:
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as out:
        for name in names:
            out.write(f"@{name}/{mate}\nACGT\n+\nIIII\n".encode())


def test_disk_gate_uses_larger_fixed_or_fractional_reserve() -> None:
    gate = DiskGate(total_bytes=500 * GIB, free_bytes=300 * GIB, estimated_high_water_bytes=200 * GIB)
    assert gate.hard_reserve_bytes == 75 * GIB and gate.passed
    assert not DiskGate(500 * GIB, 250 * GIB, 200 * GIB).passed


@pytest.mark.parametrize(("ram", "vram", "expected"), [
    (0.50, 0.50, CapacityClassification.QUALIFIED_COMFORTABLE),
    (0.80, 0.50, CapacityClassification.QUALIFIED_CONSTRAINED),
    (0.50, 0.90, CapacityClassification.QUALIFIED_CONSTRAINED),
    (0.90, 0.50, CapacityClassification.RESOURCE_FAILED),
    (0.50, 0.95, CapacityClassification.RESOURCE_FAILED),
])
def test_resource_classification_boundaries(ram: float, vram: float, expected: CapacityClassification) -> None:
    value = ResourceObservation(True, True, int(ram * 1000), 1000, vram * 1000, 1000, True)
    assert classify_capacity(value) is expected
    assert may_run_next_scale(value) is (expected is CapacityClassification.QUALIFIED_COMFORTABLE)


def test_resource_failure_precedes_utilization_classification() -> None:
    value = ResourceObservation(False, False, 1, 100, 1, 100, True)
    assert classify_capacity(value) is CapacityClassification.RESOURCE_FAILED


def test_sustained_low_available_ram_is_hard_stop() -> None:
    value = ResourceObservation(
        True, True, 700, 1000, 500, 1000, True,
        minimum_available_ram_bytes=3 * GIB, low_available_ram_duration_seconds=30,
    )
    assert classify_capacity(value) is CapacityClassification.RESOURCE_FAILED
    transient = ResourceObservation(
        True, True, 700, 1000, 500, 1000, True,
        minimum_available_ram_bytes=3 * GIB, low_available_ram_duration_seconds=29.9,
    )
    assert classify_capacity(transient) is CapacityClassification.QUALIFIED_COMFORTABLE


def test_deterministic_nested_fastq_subset_and_pair_validation(tmp_path: Path) -> None:
    source1, source2 = tmp_path / "source1.gz", tmp_path / "source2.gz"
    _fastq(source1, ["a", "b", "c"], 1); _fastq(source2, ["a", "b", "c"], 2)
    first1, first2 = tmp_path / "one/r1.gz", tmp_path / "one/r2.gz"
    second1, second2 = tmp_path / "two/r1.gz", tmp_path / "two/r2.gz"
    assert create_nested_prefix_subset(source_r1=source1, source_r2=source2, output_r1=first1, output_r2=first2, pairs=2) == 2
    assert create_nested_prefix_subset(source_r1=source1, source_r2=source2, output_r1=second1, output_r2=second2, pairs=2) == 2
    assert first1.read_bytes() == second1.read_bytes() and first2.read_bytes() == second2.read_bytes()
    assert validate_paired_fastq(first1, first2, expected_pairs=2) == {"paired_fragments": 2, "read_lengths": [4], "orphans": 0}
    with gzip.open(first1, "rt") as handle:
        assert handle.readline().strip() == "@a/1"


def test_fastq_subset_rejects_orphan_and_qname_mismatch(tmp_path: Path) -> None:
    one, two = tmp_path / "one.gz", tmp_path / "two.gz"
    _fastq(one, ["a"], 1); _fastq(two, ["b"], 2)
    with pytest.raises(ValueError, match="QNAME"):
        create_nested_prefix_subset(source_r1=one, source_r2=two, output_r1=tmp_path / "r1.gz", output_r2=tmp_path / "r2.gz", pairs=1)


def test_estimator_marks_outside_tested_range_unqualified() -> None:
    inside = observed_ratio_estimate(requested_pairs=5, observations=((1, 110), (10, 200)), fixed_bytes=100)
    outside = observed_ratio_estimate(requested_pairs=20, observations=((1, 110), (10, 200)), fixed_bytes=100)
    assert inside["status"] == "OBSERVED_RANGE_DESCRIPTIVE"
    assert outside["status"] == "EXTRAPOLATED_UNQUALIFIED"
    assert outside["fixed_bytes"] == 100


def test_orientation_selection_uses_shared_unstranded_denominator() -> None:
    selected = select_paired_orientation({"IU": 1000, "ISF": 510, "ISR": 490})
    assert selected["selected_product_library_type"] == "U"
    assert selected["proportions"] == {"IU": 1.0, "ISF": 0.51, "ISR": 0.49}
    assert select_paired_orientation({"IU": 1000, "ISF": 900, "ISR": 100})["status"] == "UNKNOWN_LIBRARY_TYPE"


def test_capacity_qualification_scripts_do_not_hardcode_user_or_use_shell_eval() -> None:
    names = (
        "acquire_medium_human_capacity_data.py", "amend_capacity_library_type_probe.py",
        "build_human_capacity_indices.py", "build_human_reference_assets.py",
        "freeze_capacity_preregistration.py", "prepare_medium_human_capacity_plans.py",
        "resolve_capacity_library_type.py",
    )
    for name in names:
        text = (REPOSITORY / "scripts/qualification" / name).read_text(encoding="utf-8")
        assert "/home/do" not in text and "shell=True" not in text and "eval(" not in text


def test_capacity_acquisition_rejects_non_preregistered_url_by_exact_allowlist() -> None:
    text = (REPOSITORY / "scripts/qualification/acquire_medium_human_capacity_data.py").read_text(
        encoding="utf-8"
    )
    assert "Non-preregistered URL refused" in text
    assert "https://ftp.sra.ebi.ac.uk/vol1/fastq/ERR188/ERR188044/" in text
