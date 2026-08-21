"""Summarize isolated Salmon qualification outputs without executing commands."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import statistics
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from harako_gpu.services.salmon_reproducibility import (
    ExpressionRow,
    ExpressionTable,
    ReproducibilityClass,
    TOLERANCE_SCHEMA_VERSION,
    TpmStratum,
    aggregate_by_gene,
    canonical_numerical_digest,
    classify_reproducibility,
    compare_expression_tables,
    compare_quant_tables,
    parse_quant_sf,
    parse_salmon_metadata,
    parse_transcript_gene_map,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def uncompressed_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with gzip.open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def portable(value: Any) -> Any:
    if is_dataclass(value):
        return portable(asdict(value))
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(portable(key)): portable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [portable(item) for item in value]
    return value


def _read_runtime_metrics(run_root: Path) -> dict[str, Any]:
    path = run_root / "run-metrics.tsv"
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        name, value = line.split("\t", 1)
        values[name] = value
    return {
        "exit_code": int(values["exit_code"]),
        "elapsed_seconds": int(values["elapsed_nanoseconds"]) / 1_000_000_000,
        "threads": int(values["threads"]),
    }


def _output_inventory(output: Path) -> dict[str, Any]:
    roles = {
        "quant_sf": output / "quant.sf",
        "gene_quant_sf": output / "quant.genes.sf",
        "meta_info": output / "aux_info" / "meta_info.json",
        "fragment_length_distribution": output / "aux_info" / "fld.gz",
        "expected_bias": output / "aux_info" / "expected_bias.gz",
        "observed_bias": output / "aux_info" / "observed_bias.gz",
        "observed_bias_3p": output / "aux_info" / "observed_bias_3p.gz",
        "command_info": output / "cmd_info.json",
    }
    inventory: dict[str, Any] = {}
    for role, path in roles.items():
        if not path.is_file():
            inventory[role] = {"present": False}
            continue
        item: dict[str, Any] = {
            "present": True,
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        if path.suffix == ".gz":
            item["uncompressed_sha256"] = uncompressed_sha256(path)
        inventory[role] = item
    return inventory


def _gene_expression(output: Path, quant, transcript_to_gene) -> ExpressionTable:
    gene_quant_path = output / "quant.genes.sf"
    if not gene_quant_path.is_file():
        return aggregate_by_gene(quant, transcript_to_gene)
    gene_quant = parse_quant_sf(gene_quant_path.read_text(encoding="utf-8"))
    return ExpressionTable(
        tuple(
            ExpressionRow(row.transcript_id, row.tpm, row.num_reads)
            for row in gene_quant.rows
        )
    )


def _run_payload(
    run_root: Path,
    baseline_quant,
    baseline_gene,
    transcript_to_gene,
) -> dict[str, Any]:
    output = run_root / "WT_REP1"
    quant = parse_quant_sf((output / "quant.sf").read_text(encoding="utf-8"))
    metadata = parse_salmon_metadata(
        (output / "aux_info" / "meta_info.json").read_text(encoding="utf-8")
    )
    gene = _gene_expression(output, quant, transcript_to_gene)
    transcript_comparison = compare_quant_tables(baseline_quant, quant)
    gene_comparison = compare_expression_tables(baseline_gene, gene)
    metadata_exact = metadata == parse_salmon_metadata(
        (
            baseline_quant_output(run_root)
            / "aux_info"
            / "meta_info.json"
        ).read_text(encoding="utf-8")
    )
    return {
        "role": run_root.parent.name if run_root.name == "salmon" else run_root.name,
        "runtime": _read_runtime_metrics(run_root),
        "metadata": portable(metadata),
        "canonical_numerical_digest": canonical_numerical_digest(quant),
        "inventory": _output_inventory(output),
        "comparison_to_group_baseline": portable(transcript_comparison),
        "gene_comparison_to_group_baseline": portable(gene_comparison),
        "reproducibility_class_to_group_baseline": classify_reproducibility(
            quant_byte_identical=(
                sha256(output / "quant.sf")
                == sha256(baseline_quant_output(run_root) / "quant.sf")
            ),
            transcript=transcript_comparison,
            gene=gene_comparison,
            metadata_exact=metadata_exact,
        ).value,
    }


_GROUP_BASELINES: dict[Path, Path] = {}


def baseline_quant_output(run_root: Path) -> Path:
    for group_root, output in _GROUP_BASELINES.items():
        if run_root.is_relative_to(group_root):
            return output
    raise ValueError(f"No group baseline registered for {run_root}")


def _max_decimal(items: Iterable[Decimal]) -> Decimal:
    return max(items, default=Decimal(0))


def summarize_group(run_roots: list[Path], transcript_to_gene) -> dict[str, Any]:
    if not run_roots:
        return {"status": "NOT_RUN", "run_count": 0}
    run_roots = sorted(run_roots)
    baseline_output = run_roots[0] / "WT_REP1"
    group_root = Path(*Path(run_roots[0]).parts[:-1])
    while group_root.name.startswith("run-") or group_root.name.startswith("threads-"):
        group_root = group_root.parent
    _GROUP_BASELINES[group_root] = baseline_output
    baseline_quant = parse_quant_sf((baseline_output / "quant.sf").read_text(encoding="utf-8"))
    baseline_gene = _gene_expression(
        baseline_output, baseline_quant, transcript_to_gene
    )

    parsed = []
    metadata = []
    for root in run_roots:
        output = root / "WT_REP1"
        quant = parse_quant_sf((output / "quant.sf").read_text(encoding="utf-8"))
        parsed.append((root, quant, _gene_expression(output, quant, transcript_to_gene)))
        metadata.append(
            parse_salmon_metadata(
                (output / "aux_info" / "meta_info.json").read_text(encoding="utf-8")
            )
        )

    transcript_pairs = []
    gene_pairs = []
    pair_classes: list[ReproducibilityClass] = []
    quant_shas = []
    gene_quant_shas = []
    canonical_digests = []
    for root, quant, _ in parsed:
        quant_shas.append(sha256(root / "WT_REP1" / "quant.sf"))
        gene_quant_shas.append(sha256(root / "WT_REP1" / "quant.genes.sf"))
        canonical_digests.append(canonical_numerical_digest(quant))
    for left_index, right_index in itertools.combinations(range(len(parsed)), 2):
        _, left_quant, left_gene = parsed[left_index]
        _, right_quant, right_gene = parsed[right_index]
        transcript = compare_quant_tables(left_quant, right_quant)
        gene = compare_expression_tables(left_gene, right_gene)
        transcript_pairs.append(transcript)
        gene_pairs.append(gene)
        pair_classes.append(
            classify_reproducibility(
                quant_byte_identical=quant_shas[left_index] == quant_shas[right_index],
                transcript=transcript,
                gene=gene,
                metadata_exact=metadata[left_index] == metadata[right_index],
            )
        )

    class_rank = {
        ReproducibilityClass.EXACT: 0,
        ReproducibilityClass.BOUNDED_NUMERICAL: 1,
        ReproducibilityClass.MATERIAL_VARIABILITY: 2,
    }
    overall_class = max(pair_classes, key=class_rank.get) if pair_classes else ReproducibilityClass.EXACT
    runtimes = [_read_runtime_metrics(root)["elapsed_seconds"] for root in run_roots]
    high = [
        comparison.strata[TpmStratum.HIGH].max_relative_difference or Decimal(0)
        for comparison in transcript_pairs
    ]
    middle = [
        comparison.strata[TpmStratum.MIDDLE].max_absolute_difference
        for comparison in transcript_pairs
    ]
    low = [
        comparison.strata[TpmStratum.LOW].max_absolute_difference
        for comparison in transcript_pairs
    ]
    gene_high = [
        comparison.strata[TpmStratum.HIGH].max_relative_difference or Decimal(0)
        for comparison in gene_pairs
    ]
    return {
        "status": "PASS" if overall_class is not ReproducibilityClass.MATERIAL_VARIABILITY else "FAIL",
        "run_count": len(run_roots),
        "pair_count": len(transcript_pairs),
        "reproducibility_class": overall_class.value,
        "quant_sf_byte_identical": len(set(quant_shas)) == 1,
        "quant_sf_distinct_sha256_count": len(set(quant_shas)),
        "gene_quant_sf_byte_identical": len(set(gene_quant_shas)) == 1,
        "gene_quant_sf_distinct_sha256_count": len(set(gene_quant_shas)),
        "canonical_numerical_digest_distinct_count": len(set(canonical_digests)),
        "metadata_identity_exact": len(set(metadata)) == 1,
        "processed_fragments_exact": len({item.num_processed for item in metadata}) == 1,
        "mapped_fragments_exact": len({item.num_mapped for item in metadata}) == 1,
        "library_type_exact": len({item.library_types for item in metadata}) == 1,
        "processed_fragments": metadata[0].num_processed,
        "mapped_fragments": metadata[0].num_mapped,
        "library_types": list(metadata[0].library_types),
        "transcript_id_set_exact": all(item.id_set_equal for item in transcript_pairs),
        "transcript_row_order_exact": all(item.row_order_equal for item in transcript_pairs),
        "gene_id_set_exact": all(item.id_set_equal for item in gene_pairs),
        "gene_row_order_exact": all(item.row_order_equal for item in gene_pairs),
        "transcript_length_exact": all(item.length_exact for item in transcript_pairs),
        "total_num_reads_exact": all(item.total_num_reads_exact for item in transcript_pairs),
        "num_reads_max_absolute_difference": portable(
            _max_decimal(item.num_reads_max_absolute_difference for item in transcript_pairs)
        ),
        "effective_length_max_absolute_difference": portable(
            _max_decimal(
                item.effective_length_max_absolute_difference for item in transcript_pairs
            )
        ),
        "effective_length_median_absolute_difference_max": max(
            (item.effective_length_median_absolute_difference for item in transcript_pairs),
            default=0.0,
        ),
        "effective_length_p95_absolute_difference_max": max(
            (item.effective_length_p95_absolute_difference for item in transcript_pairs),
            default=0.0,
        ),
        "tpm_max_absolute_difference": portable(
            _max_decimal(item.tpm_max_absolute_difference for item in transcript_pairs)
        ),
        "tpm_max_relative_difference": portable(
            _max_decimal(item.tpm_max_relative_difference for item in transcript_pairs)
        ),
        "tpm_median_relative_difference_max": max(
            (item.tpm_median_relative_difference for item in transcript_pairs),
            default=0.0,
        ),
        "tpm_p95_relative_difference_max": max(
            (item.tpm_p95_relative_difference for item in transcript_pairs),
            default=0.0,
        ),
        "transcript_tpm_pearson_min": min(
            (item.tpm_pearson for item in transcript_pairs), default=1.0
        ),
        "transcript_tpm_spearman_min": min(
            (item.tpm_spearman for item in transcript_pairs), default=1.0
        ),
        "gene_num_reads_max_absolute_difference": portable(
            _max_decimal(item.num_reads_max_absolute_difference for item in gene_pairs)
        ),
        "gene_tpm_max_absolute_difference": portable(
            _max_decimal(item.tpm_max_absolute_difference for item in gene_pairs)
        ),
        "gene_tpm_max_relative_difference": portable(
            _max_decimal(item.tpm_max_relative_difference for item in gene_pairs)
        ),
        "gene_tpm_pearson_min": min(
            (item.tpm_pearson for item in gene_pairs), default=1.0
        ),
        "gene_tpm_spearman_min": min(
            (item.tpm_spearman for item in gene_pairs), default=1.0
        ),
        "zero_nonzero_transition_count": sum(
            len(item.zero_nonzero_transition_ids) for item in transcript_pairs
        ),
        "gene_zero_nonzero_transition_count": sum(
            len(item.zero_nonzero_transition_ids) for item in gene_pairs
        ),
        "strata_ceiling": {
            TpmStratum.LOW.value: {"max_absolute_difference": portable(_max_decimal(low))},
            TpmStratum.MIDDLE.value: {
                "max_absolute_difference": portable(_max_decimal(middle))
            },
            TpmStratum.HIGH.value: {
                "max_relative_difference": portable(_max_decimal(high))
            },
            "GENE_TPM_GE_1": {
                "max_relative_difference": portable(_max_decimal(gene_high))
            },
        },
        "runtime_seconds": {
            "minimum": min(runtimes),
            "median": statistics.median(runtimes),
            "maximum": max(runtimes),
        },
        "runs": [
            _run_payload(root, baseline_quant, baseline_gene, transcript_to_gene)
            for root in run_roots
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    transcript_to_gene = parse_transcript_gene_map(
        (root / "frozen" / "gene_map.gtf").read_text(encoding="utf-8")
    )
    experiment_a = sorted((root / "experiment-a").glob("run-*"))
    thread_groups = {
        str(threads): summarize_group(
            sorted((root / "experiment-b" / f"threads-{threads}").glob("run-*")),
            transcript_to_gene,
        )
        for threads in (1, 2, 4, 8)
    }
    experiment_b_all = sorted((root / "experiment-b").glob("threads-*/run-*"))
    experiment_c = sorted(
        path.parent.parent for path in (root / "experiment-c").glob("run-*/salmon/WT_REP1/quant.sf")
    )
    payload = {
        "schema_version": 1,
        "tolerance_schema_version": TOLERANCE_SCHEMA_VERSION,
        "experiment_a": summarize_group(experiment_a, transcript_to_gene),
        "experiment_b": {
            "by_thread_count": thread_groups,
            "all_thread_counts": summarize_group(experiment_b_all, transcript_to_gene),
        },
        "experiment_c": summarize_group(experiment_c, transcript_to_gene),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(portable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
