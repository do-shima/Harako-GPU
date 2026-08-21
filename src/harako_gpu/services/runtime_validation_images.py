"""Frozen image contracts for post-workflow scientific validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from harako_gpu.adapters.bio_validation import LEGACY_WSL_UTILITY_SAMTOOLS_CONTRACT
from harako_gpu.adapters.docker import DockerImageContract
from harako_gpu.services.host_profiles import (
    TASK_IMAGE_CLOSURE_EVIDENCE_SHA256,
    TASK_IMAGE_CLOSURE_ID,
    UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
    task_image_contract_for_role,
)


@dataclass(frozen=True)
class FrozenValidationImage:
    contract: DockerImageContract
    resolution_source: str


def bam_validator_freeze_payload(host_profile_id: str) -> dict[str, Any]:
    if host_profile_id == UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID:
        contract = task_image_contract_for_role(host_profile_id, "SAMTOOLS")
        if contract is None:
            raise ValueError("Ubuntu task-image closure has no SAMTOOLS contract")
        source = {
            "closure_id": TASK_IMAGE_CLOSURE_ID,
            "closure_sha256": TASK_IMAGE_CLOSURE_EVIDENCE_SHA256,
        }
    else:
        contract = LEGACY_WSL_UTILITY_SAMTOOLS_CONTRACT
        source = {"closure_id": "legacy-wsl-utility-images-v1", "closure_sha256": None}
    return {
        "schema_version": 1,
        "host_profile_id": host_profile_id,
        "source_closure": source,
        "bam_validator": {"process_role": "SAMTOOLS", **contract.as_dict()},
    }


def _contract_from_entry(entry: Mapping[str, Any]) -> DockerImageContract:
    try:
        contract = DockerImageContract(
            str(entry["reference"]),
            str(entry["identity"]),
            str(entry["identity_kind"]),  # type: ignore[arg-type]
        )
    except KeyError as exc:
        raise ValueError("Frozen BAM validator image contract is incomplete") from exc
    contract.validate()
    if entry.get("execution_reference") != contract.execution_reference:
        raise ValueError("Frozen BAM validator execution reference mismatch")
    return contract


def resolve_frozen_bam_validator_contract(run_dir: Path) -> FrozenValidationImage:
    root = run_dir.resolve()
    plan = json.loads((root / "frozen/plan.json").read_text(encoding="utf-8"))
    host_profile_id = str(
        dict(dict(plan.get("capability_snapshot") or {}).get("result") or {}).get(
            "host_profile_id"
        )
        or "windows_wsl2_rtx3090_ram64_v1"
    )
    path = root / "frozen/runtime-validation-images.json"
    if not path.is_file():
        if host_profile_id == UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID:
            raise ValueError(
                "Retained Ubuntu run lacks a frozen SAMTOOLS closure contract; prepare a new immutable run"
            )
        return FrozenValidationImage(
            LEGACY_WSL_UTILITY_SAMTOOLS_CONTRACT,
            "legacy_wsl_utility_contract",
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("host_profile_id") != host_profile_id:
        raise ValueError("Frozen runtime-validation image identity mismatch")
    entry = dict(payload.get("bam_validator") or {})
    if entry.get("process_role") != "SAMTOOLS":
        raise ValueError("Frozen BAM validator process role mismatch")
    contract = _contract_from_entry(entry)
    expected = bam_validator_freeze_payload(host_profile_id)
    if payload != expected:
        raise ValueError("Frozen BAM validator contract differs from the qualified catalog")
    return FrozenValidationImage(contract, "dedicated_frozen_runtime_validation_images")
