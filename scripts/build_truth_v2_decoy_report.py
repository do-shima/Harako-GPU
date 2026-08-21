"""Build the machine-readable truth-v2 biological and decoy-gate report."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from harako_gpu.services.decoy_accounting import (
    IdentifiabilityClass,
    IndexControlReport,
    LeakageMeasurement,
    build_truth_v2_biological_report,
    validate_primary_decoy_gates,
)


SAMPLE_CLASS = {
    "decoy_unique_only": IdentifiabilityClass.DECOY_UNIQUE,
    "decoy_dominant_only": IdentifiabilityClass.DECOY_DOMINANT,
    "decoy_ambiguous_only": IdentifiabilityClass.DECOY_AMBIGUOUS,
    "decoy_exact_tie_only": IdentifiabilityClass.DECOY_EXACT_TIE,
}


def _quant(path: Path, transcript_ids: set[str]) -> dict[str, Decimal]:
    values: dict[str, Decimal] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["Name"] in transcript_ids:
                values[row["Name"]] = Decimal(row["NumReads"])
    return values


def build(fixture: Path, controls_path: Path, matrix_root: Path) -> dict[str, object]:
    manifest = json.loads((fixture / "manifest.json").read_text(encoding="utf-8"))
    controls = json.loads(controls_path.read_text(encoding="utf-8"))
    matrix = json.loads((matrix_root / "matrix-report.json").read_text(encoding="utf-8"))
    transcript_ids = {row["transcript_id"] for row in manifest["transcripts"]}
    quant_by_sample: dict[str, dict[str, Decimal]] = {}
    processed: dict[str, int] = {}
    mapped: dict[str, int] = {}
    for sample in (row["sample"] for row in manifest["main_samples"]):
        quant_by_sample[sample] = _quant(
            matrix_root / "main_repeat" / sample / "run-1/quant.sf", transcript_ids,
        )
        run = next(
            row for row in matrix["runs"]
            if row["phase"] == "main_repeat" and row["sample"] == sample and row["replicate"] == 1
        )
        processed[sample], mapped[sample] = int(run["num_processed"]), int(run["num_mapped"])
    biology = build_truth_v2_biological_report(
        manifest=manifest, quant_by_sample=quant_by_sample,
        processed_by_sample=processed, mapped_by_sample=mapped,
    )
    control_rows = {(row["index_role"], row["sample"]): row for row in controls["runs"]}
    primary: list[IndexControlReport] = []
    class_reports: dict[str, object] = {}
    for sample, category in SAMPLE_CLASS.items():
        aware = control_rows[("decoy_aware", sample)]
        plain = control_rows[("transcript_only", sample)]
        aware_measurement = LeakageMeasurement(
            category, int(aware["expected_fragments"]), Decimal(aware["estimated_transcript_mass"]),
        )
        plain_measurement = LeakageMeasurement(
            category, int(plain["expected_fragments"]), Decimal(plain["estimated_transcript_mass"]),
        )
        report = IndexControlReport(aware_measurement, plain_measurement)
        if category in {IdentifiabilityClass.DECOY_UNIQUE, IdentifiabilityClass.DECOY_DOMINANT}:
            primary.append(report)
        class_reports[category.value] = {
            "generated_fragments": aware_measurement.generated_fragments,
            "decoy_aware_transcript_mass": str(aware_measurement.estimated_transcript_mass),
            "decoy_aware_fraction": str(aware_measurement.fraction),
            "transcript_only_transcript_mass": str(plain_measurement.estimated_transcript_mass),
            "transcript_only_fraction": str(plain_measurement.fraction),
            "relative_reduction": str(report.relative_reduction),
            "primary_gate": aware_measurement.primary_gate,
            "gate_label": (
                "primary_leakage" if aware_measurement.primary_gate is not None
                else "unidentifiable_assignment_mass" if category is IdentifiabilityClass.DECOY_EXACT_TIE
                else "reported_without_pass_fail"
            ),
        }
    validate_primary_decoy_gates(primary)
    biology_payload = asdict(biology)
    biology_payload["unidentifiable_assignment_mass"] = str(biology.unidentifiable_assignment_mass)
    biology_payload["passed"] = biology.passed
    payload: dict[str, object] = {
        "schema_version": "expression_truth_decoy_remediation_v1",
        "fixture_id": manifest["fixture_id"],
        "fixture_scientific_manifest_sha256": manifest["scientific_manifest_sha256"],
        "candidate_version": "2.5.1",
        "deterministic_matrix_exact": bool(matrix["exact_identity_passed"]),
        "decoy_class_reports": class_reports,
        "primary_decoy_gates_passed": True,
        "biological_truth": biology_payload,
        "rad_accounting": {
            "rad_retained_for_decoy_aware_controls": True,
            "rad_binary_parsed": False,
            "reason": "binary RAD was not reverse-engineered; only official Salmon outputs and file completion evidence were used",
            "metadata_num_decoy_fragments": sorted({
                row["num_decoy_fragments"] for row in controls["runs"] if row["index_role"] == "decoy_aware"
            }),
            "metadata_num_decoy_targets": sorted({
                row["num_decoy_targets"] for row in controls["runs"] if row["index_role"] == "decoy_aware"
            }),
            "classification": "METADATA_COUNTERS_DO_NOT_EXPOSE_INDEX_DECOY_ACCOUNTING",
            "diagnostic_only_not_primary_truth": True,
        },
        "internal_truth_gates_passed": bool(matrix["exact_identity_passed"]) and biology.passed,
        "external_truth_validation": "NOT_RUN",
        "default_adoption_authorized": False,
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--controls", type=Path, required=True)
    parser.add_argument("--matrix-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(
        args.fixture.resolve(), args.controls.resolve(), args.matrix_root.resolve(),
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "primary_decoy_gates_passed": result["primary_decoy_gates_passed"],
        "biological_truth_passed": result["biological_truth"]["passed"],
        "internal_truth_gates_passed": result["internal_truth_gates_passed"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
