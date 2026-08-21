from __future__ import annotations

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
RELEASE_URL = "https://github.com/do-shima/Harako-GPU/releases/tag/v0.1.0-alpha.1"


class VisibleTextParser(HTMLParser):
    """Collect prose while excluding code and non-rendered document content."""

    IGNORED = {"code", "pre", "script", "style"}

    def __init__(self) -> None:
        super().__init__()
        self._ignored_depth = 0
        self.parts: list[str] = []
        self.title = ""
        self.description = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.IGNORED:
            self._ignored_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            values = dict(attrs)
            if values.get("name") == "description":
                self.description = values.get("content") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag in self.IGNORED and self._ignored_depth:
            self._ignored_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if not value:
            return
        if self._in_title:
            self.title += value
        if not self._ignored_depth:
            self.parts.append(value)

    @property
    def text(self) -> str:
        return " ".join(self.parts)


def parse(relative: str) -> VisibleTextParser:
    parser = VisibleTextParser()
    parser.feed((SITE / relative).read_text(encoding="utf-8"))
    return parser


def combined(paths: tuple[str, ...]) -> str:
    return "\n".join(parse(path).text for path in paths)


def test_japanese_visible_copy_excludes_internal_audit_phrases() -> None:
    text = combined(JAPANESE_PAGES)
    prohibited = (
        "receiptで検証された",
        "receipt付き",
        "hostに限定した",
        "local・immutable plan型",
        "必要な処理に絞ったnative workflow",
        "公開claim",
        "full-human terminal evidence",
        "scientific parity",
        "実browser runtime",
        "assetとreceiptもruntime contractです",
        "fresh cloneからのsource install",
        "scientific assetは別途provision",
        "candidate／unsupported",
        "科学identityをfreezeする",
        "Harako-native execution",
        "alignment profile",
        "exact process",
        "Version固定のclaim",
        "immutable lifecycle",
        "evidenceに限定した記述",
        "full-human GPU alignment観測",
        "cross-version concordance",
        "method-sensitive feature",
        "role、identity、verificationを明示",
        "filenameの存在だけで",
        "terminal-results archive policy",
        "biological outputをpublic support channelへ",
    )
    assert not [phrase for phrase in prohibited if phrase in text]


def test_english_visible_copy_excludes_internal_audit_phrases() -> None:
    text = combined(ENGLISH_PAGES).casefold()
    prohibited = (
        "receipt-backed host",
        "narrowly qualified host",
        "owns the qualified contract",
        "keeps only the qualified path",
        "authority for expected artifacts",
        "exact host/assets",
        "exact process resources",
        "bounded qc/report aggregation",
        "terminal qualified",
        "silent merge",
        "candidate only",
        "exact receipt-backed ubuntu/nvidia host",
        "exact assets and receipts are part of the runtime contract",
        "evidence-derived, deliberately narrow",
    )
    assert not [phrase for phrase in prohibited if phrase in text]


def test_japanese_prose_uses_natural_version_and_workflow_terms() -> None:
    text = combined(JAPANESE_PAGES)
    assert not re.search(r"(?i)(?<![A-Za-z0-9_.-])version(?![A-Za-z0-9_.-])", text)
    assert not re.search(r"(?i)(?<![A-Za-z0-9_.-])workflow(?![A-Za-z0-9_.-])", text)
    for phrase in ("receiptで", "claim", "silent merge"):
        assert phrase not in text
    assert "数値は完全には一致しません" in text
    assert "これは単純な丸め誤差だけを指すものではありません" in text


def test_salmon_compatibility_is_explained_without_rejection_language() -> None:
    english = combined(ENGLISH_PAGES)
    japanese = combined(JAPANESE_PAGES)
    assert "Salmon 1.10.3 remains available for compatibility" in english
    assert "highly concordant, but not numerically identical" in english
    assert "Salmon 1.10.3も互換性のため選択して実行できます" in japanese
    combined_text = f"{english}\n{japanese}".casefold()
    assert "salmon 1.10.3 is rejected" not in combined_text
    assert "salmon 1.10.3はrejected" not in combined_text


def test_release_link_and_user_value_statements_are_bilingual() -> None:
    english_install = (SITE / "installation/index.html").read_text(encoding="utf-8")
    japanese_install = (SITE / "ja/installation/index.html").read_text(encoding="utf-8")
    assert RELEASE_URL in english_install and RELEASE_URL in japanese_install
    stale = (
        "A release-download button is intentionally absent until a release exists",
        "releaseが存在するまではrelease download buttonを表示しません",
    )
    assert not any(value in english_install + japanese_install for value in stale)
    assert "For laboratories that already operate a compatible NVIDIA GPU workstation" in parse("index.html").text
    assert "すでに適合するNVIDIA GPU環境を運用している研究室では" in parse("ja/index.html").text


def test_titles_and_descriptions_are_nonempty_and_language_appropriate() -> None:
    for relative in ENGLISH_PAGES:
        page = parse(relative)
        assert page.title.strip() and page.description.strip()
    for relative in JAPANESE_PAGES:
        page = parse(relative)
        assert page.title.strip() and page.description.strip()
        assert re.search(r"[ぁ-んァ-ヶ一-龠]", page.title)
        assert re.search(r"[ぁ-んァ-ヶ一-龠]", page.description)


def test_critical_benchmark_values_and_claim_limits_remain_visible() -> None:
    english = parse("benchmarks/index.html").text
    japanese = parse("ja/benchmarks/index.html").text
    for value in (
        "36,349,964",
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
        assert value in english and value in japanese
    assert "No general speedup ratio is claimed" in english
    assert "生物学的な正解" in japanese
    assert "CPU版に対する速度向上" in combined(JAPANESE_PAGES)


def test_copy_introduces_no_private_path_or_unsupported_speedup_claim() -> None:
    rendered = "\n".join(
        (SITE / path).read_text(encoding="utf-8")
        for path in (*ENGLISH_PAGES, *JAPANESE_PAGES, "assets/ai-consult.js")
    )
    assert "/home/do/" not in rendered
    assert "C:\\Users\\do" not in rendered
    assert "\\\\do-OMEN" not in rendered
    lowered = rendered.casefold()
    assert "fully gpu accelerated" not in lowered
    assert not re.search(r"\d+(?:\.\d+)?\s*[x×]\s*(?:cpu|faster)", lowered)
