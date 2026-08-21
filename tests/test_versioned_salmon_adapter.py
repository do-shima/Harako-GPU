from __future__ import annotations

from pathlib import Path

import pytest

from harako_gpu.adapters.versioned_salmon import VersionedSalmonRequest, docker_argv, execution_metadata
from harako_gpu.services.quantification_profiles import (
    ProcessedFastqPair, ProfileIndex, SALMON_251_ID, get_profile,
)


SHA = "a" * 64


def test_adapter_uses_read_only_inputs_writable_output_and_exact_image(tmp_path: Path) -> None:
    index = tmp_path / "index"; index.mkdir()
    r1, r2, gtf = tmp_path / "r1.fq", tmp_path / "r2.fq", tmp_path / "tx.gtf"
    for path in (r1, r2, gtf): path.write_text("x", encoding="utf-8")
    output_parent = tmp_path / "out"; output_parent.mkdir()
    profile = get_profile(SALMON_251_ID)
    request = VersionedSalmonRequest(SALMON_251_ID,
        ProcessedFastqPair("S", str(r1), str(r2), SHA, SHA, 1, "fastp-v1", "1", ("fastp",), "ISR"),
        ProfileIndex(SALMON_251_ID, "i", str(index), profile.version, profile.image_identity, SHA, SHA, SHA, SHA, SHA),
        gtf, output_parent / "sample")
    argv = docker_argv(request)
    assert profile.image_identity in argv
    assert profile.image_reference not in argv
    mounts = [argv[i + 1] for i, value in enumerate(argv) if value == "--mount"]
    assert all("readonly" in mount for mount in mounts[:-1])
    assert "readonly" not in mounts[-1]
    assert argv.count("--deterministic") == 1 and "--decoder" in argv
    assert not any(value in {"eval", "sh", "bash"} for value in argv)
    metadata = execution_metadata(request, argv)
    assert metadata["index_id"] == "i" and metadata["processed_fastq"]["paired_fragments"] == 1


def test_adapter_rejects_profile_index_mismatch(tmp_path: Path) -> None:
    pair = ProcessedFastqPair("S", "r1", "r2", SHA, SHA, 1, "f", "1", ("fastp",), "ISR")
    profile = get_profile(SALMON_251_ID)
    idx = ProfileIndex(SALMON_251_ID, "i", "index", profile.version, profile.image_identity, SHA, SHA, SHA, SHA, SHA)
    request = VersionedSalmonRequest("salmon_1_10_3_compatibility", pair, idx, tmp_path / "missing", tmp_path / "out")
    with pytest.raises(ValueError, match="mismatch"):
        request.validate()
