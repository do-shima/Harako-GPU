from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.0a1"
DISPLAY_VERSION = "v0.1.0-alpha.1"


def test_package_public_display_and_cli_versions_are_consistent() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == VERSION
    assert "internal prototype" not in project["description"].lower()
    assert 'VERSION = "0.1.0a1"' in (ROOT / "src/harako_gpu/version.py").read_text(encoding="utf-8")
    for relative in ("README.md", "PUBLIC_ALPHA.md", "docs/release/v0.1.0-alpha.1.md", "site/index.html", "site/ja/index.html"):
        assert DISPLAY_VERSION in (ROOT / relative).read_text(encoding="utf-8")


def test_license_and_legal_files_are_release_ready() -> None:
    required = {
        "LICENSE", "COMMERCIAL_LICENSE.md", "THIRD_PARTY_NOTICES.md", "CITATION.cff",
        "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md",
    }
    assert not [path for path in sorted(required) if not (ROOT / path).is_file()]
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "PolyForm Noncommercial License 1.0.0" in license_text
    assert "https://polyformproject.org/licenses/noncommercial/1.0.0" in license_text
    assert "Required Notice: Copyright 2026 Daisuke Ohshima" in license_text
    notices = " ".join((ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8").split())
    assert "does not redistribute NVIDIA Parabricks" in notices
    assert "official NVIDIA NGC" in notices
    assert "does not accept those terms" in notices
    assert "Nothing in the Harako-GPU license grants rights to those assets" in notices


def test_public_alpha_scope_contains_required_boundaries() -> None:
    text = " ".join((ROOT / "PUBLIC_ALPHA.md").read_text(encoding="utf-8").split())
    required = (
        "ubuntu_native_rtx3090_ram128_v1", "harako_native_v1", "42.GB",
        "96.GB", "human_grch38p14_gencode49_harako_gpu_v1", "research use only",
        "diagnostic or clinical use", "actual Ubuntu browser runtime was unavailable",
        "does not bundle or redistribute Parabricks", "CPU STAR", "Cross-host BAM equality",
    )
    assert not [marker for marker in required if marker.casefold() not in text.casefold()]


def test_pages_workflow_is_pinned_scoped_and_dormant_until_publication() -> None:
    text = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
    uses = re.findall(r"uses:\s*([^@\s]+)@([0-9a-f]{40})", text)
    assert {name for name, _ in uses} == {
        "actions/checkout", "actions/configure-pages", "actions/upload-pages-artifact", "actions/deploy-pages",
    }
    assert "branches:\n      - main" in text
    assert '- "site/**"' in text and "workflow_dispatch:" in text
    assert "path: site/" in text
    assert "secrets." not in text and "pull_request_target" not in text


def test_no_release_artifacts_or_third_party_scientific_binaries_are_tracked() -> None:
    prohibited_suffixes = {".whl", ".tar", ".fastq", ".bam", ".bai", ".sif"}
    allowed_png = ROOT / "site/assets/harako-logo.png"
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or ".venv" in path.parts:
            continue
        if path == allowed_png:
            continue
        assert path.suffix.lower() not in prohibited_suffixes, path
    assert not (ROOT / "dist/SHA256SUMS").exists()


def test_private_publication_history_audit_is_excluded_from_snapshot() -> None:
    assert not (ROOT / "reports/publication-history-audit.json").exists()
    assert not (ROOT / "scripts/audit_publication_history.py").exists()


def test_readme_uses_public_alpha_language_without_overclaiming() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    headings = re.findall(r"^## (.+)$", text, re.MULTILINE)
    assert headings[:15] == [
        "Public alpha warning", "Current supported environment", "Harako-native workflow",
        "CPU Harako-RNAseq vs Harako-GPU", "Installation overview", "Quick start",
        "Reproducibility and version pinning", "Salmon profiles", "Outputs", "Limitations",
        "Licensing and third-party terms", "Citation", "Development and tests",
        "Detailed qualification links",
    ][:len(headings[:15])]
    lowered = text.lower()
    assert "gpu-assisted" in lowered
    assert "fully gpu accelerated" not in lowered
    assert "open source" not in lowered
    assert "matched cpu/gpu speedup ratio is claimed" in lowered
