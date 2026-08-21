from __future__ import annotations

import pytest

from harako_gpu.services.matrices import build_profile_matrices


QUANT = "Name\tLength\tEffectiveLength\tTPM\tNumReads\nA\t100\t80\t10\t5\nB\t200\t150\t0\t0\n"


def test_profile_matrix_generation_is_namespaced_and_ordered(tmp_path) -> None:
    profile = "salmon_2_5_1_deterministic"
    for sample in ("S1", "S2"):
        root = tmp_path / "results/quantification" / profile / sample; root.mkdir(parents=True)
        (root / "quant.sf").write_text(QUANT)
        (root / "quant.genes.sf").write_text(QUANT)
    manifest = build_profile_matrices(run_dir=tmp_path, profile_id=profile, samples=("S1", "S2"))
    assert manifest["samples"] == ["S1", "S2"]
    assert (tmp_path / f"results/matrices/{profile}.gene_tpm.tsv").is_file()
    with pytest.raises(ValueError, match="Unique"):
        build_profile_matrices(run_dir=tmp_path, profile_id=profile, samples=("S1", "S1"))
