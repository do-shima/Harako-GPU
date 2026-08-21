"""Correct the tautological v1 orientation ratio before primary quantification."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True)
    args = parser.parse_args()
    runtime = Path(args.runtime_root).resolve()
    source = runtime / "capacity/library-type-probe/library-type-selection.json"
    output = runtime / "capacity/library-type-probe-v2"
    if output.exists():
        raise SystemExit("Library-type probe amendment already exists; refusing overwrite")
    original = json.loads(source.read_text(encoding="utf-8"))
    counts = {str(row["candidate"]): int(row["num_compatible_fragments"]) for row in original["candidates"]}
    # IU accepts either orientation and defines the shared orientation-compatible universe.
    counts["IU"] = next(int(row["num_assigned_fragments"]) for row in original["candidates"] if row["candidate"] == "IU")
    denominator = counts["IU"]
    proportions = {key: value / denominator for key, value in counts.items()}
    ranked = sorted(proportions, key=lambda key: (-proportions[key], key))
    margin = proportions[ranked[0]] - proportions[ranked[1]]
    passed = proportions[ranked[0]] >= 0.8 and margin >= 0.2
    selected = {
        "proportions": proportions, "selected_salmon_libtype": ranked[0] if passed else None,
        "selected_product_library_type": "U" if passed and ranked[0] == "IU" else ranked[0] if passed else None,
        "margin": margin, "status": "PASS" if passed else "UNKNOWN_LIBRARY_TYPE",
        "denominator": "IU num_assigned_fragments (unstranded shared orientation universe)",
    }
    output.mkdir()
    result = {
        "schema_version": 2, "parent_probe_sha256": digest(source),
        "amended_before_primary_quantification": True,
        "amendment_reason": "v1 divided each explicit candidate by its own assigned fragments, making every ratio tautologically 1.0",
        "thresholds_unchanged": True, "minimum_consistency": 0.8, "minimum_margin": 0.2,
        "selection_inputs": "orientation-compatible fragment counts only", "abundance_mapping_rate_or_truth_used": False,
        "counts": counts, **selected,
        "amended_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path = output / "library-type-selection-v2.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "library-type-selection-v2.sha256").write_text(digest(path) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2, sort_keys=True))
    if selected["status"] != "PASS":
        raise SystemExit("Corrected orientation probe remains ambiguous")


if __name__ == "__main__":
    main()
