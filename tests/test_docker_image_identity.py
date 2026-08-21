from __future__ import annotations

import json

import pytest

from harako_gpu.adapters.docker import canonical_image_identity
from harako_gpu.adapters.process import CommandResult
from harako_gpu.services.run_preparation import (
    EXPECTED_IMAGES,
    IMAGE_CONTRACTS,
    _inspect_images,
)


class InspectRunner:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv, **_kwargs) -> CommandResult:
        command = tuple(argv)
        self.calls.append(command)
        return CommandResult(command, 0, json.dumps([self.payload]), "")


def _fastp_payload(repo_digests: list[str]) -> dict[str, object]:
    return {
        "Id": "sha256:" + "f" * 64,
        "RepoTags": ["community.wave.seqera.io/library/fastp:1.0.1--c8b87fe62dcc103c"],
        "RepoDigests": repo_digests,
        "Architecture": "amd64",
        "Os": "linux",
    }


def test_fastp_image_id_mismatch_with_exact_repo_digest_passes() -> None:
    expected = EXPECTED_IMAGES["fastp"]
    runner = InspectRunner(_fastp_payload([
        f"community.wave.seqera.io/library/fastp@{expected}",
    ]))

    observed = _inspect_images(runner, (), ("fastp",))

    assert observed == {"fastp": expected}


@pytest.mark.parametrize("repo_digests", (
    ["community.wave.seqera.io/library/fastp@sha256:" + "0" * 64],
    [],
))
def test_fastp_registry_digest_contract_rejects_mismatch_or_absence(
    repo_digests: list[str],
) -> None:
    with pytest.raises(ValueError, match="identity"):
        _inspect_images(InspectRunner(_fastp_payload(repo_digests)), (), ("fastp",))


def test_salmon_1_10_3_exact_repo_digest_passes() -> None:
    contract = IMAGE_CONTRACTS["salmon_1_10_3_compatibility"]
    payload = {
        "Id": "sha256:" + "a" * 64,
        "RepoDigests": [f"quay.io/biocontainers/salmon@{contract.identity}"],
    }
    assert canonical_image_identity(contract, payload) == contract.identity


def test_salmon_1_10_3_matching_id_without_repo_digest_fails() -> None:
    contract = IMAGE_CONTRACTS["salmon_1_10_3_compatibility"]
    with pytest.raises(ValueError, match="repository digest"):
        canonical_image_identity(contract, {"Id": contract.identity, "RepoDigests": []})


def test_salmon_2_5_1_exact_local_image_id_passes() -> None:
    contract = IMAGE_CONTRACTS["salmon_2_5_1_deterministic"]
    assert canonical_image_identity(contract, {"Id": contract.identity}) == contract.identity


def test_salmon_2_5_1_repo_digest_only_match_fails() -> None:
    contract = IMAGE_CONTRACTS["salmon_2_5_1_deterministic"]
    with pytest.raises(ValueError, match="image ID"):
        canonical_image_identity(contract, {
            "Id": "sha256:" + "0" * 64,
            "RepoDigests": [f"harako-gpu/salmon@{contract.identity}"],
        })


def test_registry_digest_on_unrelated_repository_fails() -> None:
    contract = IMAGE_CONTRACTS["fastp"]
    with pytest.raises(ValueError, match="repository digest"):
        canonical_image_identity(contract, {
            "Id": "sha256:" + "f" * 64,
            "RepoDigests": [f"mirror.invalid/library/fastp@{contract.identity}"],
        })


class MissingRunner:
    def run(self, argv, **_kwargs) -> CommandResult:
        return CommandResult(tuple(argv), 1, "", "No such image")


def test_missing_required_image_fails_closed() -> None:
    with pytest.raises(ValueError, match="unavailable"):
        _inspect_images(MissingRunner(), (), ("fastp",))


@pytest.mark.parametrize("prefix", (
    (),
    ("wsl.exe", "--distribution", "Ubuntu", "--exec"),
))
def test_native_and_wsl_inspect_prefixes_remain_structured(prefix: tuple[str, ...]) -> None:
    contract = IMAGE_CONTRACTS["fastp"]
    runner = InspectRunner(_fastp_payload([
        f"community.wave.seqera.io/library/fastp@{contract.identity}",
    ]))
    assert _inspect_images(runner, prefix, ("fastp",)) == {"fastp": contract.identity}
    assert runner.calls == [(*prefix, "docker", "image", "inspect", contract.execution_reference)]
    assert all("pull" not in call for call in runner.calls)


def test_execution_references_follow_the_identity_kind() -> None:
    fastp = IMAGE_CONTRACTS["fastp"]
    salmon_1103 = IMAGE_CONTRACTS["salmon_1_10_3_compatibility"]
    salmon_251 = IMAGE_CONTRACTS["salmon_2_5_1_deterministic"]
    assert fastp.execution_reference == f"{fastp.repository}@{fastp.identity}"
    assert salmon_1103.execution_reference == f"{salmon_1103.repository}@{salmon_1103.identity}"
    assert salmon_251.execution_reference == salmon_251.identity
    assert f"{salmon_251.reference}@{salmon_251.identity}" != salmon_251.execution_reference


def test_fixed_contract_values_are_not_derived_from_inspect_metadata() -> None:
    assert IMAGE_CONTRACTS["fastp"].identity == (
        "sha256:d228dace961ab50d04471e02e7fd2c8f2b8cd5b1b37be2d4039e2db64fcfae45"
    )
    assert IMAGE_CONTRACTS["salmon_1_10_3_compatibility"].identity == (
        "sha256:f83ebb158845ee8138d793347f83b92c75e83c58dd8f4600c6fea2a2453ef08e"
    )
    assert IMAGE_CONTRACTS["salmon_2_5_1_deterministic"].identity == (
        "sha256:e6e64f39a479458ef6f007757498321ee5a3ef8a2227ff2af414fbe3c36e6f7f"
    )
    assert IMAGE_CONTRACTS["parabricks"].identity_kind == "image_id"
