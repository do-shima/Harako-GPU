"""Evaluate frozen SIRV E0 and ERCC v2 external-truth outputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from decimal import Decimal
from pathlib import Path

from harako_gpu.services.external_truth_validation import (
    CrossMappingResult,
    aggregate_relative_error_metrics,
    concentration_metrics,
    equimolar_metrics,
    ercc_fold_change_metrics,
    normalized_mole_fractions,
    parse_ercc_truth,
    sirv_expected_fractions,
    upper_fraction_ids,
)


def quant_tpm(path: Path) -> dict[str, Decimal]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = tuple(csv.DictReader(handle, delimiter="\t"))
    if not rows or set(rows[0]) != {"Name", "Length", "EffectiveLength", "TPM", "NumReads"}:
        raise ValueError(f"Invalid quant.sf schema: {path}")
    values = {row["Name"]: Decimal(row["TPM"]) for row in rows}
    if len(values) != len(rows) or any(value < 0 or not value.is_finite() for value in values.values()):
        raise ValueError(f"Invalid or duplicate quantification values: {path}")
    return values


def meta(path: Path) -> dict[str, object]:
    return json.loads((path / "aux_info/meta_info.json").read_text(encoding="utf-8"))


def safe_number(value: float) -> float | str:
    return "Infinity" if math.isinf(value) else value


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.runtime_root.resolve()

    ident_rows = json.loads((root / "references/external-v2/sirv69.identifiability.json").read_text())
    tx_to_gene = {row["transcript_id"]: row["gene_id"] for row in ident_rows}
    tx_expected, gene_expected = sirv_expected_fractions(tx_to_gene)
    sirv_quant_path = root / "runs/salmon-2.5.1/SRR3497201/threads-6-run-1/quant.sf"
    all_tpm = quant_tpm(sirv_quant_path)
    sirv_tpm = {name: all_tpm.get(name, Decimal(0)) for name in tx_expected}
    sirv_fraction = normalized_mole_fractions(tuple(tx_expected), sirv_tpm)
    identifiable = tuple(
        row["transcript_id"] for row in ident_rows if row["classification"] == "transcript-identifiable"
    )
    transcript_report = equimolar_metrics(tx_expected, sirv_fraction, evaluated_ids=identifiable)
    gene_tpm = {
        gene: sum((sirv_tpm[name] for name, owner in tx_to_gene.items() if owner == gene), Decimal(0))
        for gene in gene_expected
    }
    gene_fraction = normalized_mole_fractions(tuple(gene_expected), gene_tpm)
    gene_report = equimolar_metrics(gene_expected, gene_fraction)
    eq_map = {row["transcript_id"]: row["equivalence_group"] for row in ident_rows}
    equivalence_report = aggregate_relative_error_metrics(tx_expected, sirv_fraction, eq_map)
    sirv_table = []
    for row in ident_rows:
        name = row["transcript_id"]
        estimated = sirv_fraction[name]
        error = math.inf if estimated == 0 else abs(math.log2(float(estimated / tx_expected[name])))
        sirv_table.append({
            **row,
            "expected_fraction": str(tx_expected[name]),
            "estimated_fraction": str(estimated),
            "tpm": str(sirv_tpm[name]),
            "detected": estimated > 0,
            "absolute_log2_molar_error": safe_number(error),
        })

    truth = parse_ercc_truth((root / "references/ERCC_Controls_Analysis.txt").read_text())
    truth_by_id = {row.ercc_id: row for row in truth}
    primary = upper_fraction_ids(
        {row.ercc_id: min(row.mix1, row.mix2) for row in truth}, Decimal("0.75")
    )
    lane_runs = {
        "Mix1": ("SRR896983", "SRR896985"),
        "Mix2": ("SRR897015", "SRR897017"),
    }
    lane_tpm: dict[str, dict[str, Decimal]] = {}
    concentration = {}
    for mix, samples in lane_runs.items():
        truth_values = {
            row.ercc_id: row.mix1 if mix == "Mix1" else row.mix2 for row in truth
        }
        concentration[mix] = {}
        for sample in samples:
            path = root / f"runs/salmon-2.5.1/{sample}/threads-6-run-1"
            values = quant_tpm(path / "quant.sf")
            lane_tpm[sample] = values
            report = concentration_metrics(truth_values, values, primary)
            concentration[mix][sample] = {
                "features": report.features,
                "detected": report.detected,
                "detection_rate": report.detection_rate,
                "pearson": report.pearson,
                "spearman": report.spearman,
                "passed": report.passed,
                "processed": meta(path)["num_processed"],
                "mapped": meta(path)["num_mapped"],
            }
    mix_tpm = {
        mix: {
            name: sum((lane_tpm[sample][name] for sample in samples), Decimal(0)) / Decimal(len(samples))
            for name in truth_by_id
        }
        for mix, samples in lane_runs.items()
    }
    fold = ercc_fold_change_metrics(truth, mix_tpm["Mix1"], mix_tpm["Mix2"], primary)

    cross_paths = {
        "SIRV-to-ERCC": root / "runs/cross-mapping/SIRV-to-ERCC",
        **{
            f"{sample}-to-combined": root / f"runs/cross-mapping/{sample}-to-combined"
            for sample in (*lane_runs["Mix1"], *lane_runs["Mix2"])
        },
    }
    cross = {}
    for name, path in cross_paths.items():
        metadata = meta(path)
        values = quant_tpm(path / "quant.sf")
        highest = max(values, key=values.get)  # type: ignore[arg-type]
        result = CrossMappingResult(
            int(metadata["num_processed"]), int(metadata["num_mapped"]), highest, values[highest]
        )
        cross[name] = {
            "processed": result.processed,
            "mapped": result.mapped,
            "mapped_fraction": str(result.mapped_fraction),
            "highest_target": result.highest_target,
            "highest_target_tpm": str(result.highest_target_mass),
            "warning": result.warning,
            "blocked": result.blocked,
        }

    output = {
        "schema_version": 1,
        "preregistration_v2_sha256": "d65570ad5d47bb99ad185e792ef1e1c9616016262189b1e24e84e43c59124794",
        "sirv": {
            "quant_sf_sha256": sha256_path(sirv_quant_path),
            "correlation": "NOT_APPLICABLE_ZERO_VARIANCE",
            "identifiable_transcript_metrics": {
                "features": transcript_report.evaluated_features,
                "detected": transcript_report.detected_features,
                "detection_rate": transcript_report.detection_rate,
                "median_absolute_log2_molar_error": safe_number(transcript_report.median_absolute_log2_error),
                "p90_absolute_log2_molar_error": safe_number(transcript_report.p90_absolute_log2_error),
                "passed": transcript_report.transcript_passed(),
            },
            "all_transcript_detection_rate": sum(row["detected"] for row in sirv_table) / 69,
            "gene_metrics": {
                "features": gene_report.evaluated_features,
                "detected": gene_report.detected_features,
                "detection_rate": gene_report.detection_rate,
                "median_absolute_log2_molar_error": safe_number(gene_report.median_absolute_log2_error),
                "p90_absolute_log2_molar_error": safe_number(gene_report.p90_absolute_log2_error),
                "passed": gene_report.gene_passed(),
            },
            "equivalence_group_metrics": {
                "groups": equivalence_report.groups,
                "median_relative_error": equivalence_report.median_relative_error,
                "p90_relative_error": equivalence_report.p90_relative_error,
                "passed": equivalence_report.passed,
            },
            "transcripts": sirv_table,
        },
        "ercc": {
            "primary_subset_count": len(primary),
            "concentration": concentration,
            "lane_aggregation": "arithmetic mean TPM per mix; fixed before primary abundance values were read",
            "fold_change": {
                "spearman": fold.spearman,
                "rmse": fold.rmse,
                "median_absolute_error": fold.median_absolute_error,
                "direction_accuracy_by_group": dict(fold.direction_accuracy_by_group),
                "group_median_error": dict(fold.group_median_error),
                "passed": fold.passed,
            },
        },
        "cross_mapping": cross,
        "overall_accuracy_without_cross_mapping": (
            transcript_report.transcript_passed() and gene_report.gene_passed()
            and equivalence_report.passed and all(
                lane["passed"] for mix in concentration.values() for lane in mix.values()
            ) and fold.passed
        ),
        "cross_mapping_passed": not any(row["blocked"] for row in cross.values()),
    }
    args.output.resolve().write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in output.items() if key != "sirv"}, indent=2))
    print(json.dumps({"sirv": {key: value for key, value in output["sirv"].items() if key != "transcripts"}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
