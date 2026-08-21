"""Descriptive profile and STAR concordance without correctness claims."""

from __future__ import annotations

import csv
import html
import io
import math
import statistics
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Iterable, Mapping, Sequence


PSEUDOCOUNT = 0.1
ORTHOGONAL_GENE_CONCORDANCE_ARTIFACT = "star_salmon_gene_concordance.tsv"


@dataclass(frozen=True)
class QuantRow:
    feature_id: str
    length: float
    effective_length: float
    tpm: float
    num_reads: float


def parse_quant_sf(text: str, *, expected_ids: Iterable[str] | None = None) -> tuple[QuantRow, ...]:
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    if reader.fieldnames != ["Name", "Length", "EffectiveLength", "TPM", "NumReads"]:
        raise ValueError("quant.sf must contain the exact Salmon column schema")
    rows: list[QuantRow] = []
    seen: set[str] = set()
    for source in reader:
        feature = source["Name"]
        if not feature or feature in seen:
            raise ValueError("quant.sf contains an empty or duplicate feature ID")
        seen.add(feature)
        try:
            values = tuple(float(source[key]) for key in ("Length", "EffectiveLength", "TPM", "NumReads"))
        except ValueError as exc:
            raise ValueError("quant.sf contains a nonnumeric value") from exc
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("quant.sf contains negative or non-finite values")
        rows.append(QuantRow(feature, *values))
    if not rows:
        raise ValueError("quant.sf is empty")
    if expected_ids is not None:
        expected = set(expected_ids)
        if seen != expected:
            raise ValueError("quant.sf feature universe differs from the reference manifest")
    return tuple(rows)


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + end - 1) / 2 + 1
        for index in order[start:end]:
            result[index] = rank
        start = end
    return result


def pearson(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("Correlation requires equally sized vectors with at least two values")
    lm, rm = statistics.fmean(left), statistics.fmean(right)
    numerator = sum((a - lm) * (b - rm) for a, b in zip(left, right))
    denominator = math.sqrt(sum((a - lm) ** 2 for a in left) * sum((b - rm) ** 2 for b in right))
    return 1.0 if denominator == 0 and left == right else (math.nan if denominator == 0 else numerator / denominator)


def spearman(left: Sequence[float], right: Sequence[float]) -> float:
    return pearson(_ranks(left), _ranks(right))


def top_overlap(left: Mapping[str, float], right: Mapping[str, float], size: int) -> float:
    if size < 1:
        raise ValueError("Rank-overlap size must be positive")
    count = min(size, len(left), len(right))
    if not count:
        return 0.0
    ltop = {key for key, _ in sorted(left.items(), key=lambda item: (-item[1], item[0]))[:count]}
    rtop = {key for key, _ in sorted(right.items(), key=lambda item: (-item[1], item[0]))[:count]}
    return len(ltop & rtop) / count


class DescriptiveTier(StrEnum):
    A = "A_HIGH_CONCORDANCE"
    B = "B_MODERATE_METHOD_SENSITIVITY"
    C = "C_SUBSTANTIAL_METHOD_SENSITIVITY"


def descriptive_tier(*, gene_spearman: float, top100_overlap: float, high_zero_fraction: float) -> DescriptiveTier:
    if gene_spearman >= 0.99 and top100_overlap >= 0.90 and high_zero_fraction <= 0.005:
        return DescriptiveTier.A
    if gene_spearman >= 0.95 and top100_overlap >= 0.75 and high_zero_fraction <= 0.02:
        return DescriptiveTier.B
    return DescriptiveTier.C


@dataclass(frozen=True)
class SensitiveFeature:
    feature_id: str
    left_tpm: float
    right_tpm: float
    log2_ratio: float
    category: str


@dataclass(frozen=True)
class ConcordanceResult:
    common_features: int
    left_only: tuple[str, ...]
    right_only: tuple[str, ...]
    detected_left: int
    detected_right: int
    detected_both: int
    spearman: float
    log_pearson: float
    top50_overlap: float
    top100_overlap: float
    zero_transitions: int
    high_priority_zero_transitions: int
    sensitive_features: tuple[SensitiveFeature, ...]


def compare_abundance(left: Mapping[str, float], right: Mapping[str, float]) -> ConcordanceResult:
    common = sorted(set(left) & set(right))
    if len(common) < 2:
        raise ValueError("Concordance requires at least two common feature IDs")
    lvals, rvals = [left[key] for key in common], [right[key] for key in common]
    if any(not math.isfinite(value) or value < 0 for value in (*lvals, *rvals)):
        raise ValueError("Concordance values must be finite and nonnegative")
    sensitive: list[SensitiveFeature] = []
    zero = high_zero = 0
    for key, lvalue, rvalue in zip(common, lvals, rvals):
        zero += (lvalue == 0) != (rvalue == 0)
        high = max(lvalue, rvalue) >= 1 and min(lvalue, rvalue) < 0.1
        high_zero += high
        ratio = abs(math.log2((lvalue + PSEUDOCOUNT) / (rvalue + PSEUDOCOUNT)))
        category = "high_priority" if max(lvalue, rvalue) >= 1 and ratio >= 1 else (
            "moderate" if max(lvalue, rvalue) >= 1 and ratio >= 0.585 else "stable")
        if category != "stable":
            sensitive.append(SensitiveFeature(key, lvalue, rvalue, ratio, category))
    return ConcordanceResult(
        len(common), tuple(sorted(set(left) - set(right))), tuple(sorted(set(right) - set(left))),
        sum(value > 0 for value in left.values()), sum(value > 0 for value in right.values()),
        sum(left[key] > 0 and right[key] > 0 for key in common), spearman(lvals, rvals),
        pearson([math.log2(value + PSEUDOCOUNT) for value in lvals], [math.log2(value + PSEUDOCOUNT) for value in rvals]),
        top_overlap(left, right, 50), top_overlap(left, right, 100), zero, high_zero,
        tuple(sorted(sensitive, key=lambda item: (-item.log2_ratio, item.feature_id))),
    )


def compare_profile_runtimes(profiles: Mapping[str, Mapping[str, Any]],
                             versions: Mapping[str, str]) -> dict[str, Any]:
    """Validate and summarize descriptive per-profile controller timings."""
    if set(profiles) != set(versions) or set(versions.values()) != {"1.10.3", "2.5.1"}:
        raise ValueError("Runtime comparison requires exactly Salmon 1.10.3 and 2.5.1")
    by_version: dict[str, Mapping[str, Any]] = {}
    for profile_id, values in profiles.items():
        wall = float(values.get("wall_seconds", 0))
        rate = float(values.get("fragments_per_second", 0))
        order = int(values.get("execution_order", 0))
        if not math.isfinite(wall) or wall <= 0 or not math.isfinite(rate) or rate <= 0 or order not in {1, 2}:
            raise ValueError("Runtime metadata must be finite, positive, and sequential")
        by_version[versions[profile_id]] = values
    if {int(item["execution_order"]) for item in by_version.values()} != {1, 2}:
        raise ValueError("Runtime execution order must contain positions one and two")
    return {
        "profiles": {key: dict(value) for key, value in sorted(profiles.items())},
        "salmon_1_10_3_to_2_5_1_wall_time_ratio": (
            float(by_version["1.10.3"]["wall_seconds"])
            / float(by_version["2.5.1"]["wall_seconds"])
        ),
    }


@dataclass(frozen=True)
class StarSalmonResult:
    common_genes: int
    detected_both: int
    star_only: int
    salmon_only: int
    spearman: float
    log_pearson: float
    top50_overlap: float
    top100_overlap: float


def counts_to_cpm(counts: Mapping[str, float]) -> dict[str, float]:
    total = sum(counts.values())
    if total <= 0 or any(value < 0 or not math.isfinite(value) for value in counts.values()):
        raise ValueError("Counts must be finite, nonnegative, and have positive total")
    return {key: value * 1_000_000 / total for key, value in counts.items()}


def compare_orthogonal_gene_counts(star_counts: Mapping[str, int], salmon_estimated_counts: Mapping[str, float]) -> StarSalmonResult:
    star = counts_to_cpm(star_counts)
    salmon = counts_to_cpm(salmon_estimated_counts)
    common = sorted(set(star) & set(salmon))
    if len(common) < 2:
        raise ValueError("STAR/Salmon comparison requires common gene IDs")
    left, right = [star[key] for key in common], [salmon[key] for key in common]
    return StarSalmonResult(
        len(common), sum(star[key] > 0 and salmon[key] > 0 for key in common),
        sum(value > 0 and salmon.get(key, 0) == 0 for key, value in star.items()),
        sum(value > 0 and star.get(key, 0) == 0 for key, value in salmon.items()),
        spearman(left, right), pearson([math.log2(value + 1) for value in left], [math.log2(value + 1) for value in right]),
        top_overlap(star, salmon, 50), top_overlap(star, salmon, 100),
    )


# Backward-compatible service alias; command handlers use the neutral name so
# scientific/backend decisions remain outside the CLI composition layer.
compare_star_salmon_counts = compare_orthogonal_gene_counts


def annotation_strata(result: ConcordanceResult, annotations: Mapping[str, Mapping[str, str]]) -> tuple[dict[str, Any], ...]:
    groups: dict[str, list[SensitiveFeature]] = {}
    for item in result.sensitive_features:
        annotation = annotations.get(item.feature_id, {})
        biotype = annotation.get("gene_biotype", "unknown")
        transcript_class = annotation.get("transcript_class", "unknown")
        groups.setdefault(f"{biotype}|{transcript_class}", []).append(item)
    return tuple({
        "stratum": key, "method_sensitive_features": len(items),
        "median_absolute_log2_ratio": statistics.median(item.log2_ratio for item in items),
    } for key, items in sorted(groups.items()))


def parse_gtf_annotations(text: str) -> dict[str, dict[str, Any]]:
    genes: dict[str, dict[str, Any]] = {}
    transcripts: dict[str, set[str]] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        columns = line.split("\t")
        if len(columns) != 9:
            raise ValueError("GTF records must contain nine columns")
        attributes = {}
        for part in columns[8].rstrip(";").split(";"):
            fields = part.strip().split(" ", 1)
            if len(fields) == 2:
                attributes[fields[0]] = fields[1].strip('"')
        gene = attributes.get("gene_id")
        if not gene:
            continue
        start, end = int(columns[3]), int(columns[4])
        row = genes.setdefault(gene, {"gene_biotype": attributes.get("gene_biotype", attributes.get("gene_type", "unknown")),
                                      "seqname": columns[0], "start": start, "end": end})
        row["start"], row["end"] = min(row["start"], start), max(row["end"], end)
        if attributes.get("transcript_id"):
            transcripts.setdefault(gene, set()).add(attributes["transcript_id"])
    for gene, row in genes.items():
        count = len(transcripts.get(gene, set()))
        row["transcript_count"] = count
        row["transcript_class"] = "single_transcript" if count == 1 else ("multi_transcript" if count > 1 else "unknown")
        row["gene_length_span"] = row["end"] - row["start"] + 1
        row["mitochondrial"] = row["seqname"] in {"MT", "chrM", "M"}
        row["ribosomal"] = "rRNA" in row["gene_biotype"] or "ribosomal" in row["gene_biotype"].lower()
    return genes


def stratified_concordance(left: Mapping[str, float], right: Mapping[str, float],
                           annotations: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    groups: dict[str, list[str]] = {}
    for feature in sorted(set(left) & set(right)):
        row = annotations.get(feature, {})
        labels = [str(row.get("gene_biotype", "unknown")), str(row.get("transcript_class", "unknown"))]
        if row.get("mitochondrial"):
            labels.append("mitochondrial")
        if row.get("ribosomal"):
            labels.append("ribosomal")
        groups.setdefault("|".join(labels), []).append(feature)
    result = []
    for label, features in sorted(groups.items()):
        lvals, rvals = [left[key] for key in features], [right[key] for key in features]
        ratios = [abs(math.log2((a + PSEUDOCOUNT) / (b + PSEUDOCOUNT))) for a, b in zip(lvals, rvals)]
        sensitive = [ratio >= 1 and max(a, b) >= 1 for ratio, a, b in zip(ratios, lvals, rvals)]
        zeros = [(a == 0) != (b == 0) for a, b in zip(lvals, rvals)]
        result.append({"stratum": label, "features": len(features),
                       "profile_spearman": spearman(lvals, rvals) if len(features) >= 2 else None,
                       "median_absolute_log2_difference": statistics.median(ratios),
                       "method_sensitive_fraction": sum(sensitive) / len(features),
                       "zero_transition_fraction": sum(zeros) / len(features)})
    return tuple(result)


def stratified_orthogonal_concordance(
    star_counts: Mapping[str, float], salmon_estimated_counts: Mapping[str, float],
    annotations: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Compare STAR and Salmon within fixed annotation strata in count-CPM space."""
    star, salmon = counts_to_cpm(star_counts), counts_to_cpm(salmon_estimated_counts)
    groups: dict[str, list[str]] = {}
    for feature in sorted(set(star) & set(salmon)):
        row = annotations.get(feature, {})
        labels = [str(row.get("gene_biotype", "unknown")), str(row.get("transcript_class", "unknown"))]
        if row.get("mitochondrial"):
            labels.append("mitochondrial")
        if row.get("ribosomal"):
            labels.append("ribosomal")
        groups.setdefault("|".join(labels), []).append(feature)
    result = []
    for label, features in sorted(groups.items()):
        left = [star[key] for key in features]
        right = [salmon[key] for key in features]
        differences = [abs(math.log2(a + 1) - math.log2(b + 1)) for a, b in zip(left, right)]
        result.append({
            "stratum": label,
            "features": len(features),
            "star_profile_spearman": spearman(left, right) if len(features) >= 2 else None,
            "median_absolute_log2_cpm_difference": statistics.median(differences),
            "detection_discordance_fraction": sum((a == 0) != (b == 0) for a, b in zip(left, right)) / len(features),
        })
    return tuple(result)


def render_summary_html(*, analysis_series_id: str, project_id: str, primary_profile: Mapping[str, Any],
                        secondary_profile: Mapping[str, Any], reference_pack_id: str,
                        library_type: str, processed_fastq_identity: str,
                        transcript: ConcordanceResult, gene: ConcordanceResult,
                        star_status: str, star_results: Mapping[str, StarSalmonResult] | None = None) -> str:
    tier = descriptive_tier(
        gene_spearman=gene.spearman, top100_overlap=gene.top100_overlap,
        high_zero_fraction=gene.high_priority_zero_transitions / gene.common_features,
    )
    rows = "".join(
        f"<tr><td>{html.escape(item.feature_id)}</td><td>{item.left_tpm:.6g}</td><td>{item.right_tpm:.6g}</td><td>{item.log2_ratio:.4f}</td><td>{item.category}</td></tr>"
        for item in gene.sensitive_features[:100]
    )
    star = "Not available / 利用不可"
    if star_results:
        star = "; ".join(f"{html.escape(key)}: Spearman {value.spearman:.6f}" for key, value in star_results.items())
    return f"""<!doctype html><html lang=\"ja\"><head><meta charset=\"utf-8\"><title>Harako-GPU concordance</title><style>body{{font-family:system-ui,sans-serif;max-width:1100px;margin:auto;padding:2rem}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #bbb;padding:.35rem;text-align:left}}code{{overflow-wrap:anywhere}}</style></head><body>
<h1>Quantification concordance / 定量一致性</h1>
<p>Project: {html.escape(project_id)}<br>Analysis series: <code>{html.escape(analysis_series_id)}</code><br>Reference: <code>{html.escape(reference_pack_id)}</code><br>Library: {html.escape(library_type)}<br>Processed FASTQ: <code>{html.escape(processed_fastq_identity)}</code></p>
<h2>Profiles / プロファイル</h2><p>Primary: {html.escape(str(primary_profile['display_name_ja']))} / {html.escape(str(primary_profile['display_name_en']))} ({primary_profile['version']}, {primary_profile['reproducibility_class']})<br>Secondary: {html.escape(str(secondary_profile['display_name_ja']))} / {html.escape(str(secondary_profile['display_name_en']))} ({secondary_profile['version']}, {secondary_profile['reproducibility_class']})</p>
<h2>Concordance / 一致性</h2><p>Descriptive tier: {tier.value}; transcript Spearman {transcript.spearman:.6f}; gene Spearman {gene.spearman:.6f}; gene top-100 overlap {gene.top100_overlap:.2%}; high-priority zero transitions {gene.high_priority_zero_transitions}.</p>
<h2>STAR comparator</h2><p>Status: {html.escape(star_status)}. {star}</p>
<h2>Method-sensitive features / 方法依存feature</h2><table><tr><th>Feature</th><th>Primary TPM</th><th>Secondary TPM</th><th>|log2 ratio|</th><th>Category</th></tr>{rows}</table>
<h2>Interpretation / 解釈</h2><p>Profile differences do not necessarily mean error; they show sensitivity to quantification method/version. 差は必ずしもerrorを意味せず、quantification method/versionへの感度を示します。 Only the primary profile is eligible for downstream analysis; secondary and STAR results are robustness comparators. Primary profileだけがdownstream解析へ使用され、secondaryとSTARはrobustness comparatorです。 Version pinning is required for comparability. Analysis series must not be mixed. GPU acceleration applies to alignment; Salmon quantification is CPU. Research use only; non-diagnostic and non-clinical.</p>
</body></html>"""


def result_dict(result: ConcordanceResult | StarSalmonResult) -> dict[str, Any]:
    return asdict(result)
