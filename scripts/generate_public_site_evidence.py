"""Generate deterministic public benchmark JSON and accessible SVGs.

Only committed qualification JSON and an explicitly supplied verified evidence
bundle are accepted. Private source paths are never copied to the public site.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from statistics import median
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
QUALIFICATION = ROOT / "docs" / "qualification"
SITE_DATA = ROOT / "site" / "assets" / "data"
SITE_CHARTS = ROOT / "site" / "assets" / "charts"

SOURCES = {
    "one_pass": (
        QUALIFICATION / "native-high-memory-full-human-one-pass.json",
        "4c8017e5f37fe9b530c41ca18e56ac7bc5890ff53534910dd252d720508cca68",
    ),
    "two_pass": (
        QUALIFICATION / "native-high-memory-full-human-two-pass.json",
        "6f1511fe70997337971f2849d9b7ee0793d9b57692510788173d69419baed1db",
    ),
    "salmon": (
        QUALIFICATION / "salmon-1.10.3-vs-2.5.1-c1-comparison.json",
        "00ac39f2b18cb2b4053bb1c0141f523d9294707e5eb029bdf876b76d79972d3b",
    ),
    "parity": (
        QUALIFICATION / "harako-native-vs-nfcore-c1-parity.json",
        "8ee18a091408dc4433725ed7515bb3b2210395beede91487ce0adebbc4a37ccc",
    ),
    "gui": (
        QUALIFICATION / "ubuntu-native-gui-scientific-launch.json",
        "e6ce232a2c7a010705cf788afe0cd510e9b93685bc277fda45a12fff56ac7eee",
    ),
}

EXTERNAL = {
    "evidence-source-map.json": "0dbece6a8896d271fabeac9f6dfa61371b80b137d1b36a9d74ae0db90b01ff02",
    "host-capability-evidence.json": "d13224114bdd9990bb4d299a654982380fcb85c253e95ee99120447be758f324",
    "f2/final-report.md": "48b3af66048e4e111c880c04aa0d1ee48b6679a6cb332a2718fb867e8ce16569",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_sources() -> tuple[dict[str, Any], list[dict[str, str]]]:
    payloads: dict[str, Any] = {}
    records: list[dict[str, str]] = []
    for name, (path, expected) in SOURCES.items():
        observed = sha256(path)
        if observed != expected:
            raise ValueError(f"qualification source SHA-256 mismatch: {path}")
        payloads[name] = json.loads(path.read_text(encoding="utf-8"))
        records.append({
            "id": name,
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": observed,
        })
    return payloads, records


def validate_classifications(data: dict[str, Any]) -> None:
    expected = {
        "one_pass": "FULL_SIZE_ONE_PASS_END_TO_END_QUALIFIED",
        "two_pass": "FULL_SIZE_TWO_PASS_END_TO_END_QUALIFIED_96GB",
        "salmon": "SALMON_1103_VS_251_C1_TIME_AND_CONCORDANCE_COMPLETED",
        "parity": "HARAKO_NATIVE_C1_ONE_PASS_TWO_PASS_STRICT_SCIENTIFIC_PARITY",
        "gui": "UBUNTU_NATIVE_GUI_ONE_PASS_TWO_PASS_APPTEST_QUALIFIED_BROWSER_RUNTIME_BLOCKED",
    }
    for name, classification in expected.items():
        if data[name].get("classification") != classification:
            raise ValueError(f"unexpected {name} classification")
    if not data["one_pass"].get("terminal_success") or not data["two_pass"].get("terminal_success"):
        raise ValueError("full-human terminal qualification is incomplete")
    parity = data["parity"].get("parity", {})
    if parity.get("one_pass", {}).get("classification") != "STRICT_SCIENTIFIC_PARITY":
        raise ValueError("one-pass parity classification mismatch")
    if parity.get("two_pass", {}).get("classification") != "STRICT_SCIENTIFIC_PARITY":
        raise ValueError("two-pass parity classification mismatch")


def load_external(bundle: Path) -> tuple[int, dict[str, Any], list[dict[str, str]]]:
    records: list[dict[str, str]] = []
    for relative, expected in EXTERNAL.items():
        path = bundle / relative
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"external evidence missing or SHA-256 mismatch: {relative}")
        records.append({
            "id": f"external:{relative}",
            "path": f"verified-external-bundle/{relative}",
            "sha256": expected,
        })
    source_map = json.loads((bundle / "evidence-source-map.json").read_text(encoding="utf-8"))
    if source_map.get("normalized_evidence_sha256") != (
        "d13224114bdd9990bb4d299a654982380fcb85c253e95ee99120447be758f324"
    ):
        raise ValueError("external evidence source-map identity mismatch")
    report = (bundle / "f2" / "final-report.md").read_text(encoding="utf-8")
    match = re.search(r"Parabricks task result.*?duration\s+(\d+)m(\d+)s", report)
    if not match:
        raise ValueError("two-pass Parabricks task duration is absent")
    normalized = json.loads((bundle / "host-capability-evidence.json").read_text(encoding="utf-8"))
    if normalized.get("evidence_bundle_id") != "ubuntu-high-memory-host-capability-v1":
        raise ValueError("external normalized evidence identity mismatch")
    return int(match.group(1)) * 60 + int(match.group(2)), normalized, records


def svg(title: str, description: str, rows: list[tuple[str, float, str]], *, maximum: float) -> str:
    width, left, top, row_height = 760, 230, 72, 62
    height = top + len(rows) * row_height + 48
    bars = []
    for index, (label, value, display) in enumerate(rows):
        y = top + index * row_height
        bar_width = 430 * value / maximum if maximum else 0
        bars.append(
            f'<text x="16" y="{y + 22}" class="label">{label}</text>'
            f'<rect x="{left}" y="{y}" width="{bar_width:.2f}" height="28" '
            f'fill="#176b52" stroke="#0d4b39" />'
            f'<text x="{left + bar_width + 10:.2f}" y="{y + 21}" class="value">{display}</text>'
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" role="img" '
        f'viewBox="0 0 {width} {height}" aria-labelledby="title desc">'
        f'<title id="title">{title}</title><desc id="desc">{description}</desc>'
        '<style>.label{font:600 15px system-ui;fill:#15211d}.value{font:700 14px system-ui;fill:#15211d}'
        '.heading{font:700 20px system-ui;fill:#15211d}</style>'
        f'<text x="16" y="34" class="heading">{title}</text>{"".join(bars)}</svg>\n'
    )


def build_public(data: dict[str, Any], external: dict[str, Any], two_pass_seconds: int) -> dict[str, Any]:
    salmon = data["salmon"]
    cross = salmon["cross_version"]
    metrics = ("transcript_tpm", "gene_tpm", "transcript_num_reads", "gene_num_reads")
    concordance = {
        metric: {
            "q1": cross["q1"][metric]["spearman"],
            "q2": cross["q2"][metric]["spearman"],
            "median": median((cross["q1"][metric]["spearman"], cross["q2"][metric]["spearman"])),
        }
        for metric in metrics
    }
    sensitive = {
        metric: {
            "q1": cross["q1"][metric]["method_sensitive_features"],
            "q2": cross["q2"][metric]["method_sensitive_features"],
        }
        for metric in metrics
    }
    one = data["one_pass"]
    two = data["two_pass"]
    return {
        "schema_version": 1,
        "public_display_version": "v0.1.0-alpha.1",
        "claim_boundary": {
            "research_use_only": True,
            "matched_cpu_benchmark": False,
            "general_speedup_ratio": None,
            "biological_truth": "NOT_EVALUATED",
            "cross_host_equality": "NOT_EVALUATED",
            "salmon_comparison_n": 2,
        },
        "gpu_observed": {
            "host": two["host"],
            "input": one["input"],
            "one_pass": {
                "classification": one["classification"],
                "cpus": one["resource_contract"]["cpus"],
                "memory_contract_bytes": one["resource_contract"]["memory_bytes"],
                "peak_host_ram_bytes": external["one_pass"]["resources"]["peak_ram_used_bytes"],
                "peak_vram_mib": external["one_pass"]["resources"]["peak_vram_mib"],
                "isolated_alignment_seconds": None,
                "duration_note": "The final FeatureCounts repair reused the cached alignment; no clean isolated one-pass task duration is published.",
            },
            "two_pass": {
                "classification": two["classification"],
                "cpus": two["resource_contract"]["cpus"],
                "memory_contract_bytes": two["resource_contract"]["memory_bytes"],
                "cgroup_peak_bytes": two["resource_contract"]["cgroup_memory_peak_bytes"],
                "peak_host_ram_bytes": external["two_pass"]["host"]["peak_ram_used_bytes"],
                "peak_vram_mib": external["two_pass"]["host"]["peak_vram_mib"],
                "isolated_alignment_seconds": two_pass_seconds,
            },
        },
        "salmon": {
            "fixture": salmon["fixture"],
            "median_wall_seconds": {
                "1.10.3": salmon["runtime"]["salmon_1_10_3_median_wall_seconds"],
                "2.5.1": salmon["runtime"]["salmon_2_5_1_median_wall_seconds"],
            },
            "median_wall_ratio_1_10_3_to_2_5_1": salmon["runtime"]["median_wall_time_ratio_1_10_3_to_2_5_1"],
            "spearman": concordance,
            "method_sensitive_features": sensitive,
            "repeatability": salmon["repeatability"],
            "policy": salmon["default_primary_policy"],
        },
        "parity": {
            "classification": data["parity"]["classification"],
            "one_pass": data["parity"]["parity"]["one_pass"]["classification"],
            "two_pass": data["parity"]["parity"]["two_pass"]["classification"],
        },
        "gui": {
            "classification": data["gui"]["classification"],
            "app_test": data["gui"]["gui"]["app_test"],
            "actual_browser": data["gui"]["gui"]["actual_browser"],
        },
    }


def write_outputs(public: dict[str, Any], source_records: list[dict[str, str]]) -> None:
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    SITE_CHARTS.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / "public-benchmark-summary.json").write_text(
        json.dumps(public, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    source_map = {
        "schema_version": 1,
        "generated_artifact": "site/assets/data/public-benchmark-summary.json",
        "sources": source_records,
        "private_paths_included": False,
    }
    (SITE_DATA / "evidence-source-map.json").write_text(
        json.dumps(source_map, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    salmon = public["salmon"]
    runtime = salmon["median_wall_seconds"]
    (SITE_CHARTS / "salmon-runtime.svg").write_text(svg(
        "Salmon median wall time (C1, n=2)",
        "Median wall time was 28.200 seconds for Salmon 1.10.3 and 22.658 seconds for Salmon 2.5.1.",
        [("Salmon 1.10.3", runtime["1.10.3"], f'{runtime["1.10.3"]:.3f} s'),
         ("Salmon 2.5.1", runtime["2.5.1"], f'{runtime["2.5.1"]:.3f} s')], maximum=30,
    ), encoding="utf-8")
    concordance = salmon["spearman"]
    (SITE_CHARTS / "salmon-concordance.svg").write_text(svg(
        "Cross-version Spearman concordance (median of Q1/Q2)",
        "Median Spearman correlations for transcript and gene TPM and estimated counts across two order-balanced comparisons.",
        [("Transcript TPM", concordance["transcript_tpm"]["median"], f'{concordance["transcript_tpm"]["median"]:.6f}'),
         ("Gene TPM", concordance["gene_tpm"]["median"], f'{concordance["gene_tpm"]["median"]:.6f}'),
         ("Transcript NumReads", concordance["transcript_num_reads"]["median"], f'{concordance["transcript_num_reads"]["median"]:.6f}'),
         ("Gene NumReads", concordance["gene_num_reads"]["median"], f'{concordance["gene_num_reads"]["median"]:.6f}')], maximum=1,
    ), encoding="utf-8")
    sensitive = salmon["method_sensitive_features"]
    max_sensitive = max(max(item["q1"], item["q2"]) for item in sensitive.values())
    (SITE_CHARTS / "method-sensitive-features.svg").write_text(svg(
        "Method-sensitive feature counts (Q1/Q2)",
        "Descriptive counts of features crossing the frozen method-sensitivity threshold in two order-balanced comparisons.",
        [("Transcript TPM", max(sensitive["transcript_tpm"].values()), f'Q1 {sensitive["transcript_tpm"]["q1"]:,} / Q2 {sensitive["transcript_tpm"]["q2"]:,}'),
         ("Gene TPM", max(sensitive["gene_tpm"].values()), f'Q1 {sensitive["gene_tpm"]["q1"]:,} / Q2 {sensitive["gene_tpm"]["q2"]:,}'),
         ("Transcript NumReads", max(sensitive["transcript_num_reads"].values()), f'Q1 {sensitive["transcript_num_reads"]["q1"]:,} / Q2 {sensitive["transcript_num_reads"]["q2"]:,}'),
         ("Gene NumReads", max(sensitive["gene_num_reads"].values()), f'Q1 {sensitive["gene_num_reads"]["q1"]:,} / Q2 {sensitive["gene_num_reads"]["q2"]:,}')], maximum=max_sensitive,
    ), encoding="utf-8")
    gpu = public["gpu_observed"]
    gib = 1024 ** 3
    (SITE_CHARTS / "gpu-alignment-observed.svg").write_text(svg(
        "Observed full-human alignment resource envelope",
        "Peak host RAM was 49.35 GiB for one-pass and 57.42 GiB for two-pass; the isolated two-pass Parabricks task took 850 seconds. One-pass isolated time was unavailable.",
        [("One-pass peak host RAM", gpu["one_pass"]["peak_host_ram_bytes"] / gib, f'{gpu["one_pass"]["peak_host_ram_bytes"] / gib:.2f} GiB'),
         ("Two-pass peak host RAM", gpu["two_pass"]["peak_host_ram_bytes"] / gib, f'{gpu["two_pass"]["peak_host_ram_bytes"] / gib:.2f} GiB')], maximum=128,
    ), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--external-bundle", type=Path, required=True)
    args = parser.parse_args()
    data, records = load_sources()
    validate_classifications(data)
    two_pass_seconds, external, external_records = load_external(args.external_bundle)
    write_outputs(build_public(data, external, two_pass_seconds), records + external_records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
