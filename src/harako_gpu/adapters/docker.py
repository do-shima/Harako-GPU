"""Docker CLI inspection without image pulls or container execution."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal, Mapping

from .process import CommandResult, ProcessRunner


PARABRICKS_IMAGE = "nvcr.io/nvidia/clara/clara-parabricks:4.6.0-1"
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class DockerImageContract:
    """One fixed registry-digest or local-image-ID contract."""

    reference: str
    identity: str
    identity_kind: Literal["repo_digest", "image_id"]

    def validate(self) -> None:
        if not self.reference or not _DIGEST.fullmatch(self.identity):
            raise ValueError("Docker image reference and sha256 identity must be fixed")
        if self.identity_kind not in {"repo_digest", "image_id"}:
            raise ValueError("Unsupported Docker image identity kind")

    @property
    def repository(self) -> str:
        self.validate()
        reference = self.reference.split("@", 1)[0]
        slash = reference.rfind("/")
        colon = reference.rfind(":")
        return reference[:colon] if colon > slash else reference

    @property
    def execution_reference(self) -> str:
        self.validate()
        if self.identity_kind == "repo_digest":
            return f"{self.repository}@{self.identity}"
        return self.identity

    def as_dict(self) -> dict[str, str]:
        self.validate()
        return {
            "reference": self.reference,
            "identity": self.identity,
            "identity_kind": self.identity_kind,
            "execution_reference": self.execution_reference,
        }


def canonical_image_identity(
    contract: DockerImageContract,
    inspected: Mapping[str, Any],
) -> str:
    """Validate one Docker inspect object and return its canonical identity."""
    contract.validate()
    if contract.identity_kind == "image_id":
        if inspected.get("Id") != contract.identity:
            raise ValueError("Docker image ID identity mismatch")
        return contract.identity
    repo_digests = inspected.get("RepoDigests")
    expected = f"{contract.repository}@{contract.identity}"
    if not isinstance(repo_digests, list) or expected not in repo_digests:
        raise ValueError("Docker repository digest identity mismatch")
    return contract.identity


def inspect_image_contract(
    runner: ProcessRunner,
    contract: DockerImageContract,
    *,
    prefix: tuple[str, ...] = (),
    timeout: float = 15,
) -> str:
    """Inspect one fixed image exactly once without pulling or retagging it."""
    inspection_reference = (
        contract.execution_reference
        if contract.identity_kind == "repo_digest"
        else contract.reference
    )
    result = runner.run(
        (*prefix, "docker", "image", "inspect", inspection_reference),
        timeout=timeout,
    )
    if not result.ok:
        raise ValueError(f"Required local image unavailable: {contract.reference}")
    try:
        payload = json.loads(result.stdout)
        if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
            raise ValueError("Docker image inspect must return one object")
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Docker image inspect returned malformed JSON") from exc
    return canonical_image_identity(contract, payload[0])


def daemon_info(runner: ProcessRunner) -> CommandResult:
    return runner.run(["docker", "info", "--format", "{{json .}}"], timeout=10)


def inspect_image(runner: ProcessRunner, image: str) -> CommandResult:
    return runner.run(["docker", "image", "inspect", image, "--format", "{{.Id}}"], timeout=8)


def local_images(runner: ProcessRunner) -> CommandResult:
    return runner.run(["docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}"], timeout=8)
