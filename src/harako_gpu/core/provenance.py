"""Versioned response and plan identity contracts."""

from __future__ import annotations

from typing import Any, Mapping

from .canonical import sha256_payload
from harako_gpu.version import VERSION


PROVENANCE_SCHEMA_VERSION = 1


def response(payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Port of the Harako response envelope, renamed for this namespace."""
    return {"schema_version": PROVENANCE_SCHEMA_VERSION, "harako_version": VERSION, **dict(payload or {})}


def plan_id_for(execution_payload: Mapping[str, Any]) -> str:
    return sha256_payload({"kind": "harako-agent-plan", "payload": dict(execution_payload)})


def approval_hash_for(execution_payload: Mapping[str, Any]) -> str:
    return sha256_payload({"kind": "harako-agent-approval", "payload": dict(execution_payload)})
