"""Build the frozen descriptive WT_REP1 alignment-profile comparison artifacts."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
from pathlib import Path
from statistics import mean

from harako_gpu.adapters.filesystem import sha256_path, write_new_text
from harako_gpu.adapters.wsl import linux_path_to_unc


def local(path: str, distribution: str) -> Path:
    return Path(linux_path_to_unc(path, distribution=distribution))


def star_metrics(path: Path) -> dict[str, float]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "|" not in line:
            continue
        key, value = (item.strip() for item in line.split("|", 1))
        clean = value.rstrip("%")
        try:
            rows[key] = float(clean)
        except ValueError:
            continue
    rows["Derived total mapped %"] = (
        rows.get("Uniquely mapped reads %", 0) + rows.get("% of reads mapped to multiple loci", 0)
    )
    rows["Derived non-annotated splices"] = (
        rows.get("Number of splices: Total", 0) - rows.get("Number of splices: Annotated (sjdb)", 0)
    )
    return rows


def junctions(path: Path) -> set[tuple[str, ...]]:
    result = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        columns = line.split("\t")
        if len(columns) >= 6:
            result.add(tuple(columns[:6]))
    return result


def selected_counts(path: Path) -> dict[str, float]:
    rows = csv.DictReader(path.read_text(encoding="utf-8").splitlines(), delimiter="\t")
    return {row["gene_id"]: float(row["count"]) for row in rows}


def ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    index = 0
    while index < len(order):
        end = index + 1
        while end < len(order) and values[order[end]] == values[order[index]]:
            end += 1
        rank = (index + end - 1) / 2 + 1
        for position in order[index:end]:
            result[position] = rank
        index = end
    return result


def pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2:
        return None
    lm, rm = mean(left), mean(right)
    numerator = sum((a - lm) * (b - rm) for a, b in zip(left, right, strict=True))
    denominator = math.sqrt(sum((a - lm) ** 2 for a in left) * sum((b - rm) ** 2 for b in right))
    return numerator / denominator if denominator else None


def resource_summary(path: Path) -> dict[str, float | int | None]:
    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines(), delimiter="\t"))
    numeric = lambda key: [float(row[key]) for row in rows if row.get(key) not in {None, ""}]
    total = numeric("ram_total_bytes")
    if not total:
        used, available = numeric("ram_used_bytes"), numeric("ram_available_bytes")
        total = [a + b for a, b in zip(used, available, strict=True)]
    return {
        "samples": len(rows),
        "peak_ram_bytes": int(max(numeric("ram_used_bytes"), default=0)),
        "total_ram_bytes": int(max(total, default=0)),
        "minimum_available_ram_bytes": int(min(numeric("ram_available_bytes"), default=0)),
        "peak_swap_used_bytes": int(max(numeric("swap_used_bytes"), default=0)),
        "peak_vram_mib": max(numeric("vram_used_mib"), default=0),
        "peak_gpu_utilization_percent": max(numeric("gpu_utilization_percent"), default=0),
        "peak_cpu_utilization_percent": max(numeric("cpu_utilization_percent"), default=0),
        "work_peak_bytes": int(max(numeric("work_peak_bytes"))) if numeric("work_peak_bytes") else None,
        "result_peak_bytes": int(max(numeric("result_peak_bytes"))) if numeric("result_peak_bytes") else None,
    }


def meta(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--one-pass-run", required=True)
    parser.add_argument("--two-pass-run", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--distribution", default="Ubuntu")
    args = parser.parse_args()
    one, two, output = (local(value, args.distribution) for value in
                        (args.one_pass_run, args.two_pass_run, args.output))
    if output.exists():
        raise SystemExit("comparison output already exists")
    output.mkdir(parents=True)
    sample = "WT_REP1"
    one_alignment, two_alignment = one / f"results/alignment/{sample}", two / f"results/alignment/{sample}"
    one_star = star_metrics(one_alignment / f"{sample}.Log.final.out")
    two_star = star_metrics(two_alignment / f"{sample}.Log.final.out")
    keys = (
        "Number of input reads", "Uniquely mapped reads %", "Derived total mapped %",
        "% of reads mapped to multiple loci", "Number of splices: Total",
        "Number of splices: Annotated (sjdb)", "Derived non-annotated splices",
    )
    write_new_text(output / "mapping-metrics.tsv", "metric\tone_pass\ttwo_pass\tdelta\n" + "".join(
        f"{key}\t{one_star.get(key)}\t{two_star.get(key)}\t{one_star.get(key, 0)-two_star.get(key, 0)}\n"
        for key in keys[:4]))
    one_junctions = junctions(one_alignment / f"{sample}.SJ.out.tab")
    two_junctions = junctions(two_alignment / f"{sample}.SJ.out.tab")
    splice_rows = [(key, one_star.get(key), two_star.get(key)) for key in keys[4:]] + [
        ("SJ unique rows", len(one_junctions), len(two_junctions)),
        ("SJ overlap", len(one_junctions & two_junctions), len(one_junctions & two_junctions)),
        ("SJ one-pass only", len(one_junctions - two_junctions), 0),
        ("SJ two-pass only", 0, len(two_junctions - one_junctions)),
    ]
    write_new_text(output / "splice-metrics.tsv", "metric\tone_pass\ttwo_pass\n" + "".join(
        f"{key}\t{left}\t{right}\n" for key, left, right in splice_rows))
    one_counts = selected_counts(one / f"results/alignment/star_gene_counts/{sample}.selected_gene_counts.tsv")
    two_counts = selected_counts(two / f"results/alignment/star_gene_counts/{sample}.selected_gene_counts.tsv")
    common = sorted(one_counts.keys() & two_counts.keys())
    left, right = [one_counts[key] for key in common], [two_counts[key] for key in common]
    transitions = sum((a == 0) != (b == 0) for a, b in zip(left, right, strict=True))
    correlation = pearson(ranks(left), ranks(right))
    write_new_text(output / "gene-counts-concordance.tsv",
                   "common_genes\tspearman\tzero_nonzero_transitions\n"
                   f"{len(common)}\t{correlation}\t{transitions}\n")
    one_bam = meta(one_alignment / "bam-validation.json")
    two_bam = meta(two_alignment / "bam-validation.json")
    def bam_count(value: dict) -> int:
        for line in value["checksum"].splitlines():
            if line.startswith("all"):
                return int(line.split()[2])
        raise ValueError("BAM checksum lacks all-record row")
    write_new_text(output / "bam-metrics.tsv", "metric\tone_pass\ttwo_pass\n"
                   f"records\t{bam_count(one_bam)}\t{bam_count(two_bam)}\n"
                   f"quickcheck\t{one_bam['quickcheck']}\t{two_bam['quickcheck']}\n")
    one_resources = resource_summary(one / "execution/attempts/0001/resource-monitor.tsv")
    two_resources = resource_summary(two / "execution/attempts/0001/resource-monitor.tsv")
    write_new_text(output / "resource-comparison.tsv", "metric\tone_pass\ttwo_pass\n" + "".join(
        f"{key}\t{one_resources[key]}\t{two_resources[key]}\n" for key in one_resources))
    profile = "salmon_2_5_1_deterministic"
    oq = one / f"results/quantification/{profile}/{sample}/quant.sf"
    tq = two / f"results/quantification/{profile}/{sample}/quant.sf"
    p1103 = "salmon_1_10_3_compatibility"
    one_1103 = one / f"results/quantification/{p1103}/{sample}/quant.sf"
    two_1103 = two / f"results/quantification/{p1103}/{sample}/quant.sf"
    one_meta = meta(one / f"results/quantification/{p1103}/{sample}/aux_info/meta_info.json")
    two_meta = meta(two / f"results/quantification/{p1103}/{sample}/aux_info/meta_info.json")
    manifest = {
        "schema_version": 1, "comparison_kind": "descriptive_not_equivalence",
        "one_pass_run_id": meta(one / "run.json")["identity"]["run_id"],
        "two_pass_run_id": meta(two / "run.json")["identity"]["run_id"],
        "parameter_delta": {"--two-pass-mode": {"one_pass": "None", "two_pass": "Basic"}},
        "junctions": {"one_pass": len(one_junctions), "two_pass": len(two_junctions),
                      "overlap": len(one_junctions & two_junctions)},
        "gene_counts": {"common_genes": len(common), "spearman": correlation,
                        "zero_nonzero_transitions": transitions},
        "salmon_2_5_1": {"quant_sf_byte_identical": sha256_path(oq) == sha256_path(tq),
                          "one_pass_sha256": sha256_path(oq), "two_pass_sha256": sha256_path(tq)},
        "salmon_1_10_3": {"feature_ids_identical": [line.split("\t", 1)[0] for line in one_1103.read_text().splitlines()] ==
                                                    [line.split("\t", 1)[0] for line in two_1103.read_text().splitlines()],
                            "processed_fragments_identical": one_meta.get("num_processed") == two_meta.get("num_processed"),
                            "one_num_processed": one_meta.get("num_processed"), "two_num_processed": two_meta.get("num_processed")},
        "resources": {"one_pass": one_resources, "two_pass": two_resources},
        "limitations": ["descriptive comparison only", "not an equivalence claim",
                        "one-pass novel-junction sensitivity may be lower"],
    }
    html_text = """<!doctype html><html><meta charset='utf-8'><title>Alignment profile comparison</title><body>
<h1>One-pass / two-pass descriptive comparison</h1>
<p>This is not a correct/incorrect or equivalence verdict.</p>
<p>The workstation profile is annotation-backed one-pass alignment. It is intended for BAM generation,
GeneCounts, and known-gene expression analysis. Novel or low-abundance splice-junction sensitivity may be lower.</p>
<table><tr><th>Metric</th><th>One-pass</th><th>Two-pass</th></tr>""" + "".join(
        f"<tr><td>{html.escape(key)}</td><td>{left}</td><td>{right}</td></tr>" for key, left, right in splice_rows
    ) + "</table></body></html>"
    write_new_text(output / "summary.html", html_text)
    manifest["report_sha256"] = sha256_path(output / "summary.html")
    manifest["artifact_sha256"] = {path.name: sha256_path(path) for path in sorted(output.iterdir())}
    write_new_text(output / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
