"""Profile-qualified Salmon matrix generation after all sample outputs validate."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from harako_gpu.adapters.filesystem import sha256_path, write_new_text
from harako_gpu.services.concordance import QuantRow, parse_quant_sf
from harako_gpu.services.quantification_profiles import artifact_names, get_profile


FIELDS = {
    "transcript_counts": "num_reads", "transcript_tpm": "tpm",
    "transcript_effective_length": "effective_length",
    "gene_counts": "num_reads", "gene_tpm": "tpm", "gene_effective_length": "effective_length",
}


def _matrix(rows: dict[str, tuple[QuantRow, ...]], field: str) -> str:
    samples = tuple(rows)
    order = tuple(item.feature_id for item in rows[samples[0]])
    if any(tuple(item.feature_id for item in rows[sample]) != order for sample in samples):
        raise ValueError("Profile matrix feature order differs across samples")
    lines = ["\t".join(("feature_id", *samples))]
    for position, feature in enumerate(order):
        lines.append("\t".join((feature, *(str(getattr(rows[sample][position], field)) for sample in samples))))
    return "\n".join(lines) + "\n"


def build_profile_matrices(*, run_dir: Path, profile_id: str, samples: tuple[str, ...]) -> dict[str, object]:
    get_profile(profile_id)
    if not samples or len(set(samples)) != len(samples):
        raise ValueError("Unique ordered samples are required")
    names = artifact_names(profile_id)
    transcripts, genes = {}, {}
    quant_hashes = {}
    for sample in samples:
        root = run_dir / "results/quantification" / profile_id / sample
        quant, gene = root / "quant.sf", root / "quant.genes.sf"
        if not quant.is_file() or not gene.is_file():
            raise ValueError(f"Validated Salmon outputs are missing for {profile_id}/{sample}")
        transcripts[sample] = parse_quant_sf(quant.read_text(encoding="utf-8"))
        genes[sample] = parse_quant_sf(gene.read_text(encoding="utf-8"))
        quant_hashes[sample] = {"quant_sf": sha256_path(quant), "quant_genes_sf": sha256_path(gene)}
    destination = run_dir / "results/matrices"
    destination.mkdir(parents=True, exist_ok=True)
    outputs = {}
    for role, field in FIELDS.items():
        rows = transcripts if role.startswith("transcript_") else genes
        path = run_dir / "results" / names[role]
        write_new_text(path, _matrix(rows, field))
        outputs[role] = {"path": path.relative_to(run_dir).as_posix(), "sha256": sha256_path(path)}
    manifest = {
        "schema_version": 1, "profile_id": profile_id, "samples": list(samples),
        "sample_order_exact": True, "feature_order_exact": True,
        "quant_outputs": quant_hashes, "matrices": outputs,
    }
    write_new_text(destination / f"{profile_id}.manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest
