from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
PREFIX = "https://do-shima.github.io/Harako-GPU/"
CPU_SITE = "https://do-shima.github.io/harako-rnaseq/"
PAIRS = {
    "": "ja/",
    "installation/": "ja/installation/",
    "methods/": "ja/methods/",
    "benchmarks/": "ja/benchmarks/",
    "outputs/": "ja/outputs/",
}
CONTENT = {f"{path}index.html" for pair in PAIRS.items() for path in pair}
HTML = CONTENT | {"404.html"}
CHARTS = {
    "assets/charts/gpu-alignment-observed.svg",
    "assets/charts/salmon-runtime.svg",
    "assets/charts/salmon-concordance.svg",
    "assets/charts/method-sensitive-features.svg",
}


class Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self.scripts: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self.lang = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "html":
            self.lang = values.get("lang", "")
        elif tag in {"a", "link"}:
            self.links.append({"tag": tag, **values})
        elif tag == "script":
            self.scripts.append(values)
        elif tag == "img":
            self.images.append(values)


def parse(relative: str) -> Parser:
    parser = Parser()
    parser.feed((SITE / relative).read_text(encoding="utf-8"))
    return parser


def public_url(relative: str) -> str:
    return PREFIX + (relative.removesuffix("index.html") if relative != "index.html" else "")


def local_target(source: Path, value: str) -> Path | None:
    split = urlsplit(value)
    if value.startswith(PREFIX):
        relative = unquote(value.removeprefix(PREFIX))
        target = SITE / relative
    elif split.scheme or split.netloc or value.startswith("#") or not split.path:
        return None
    else:
        target = (source.parent / unquote(split.path)).resolve()
    if value.endswith("/"):
        target /= "index.html"
    return target


def test_expected_bilingual_site_structure_exists() -> None:
    expected = {
        *HTML,
        *CHARTS,
        "assets/site.css",
        "assets/ai-consult.js",
        "assets/harako-logo.png",
        "assets/data/public-benchmark-summary.json",
        "assets/data/evidence-source-map.json",
        "robots.txt",
        "sitemap.xml",
        ".nojekyll",
    }
    assert not [path for path in sorted(expected) if not (SITE / path).is_file()]
    assert len(CONTENT) == 10


def test_internal_links_and_local_runtime_assets_resolve() -> None:
    broken: list[str] = []
    for relative in HTML:
        source = SITE / relative
        page = parse(relative)
        for entry in [*page.links, *page.scripts, *page.images]:
            value = entry.get("href") or entry.get("src") or ""
            target = local_target(source, value)
            if target is not None and not target.exists():
                broken.append(f"{relative} -> {value}")
        for script in page.scripts:
            assert not urlsplit(script.get("src", "")).scheme
        for link in (item for item in page.links if item.get("rel") == "stylesheet"):
            assert not urlsplit(link["href"]).scheme
    assert not broken, "\n".join(sorted(broken))
    css = (SITE / "assets/site.css").read_text(encoding="utf-8")
    assert "@import" not in css.lower()
    assert not re.search(r"url\(\s*['\"]?https?://", css, re.IGNORECASE)


def test_canonical_and_reciprocal_hreflang_are_exact() -> None:
    for english, japanese in PAIRS.items():
        expected = {
            "en": PREFIX + english,
            "ja": PREFIX + japanese,
            "x-default": PREFIX + english,
        }
        for relative in (f"{english}index.html", f"{japanese}index.html"):
            page = parse(relative)
            canonical = [link for link in page.links if link.get("rel") == "canonical"]
            assert canonical == [{"tag": "link", "rel": "canonical", "href": public_url(relative)}]
            alternates = {
                link["hreflang"]: link["href"]
                for link in page.links
                if link.get("rel") == "alternate"
            }
            assert alternates == expected


def test_sitemap_and_robots_cover_all_content_pages() -> None:
    tree = ElementTree.parse(SITE / "sitemap.xml")
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [node.text for node in tree.findall("sm:url/sm:loc", ns)]
    assert set(urls) == {public_url(relative) for relative in CONTENT}
    assert len(urls) == len(set(urls))
    robots = (SITE / "robots.txt").read_text(encoding="utf-8")
    assert "User-agent: *" in robots and "Allow: /" in robots
    assert f"Sitemap: {PREFIX}sitemap.xml" in robots


def test_cpu_relationship_and_required_navigation_are_public() -> None:
    for relative in HTML:
        text = (SITE / relative).read_text(encoding="utf-8")
        assert CPU_SITE in text
        assert "https://github.com/do-shima/Harako-GPU" in text
    english = (SITE / "index.html").read_text(encoding="utf-8")
    assert "Harako-GPU does not supersede Harako-RNAseq" in english
    assert "Harako-RNAseq (CPU)" in english
    assert "GPU-assisted BAM/junction/GeneCounts" in english


def test_accessible_svg_charts_have_adjacent_html_tables() -> None:
    for relative in CHARTS:
        root = ElementTree.parse(SITE / relative).getroot()
        assert root.attrib.get("role") == "img"
        assert "aria-labelledby" in root.attrib
        names = {node.tag.rsplit("}", 1)[-1] for node in root}
        assert {"title", "desc"}.issubset(names)
        text = " ".join("".join(root.itertext()).split())
        assert re.search(r"\d", text)
    for relative in ("benchmarks/index.html", "ja/benchmarks/index.html"):
        text = (SITE / relative).read_text(encoding="utf-8")
        assert text.count("<figure") == 4
        assert text.count("</figure><") == 4
        assert text.count("<table") == 4


def test_benchmark_json_matches_immutable_evidence() -> None:
    public = json.loads((SITE / "assets/data/public-benchmark-summary.json").read_text(encoding="utf-8"))
    salmon = json.loads((ROOT / "docs/qualification/salmon-1.10.3-vs-2.5.1-c1-comparison.json").read_text(encoding="utf-8"))
    one = json.loads((ROOT / "docs/qualification/native-high-memory-full-human-one-pass.json").read_text(encoding="utf-8"))
    two = json.loads((ROOT / "docs/qualification/native-high-memory-full-human-two-pass.json").read_text(encoding="utf-8"))
    assert public["salmon"]["median_wall_seconds"]["1.10.3"] == salmon["runtime"]["salmon_1_10_3_median_wall_seconds"]
    assert public["salmon"]["median_wall_seconds"]["2.5.1"] == salmon["runtime"]["salmon_2_5_1_median_wall_seconds"]
    assert public["salmon"]["median_wall_ratio_1_10_3_to_2_5_1"] == salmon["runtime"]["median_wall_time_ratio_1_10_3_to_2_5_1"]
    assert public["gpu_observed"]["one_pass"]["memory_contract_bytes"] == one["resource_contract"]["memory_bytes"]
    assert public["gpu_observed"]["two_pass"]["cgroup_peak_bytes"] == two["resource_contract"]["cgroup_memory_peak_bytes"]
    assert public["gpu_observed"]["two_pass"]["isolated_alignment_seconds"] == 850
    assert public["gpu_observed"]["one_pass"]["isolated_alignment_seconds"] is None
    assert public["salmon"]["method_sensitive_features"] == {
        "transcript_tpm": {"q1": 2882, "q2": 2883},
        "gene_tpm": {"q1": 733, "q2": 731},
        "transcript_num_reads": {"q1": 2929, "q2": 2925},
        "gene_num_reads": {"q1": 552, "q2": 554},
    }


def test_method_sensitive_feature_counts_are_discrete_q1_q2_values() -> None:
    paths = (
        SITE / "assets/charts/method-sensitive-features.svg",
        SITE / "assets/data/public-benchmark-summary.json",
        SITE / "benchmarks/index.html",
        SITE / "ja/benchmarks/index.html",
    )
    rendered = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "2882.5" not in rendered and "2,882.5" not in rendered
    for expected in ("2882", "2883", "733", "731", "2929", "2925", "552", "554"):
        assert expected in rendered.replace(",", "")


def test_source_map_is_redacted_and_sha_pinned() -> None:
    payload = json.loads((SITE / "assets/data/evidence-source-map.json").read_text(encoding="utf-8"))
    assert payload["private_paths_included"] is False
    assert len(payload["sources"]) == 8
    for source in payload["sources"]:
        assert re.fullmatch(r"[0-9a-f]{64}", source["sha256"])
        assert not re.search(r"(?i)(/home/|[A-Z]:\\|\\\\|do-OMEN)", source["path"])


def test_public_claim_boundaries_and_version_pinning_copy() -> None:
    public_text = "\n".join(
        (SITE / relative).read_text(encoding="utf-8") for relative in sorted(HTML)
    )
    lowered = public_text.lower()
    assert "fully gpu accelerated" not in lowered
    assert "open source" not in lowered and "open-source" not in lowered
    assert "cpu speedup chart" not in lowered
    assert not re.search(r"\d+(?:\.\d+)?\s*[x×]\s*(?:cpu|faster)", lowered)
    assert "salmon 1.10.3 is rejected" not in lowered
    assert "salmon 1.10.3はrejected" not in lowered
    assert "no general speedup ratio is claimed" in lowered
    japanese = (SITE / "ja/methods/index.html").read_text(encoding="utf-8")
    assert "Salmonのversionを固定しなければ、software versionに依存する数値差やmethod-dependent variationが、実験条件による差に混入する可能性があります。" in japanese
    assert "ここでいう差は、単純な丸め誤差だけではなく、version、implementation、index、execution behaviorに依存する差を含みます。" in japanese


def test_site_contains_no_private_path_or_biological_binary() -> None:
    private_linux = "/home/" + "do/"
    private_windows = "C:\\Users\\" + "do"
    private_unc = "\\\\" + "do-OMEN"
    prohibited = re.compile(
        "|".join(re.escape(value) for value in (private_linux, private_windows, private_unc)),
        re.IGNORECASE,
    )
    for path in SITE.rglob("*"):
        if not path.is_file():
            continue
        assert path.suffix.lower() not in {".fastq", ".bam", ".bai", ".tar", ".gz"}
        if path.suffix.lower() in {".html", ".js", ".css", ".json", ".svg", ".txt", ".xml"}:
            assert not prohibited.search(path.read_text(encoding="utf-8")), path
