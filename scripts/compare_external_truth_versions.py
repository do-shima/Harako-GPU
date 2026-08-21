"""Compare version-specific Salmon outputs against fixed external truth."""

from __future__ import annotations

import argparse
import csv
import json
from decimal import Decimal
from pathlib import Path

from harako_gpu.services.external_truth_validation import (
    aggregate_relative_error_metrics,
    concentration_metrics,
    equimolar_metrics,
    ercc_fold_change_metrics,
    normalized_mole_fractions,
    parse_ercc_truth,
    sirv_expected_fractions,
    upper_fraction_ids,
)


def tpm(path: Path) -> dict[str, Decimal]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = tuple(csv.DictReader(handle, delimiter="\t"))
    return {row["Name"]: Decimal(row["TPM"]) for row in rows}


def metadata(path: Path) -> dict[str, object]:
    return json.loads((path / "aux_info/meta_info.json").read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.runtime_root.resolve()
    ident = json.loads((root / "references/external-v2/sirv69.identifiability.json").read_text())
    tx_gene = {row["transcript_id"]: row["gene_id"] for row in ident}
    tx_expected, gene_expected = sirv_expected_fractions(tx_gene)
    identifiable = tuple(row["transcript_id"] for row in ident if row["classification"] == "transcript-identifiable")
    eq_map = {row["transcript_id"]: row["equivalence_group"] for row in ident}
    truth = parse_ercc_truth((root / "references/ERCC_Controls_Analysis.txt").read_text())
    primary = upper_fraction_ids({row.ercc_id: min(row.mix1, row.mix2) for row in truth}, Decimal("0.75"))
    lanes = {"Mix1": ("SRR896983", "SRR896985"), "Mix2": ("SRR897015", "SRR897017")}
    report = {}
    for version in ("1.10.3", "1.12.1", "2.5.1"):
        if version == "2.5.1":
            base = root / "runs/salmon-2.5.1"
            sirv_path = base / "SRR3497201/threads-6-run-1"
            lane_paths = {sample: base / sample / "threads-6-run-1" for samples in lanes.values() for sample in samples}
        else:
            base = root / "runs/version-comparison" / version
            sirv_path = base / "SRR3497201"
            lane_paths = {sample: base / sample for samples in lanes.values() for sample in samples}
        full_tpm = tpm(sirv_path / "quant.sf")
        sirv_tpm = {name: full_tpm.get(name, Decimal(0)) for name in tx_expected}
        sirv_fraction = normalized_mole_fractions(tuple(tx_expected), sirv_tpm)
        tx_metrics = equimolar_metrics(tx_expected, sirv_fraction, evaluated_ids=identifiable)
        gene_tpm = {
            gene: sum((sirv_tpm[name] for name, owner in tx_gene.items() if owner == gene), Decimal(0))
            for gene in gene_expected
        }
        gene_fraction = normalized_mole_fractions(tuple(gene_expected), gene_tpm)
        gene_metrics = equimolar_metrics(gene_expected, gene_fraction)
        eq_metrics = aggregate_relative_error_metrics(tx_expected, sirv_fraction, eq_map)
        lane_tpm = {sample: tpm(path / "quant.sf") for sample, path in lane_paths.items()}
        concentrations = {}
        for mix, samples in lanes.items():
            expected = {row.ercc_id: row.mix1 if mix == "Mix1" else row.mix2 for row in truth}
            concentrations[mix] = {
                sample: concentration_metrics(expected, lane_tpm[sample], primary).__dict__
                for sample in samples
            }
        means = {
            mix: {
                row.ercc_id: sum((lane_tpm[sample][row.ercc_id] for sample in samples), Decimal(0)) / Decimal(2)
                for row in truth
            }
            for mix, samples in lanes.items()
        }
        fold = ercc_fold_change_metrics(truth, means["Mix1"], means["Mix2"], primary)
        report[version] = {
            "sirv": {
                "processed": metadata(sirv_path)["num_processed"],
                "mapped": metadata(sirv_path)["num_mapped"],
                "identifiable_detection": tx_metrics.detection_rate,
                "transcript_median_abs_log2_error": tx_metrics.median_absolute_log2_error,
                "transcript_p90_abs_log2_error": tx_metrics.p90_absolute_log2_error,
                "transcript_gate": tx_metrics.transcript_passed(),
                "gene_median_abs_log2_error": gene_metrics.median_absolute_log2_error,
                "gene_p90_abs_log2_error": gene_metrics.p90_absolute_log2_error,
                "gene_gate": gene_metrics.gene_passed(),
                "equivalence_median_relative_error": eq_metrics.median_relative_error,
                "equivalence_p90_relative_error": eq_metrics.p90_relative_error,
                "equivalence_gate": eq_metrics.passed,
            },
            "ercc": {
                "concentration": concentrations,
                "fold_change_spearman": fold.spearman,
                "fold_change_rmse": fold.rmse,
                "fold_change_median_absolute_error": fold.median_absolute_error,
                "fold_change_gate": fold.passed,
                "fragment_accounting": {
                    sample: {
                        "processed": metadata(path)["num_processed"],
                        "mapped": metadata(path)["num_mapped"],
                    }
                    for sample, path in lane_paths.items()
                },
            },
        }
    args.output.resolve().write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
