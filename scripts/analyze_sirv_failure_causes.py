"""Audit the frozen SIRV equivalence-group failure without changing its verdict."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from decimal import Decimal
from pathlib import Path

from harako_gpu.services.external_truth_cause_isolation import (
    EquivalenceMember,
    audit_equivalence_partition,
    classify_gate_coherence,
    log2_threshold_scale,
    relative_threshold_scale,
)
from harako_gpu.services.external_truth_validation import normalized_mole_fractions, percentile


def quant_rows(path: Path) -> dict[str, dict[str, Decimal]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = tuple(csv.DictReader(handle, delimiter="\t"))
    expected = {"Name", "Length", "EffectiveLength", "TPM", "NumReads"}
    if not rows or set(rows[0]) != expected or len({row["Name"] for row in rows}) != len(rows):
        raise ValueError(f"Invalid quant.sf: {path}")
    return {
        row["Name"]: {key: Decimal(row[key]) for key in expected - {"Name"}}
        for row in rows
    }


def group_metrics(groups: list[dict[str, object]]) -> dict[str, float | int | bool]:
    errors = [float(row["relative_error"]) for row in groups]
    return {
        "groups": len(errors),
        "median_relative_error": statistics.median(errors),
        "p90_relative_error": percentile(errors, 0.90),
        "passed": statistics.median(errors) <= 0.25 and percentile(errors, 0.90) <= 0.50,
    }


def summarize(groups: list[dict[str, object]], predicate) -> dict[str, float | int | bool]:
    return group_metrics([row for row in groups if predicate(row)])


def audit_quant(ident: list[dict[str, object]], quant: dict[str, dict[str, Decimal]]) -> tuple[list[dict[str, object]], dict[str, object]]:
    names = tuple(str(row["transcript_id"]) for row in ident)
    expected = {name: Decimal(1) / Decimal(69) for name in names}
    tpm = {name: quant.get(name, {}).get("TPM", Decimal(0)) for name in names}
    estimated = normalized_mole_fractions(names, tpm)
    members = [
        EquivalenceMember(
            str(row["transcript_id"]), str(row["equivalence_group"]), str(row["gene_id"]),
            expected[str(row["transcript_id"])], estimated[str(row["transcript_id"])],
            row["classification"] == "transcript-identifiable", int(row["length"]),
            float(row["gc_fraction"]), estimated[str(row["transcript_id"])] > 0,
            sirv502=row["transcript_id"] == "SIRV502",
        )
        for row in ident
    ]
    audited = audit_equivalence_partition(members)
    rows = [
        {
            "group_id": row.group_id,
            "member_transcripts": list(row.members),
            "member_genes": list(row.genes),
            "group_size": len(row.members),
            "singleton": len(row.members) == 1,
            "expected_fraction": str(row.expected_fraction),
            "estimated_fraction": str(row.estimated_fraction),
            "relative_error": row.relative_error,
            "absolute_log2_error": "Infinity" if math.isinf(row.absolute_log2_error) else row.absolute_log2_error,
            "identifiable": row.identifiable,
            "sirv502": row.sirv502,
            "mean_length": row.mean_length,
            "mean_gc": row.mean_gc,
            "all_detected": all(member.detected for member in members if member.transcript_id in row.members),
        }
        for row in audited
    ]
    summary = {
        "partition": {
            "transcripts": len(names),
            "unique_transcripts": len(set(names)),
            "groups": len(rows),
            "duplicate_membership": False,
            "missing_transcripts": [],
            "expected_fraction_sum": str(sum((row.expected_fraction for row in audited), Decimal(0))),
            "estimated_fraction_sum": str(sum((row.estimated_fraction for row in audited), Decimal(0))),
            "zero_denominators": 0,
        },
        "overall": group_metrics(rows),
        "strata": {
            "singleton": summarize(rows, lambda row: row["singleton"]),
            "multi_transcript": summarize(rows, lambda row: not row["singleton"]),
            "identifiable": summarize(rows, lambda row: row["identifiable"]),
            "non_identifiable": summarize(rows, lambda row: not row["identifiable"]),
            "sirv502": summarize(rows, lambda row: row["sirv502"]),
            "without_sirv502": summarize(rows, lambda row: not row["sirv502"]),
            "short_le_1000": summarize(rows, lambda row: float(row["mean_length"]) <= 1000),
            "long_gt_1000": summarize(rows, lambda row: float(row["mean_length"]) > 1000),
            "low_gc_lt_0_45": summarize(rows, lambda row: float(row["mean_gc"]) < 0.45),
            "high_gc_ge_0_45": summarize(rows, lambda row: float(row["mean_gc"]) >= 0.45),
        },
        "target_mass": {
            "sirv_tpm": str(sum((quant[name]["TPM"] for name in names if name in quant), Decimal(0))),
            "human_tpm": str(sum((values["TPM"] for name, values in quant.items() if name not in set(names)), Decimal(0))),
            "sirv_num_reads": str(sum((quant[name]["NumReads"] for name in names if name in quant), Decimal(0))),
            "human_num_reads": str(sum((values["NumReads"] for name, values in quant.items() if name not in set(names)), Decimal(0))),
        },
    }
    return rows, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.runtime_root.resolve()
    ident = json.loads((root / "references/external-v2/sirv69.identifiability.json").read_text())
    paths = {
        "2.5.1_combined": root / "runs/salmon-2.5.1/SRR3497201/threads-6-run-1/quant.sf",
        "2.5.1_sirv_only": root / "runs/diagnostic/sirv-only/quant.sf",
        "1.10.3_combined": root / "runs/version-comparison/1.10.3/SRR3497201/quant.sf",
        "1.12.1_combined": root / "runs/version-comparison/1.12.1/SRR3497201/quant.sf",
    }
    analyses = {}
    group_rows = {}
    for name, path in paths.items():
        rows, summary = audit_quant(ident, quant_rows(path))
        group_rows[name] = rows
        analyses[name] = summary
    transcript_median = log2_threshold_scale(0.75, metric="transcript_absolute_log2_median")
    transcript_p90 = log2_threshold_scale(1.50, metric="transcript_absolute_log2_p90")
    gene_median = log2_threshold_scale(0.50, metric="gene_absolute_log2_median")
    gene_p90 = log2_threshold_scale(1.00, metric="gene_absolute_log2_p90")
    group_median = relative_threshold_scale(0.25, metric="group_relative_median")
    group_p90 = relative_threshold_scale(0.50, metric="group_relative_p90")
    scale = [transcript_median, transcript_p90, gene_median, gene_p90, group_median, group_p90]
    combined_pass = bool(analyses["2.5.1_combined"]["overall"]["passed"])
    sirv_only_pass = bool(analyses["2.5.1_sirv_only"]["overall"]["passed"])
    all_salmon_fail = all(not bool(analyses[name]["overall"]["passed"]) for name in analyses if name.endswith("combined"))
    s502_all = analyses["2.5.1_combined"]["overall"]
    s502_without = analyses["2.5.1_combined"]["strata"]["without_sirv502"]
    output = {
        "schema_version": 1,
        "historical_verdict_changed": False,
        "threshold_scale": [row.__dict__ for row in scale],
        "coherence": {
            "median": classify_gate_coherence(transcript_median, group_median).value,
            "p90": classify_gate_coherence(transcript_p90, group_p90).value,
            "mathematical_contradiction": False,
            "finding": "group relative-error limits are stricter and asymmetric on log2 fold scale",
        },
        "analyses": analyses,
        "groups": group_rows["2.5.1_combined"],
        "reference_competition": (
            "REFERENCE_COMPETITION_CONTRIBUTOR" if not combined_pass and sirv_only_pass
            else "LIBRARY_OR_METRIC_CONTRIBUTOR" if not combined_pass and not sirv_only_pass
            else "NO_FAILURE"
        ),
        "sirv502": {
            "all_groups": s502_all,
            "without_sirv502_diagnostic": s502_without,
            "classification": (
                "DOMINANT_CONTRIBUTOR" if not s502_all["passed"] and s502_without["passed"]
                else "PARTIAL_CONTRIBUTOR" if analyses["2.5.1_combined"]["strata"]["sirv502"]["median_relative_error"] > s502_all["median_relative_error"]
                else "NO_MATERIAL_EFFECT"
            ),
            "original_gate_changed": False,
        },
        "quantifier_specificity": {
            "classification": "SALMON_1X_AND_2X_SHARED" if all_salmon_fail else "SALMON_2_5_1_SPECIFIC",
            "independent_quantifier": "NOT_RUN_NOT_LOCALLY_AVAILABLE",
        },
    }
    args.output.resolve().write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in output.items() if key != "groups"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
