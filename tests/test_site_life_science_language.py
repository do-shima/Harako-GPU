from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
ENGLISH_PAGES = (
    "index.html",
    "installation/index.html",
    "methods/index.html",
    "benchmarks/index.html",
    "outputs/index.html",
    "404.html",
)
JAPANESE_PAGES = (
    "ja/index.html",
    "ja/installation/index.html",
    "ja/methods/index.html",
    "ja/benchmarks/index.html",
    "ja/outputs/index.html",
)


class VisibleText(HTMLParser):
    """Extract reader-visible prose while excluding technical literals."""

    ignored = {"code", "pre", "script", "style"}

    def __init__(self) -> None:
        super().__init__()
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.ignored:
            self.depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self.ignored and self.depth:
            self.depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.depth and (value := " ".join(data.split())):
            self.parts.append(value)

    @property
    def text(self) -> str:
        return " ".join(self.parts)


def visible(relative: str) -> str:
    parser = VisibleText()
    parser.feed((SITE / relative).read_text(encoding="utf-8"))
    return parser.text


def joined(paths: tuple[str, ...]) -> str:
    return "\n".join(visible(path) for path in paths)


def sha256(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def test_japanese_copy_uses_life_science_terminology() -> None:
    text = joined(JAPANESE_PAGES)
    required = (
        "ペアエンドFASTQ",
        "発現量マトリックス",
        "biotype別QC",
        "座標順にソートされたBAM",
        "動作確認用の環境設定ファイル",
        "ERR188044の全36,349,964ペア",
        "最大メモリ使用量",
        "再現性",
        "比較実行Q1／Q2",
        "アーカイブ用の大容量ストレージ",
    )
    assert not [term for term in required if term not in text]


def test_japanese_copy_excludes_audit_and_infrastructure_shorthand() -> None:
    text = joined(JAPANESE_PAGES)
    prohibited = (
        "対になったFASTQ",
        "対のFASTQ",
        "座標順にsort",
        "行列",
        "生物型QC",
        "製品としてのRun",
        "科学解析",
        "科学的処理",
        "科学的出力",
        "ヒト全量データ",
        "ヒト全量BAM",
        "ホスト証明書",
        "ホスト検証証明書",
        "receipt",
        "qualification evidence",
        "terminal qualified",
        "terminal evidence",
        "public claim",
        "scientific parity",
        "method-sensitive feature",
        "silent merge",
        "role、identity、verification",
        "filenameの存在だけで",
        "evidenceに限定した",
        "candidate／unsupported",
        "fresh clone",
        "source install",
        "scientific asset",
        "provision",
        "exact process",
        "immutable lifecycle",
        "Version固定のclaim",
        "biological output",
        "public support channel",
        "WD Gold",
        "特徴量",
        "製品として",
    )
    assert not [phrase for phrase in prohibited if phrase in text]


def test_comparison_runs_are_not_described_as_biological_replicates() -> None:
    text = visible("ja/benchmarks/index.html")
    assert "比較実行Q1／Q2" in text
    assert "生物学的反復" not in text
    assert "反復1" not in text and "反復2" not in text


def test_english_copy_excludes_audit_style_wording() -> None:
    text = joined(ENGLISH_PAGES).casefold()
    prohibited = (
        "receipt-backed host",
        "exact host/assets",
        "owns the contract",
        "authority for artifacts",
        "terminal qualified",
        "bounded qc",
        "evidence-derived, deliberately narrow",
        "silent merge",
        "candidate only",
        "scientific identity",
        "frozen closure",
        "method-sensitive features",
        "wd gold",
    )
    assert not [phrase for phrase in prohibited if phrase in text]


def test_salmon_version_guidance_is_bilingual_and_not_rejection_language() -> None:
    japanese = joined(JAPANESE_PAGES)
    english = joined(ENGLISH_PAGES)
    assert "Salmon 2.5.1は、新規解析で使用する既定のバージョンです" in japanese
    assert "数値は完全には一致しませんでした" in japanese
    assert "同一の解析データセットへ統合しないでください" in japanese
    assert "Salmon 2.5.1 is the default for new analyses" in english
    assert "the numerical results were not identical" in english
    assert "explicitly accounting for the version difference" in english
    assert "1.10.3 is rejected" not in english.casefold()


def test_evidence_values_and_machine_readable_benchmark_are_unchanged() -> None:
    assert sha256("site/assets/data/public-benchmark-summary.json") == (
        "3a5a792ec61014007a4a78b2a76e8887140e5d418a31e2ad69d903a86becb7e0"
    )
    pages = joined(("benchmarks/index.html", "ja/benchmarks/index.html"))
    for value in (
        "36,349,964",
        "42 GB",
        "96 GB",
        "850",
        "80,275,611,648",
        "28.1998923805",
        "22.6584244570",
        "1.2445654566",
        "0.9537426073",
        "0.9889087428",
        "2,882",
        "2,883",
        "733",
        "731",
        "2,929",
        "2,925",
        "552",
        "554",
    ):
        assert value in pages


def test_chart_files_are_unchanged() -> None:
    expected = {
        "site/assets/charts/gpu-alignment-observed.svg": "0c5e12e3d30468fbed21a96088a16362497dd920bbce72201c454176977d133a",
        "site/assets/charts/method-sensitive-features.svg": "b67f9755d88765950047b2413327ed5c14388330bf812618833e12454c84b9e4",
        "site/assets/charts/salmon-concordance.svg": "327885d669ef48e42a56fd87c490a7a6b1eaac3e0c8192fa628faae469bd0f70",
        "site/assets/charts/salmon-runtime.svg": "14474092fcb6f5e51b02d414f9b6ee25e804d5320fd3f4a2bda3ca0ab2dccc2e",
    }
    assert {path: sha256(path) for path in expected} == expected


def test_links_and_claim_boundaries_remain_visible() -> None:
    html = "\n".join((SITE / page).read_text(encoding="utf-8") for page in (*ENGLISH_PAGES, *JAPANESE_PAGES))
    assert "https://github.com/do-shima/Harako-GPU/releases/tag/v0.1.0-alpha.1" in html
    assert "https://do-shima.github.io/harako-rnaseq/" in html
    assert "not a matched CPU STAR benchmark" in html
    assert "一般的なGPUの速度向上率" in html
    assert not re.search(r"\d+(?:\.\d+)?\s*[x×]\s*(?:CPU|faster)", html, re.IGNORECASE)
    for private in ("/home/do/", r"C:\Users\do", r"\\do-OMEN"):
        assert private not in html
