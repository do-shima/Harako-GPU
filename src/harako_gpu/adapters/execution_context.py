"""Fail-closed identity and host projection for fixed execution transports."""

from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path

from harako_gpu.adapters.host_paths import host_path_from_linux


NATIVE_LINUX = "native_linux"
WSL2_PREFIX = "wsl2:"


@dataclass(frozen=True)
class ExecutionContext:
    """One immutable Harako-GPU execution transport identity."""

    identity: str
    distribution: str | None

    @property
    def is_native_linux(self) -> bool:
        return self.identity == NATIVE_LINUX

    @property
    def is_wsl2(self) -> bool:
        return self.identity.startswith(WSL2_PREFIX)

    def host_path(self, value: str) -> Path:
        if self.is_native_linux:
            require_native_linux_host()
            return host_path_from_linux(value, host_system="Linux")
        if self.distribution is None:
            raise ValueError("WSL2 execution requires a distribution")
        return host_path_from_linux(value, distribution=self.distribution, host_system="Windows")


def _valid_distribution(value: str | None, message: str) -> str:
    if value is None or not value.strip() or any(ord(char) < 32 for char in value):
        raise ValueError(message)
    return value.strip()


def parse_execution_context(value: str, *, distribution: str | None = None) -> ExecutionContext:
    """Parse a CLI or frozen context without silently selecting another transport."""
    normalized = value.strip().casefold().replace("_", "-")
    if normalized == "native-linux":
        return ExecutionContext(NATIVE_LINUX, None)
    if normalized == "wsl2":
        selected = _valid_distribution(distribution, "WSL2 execution requires a valid distribution")
        return ExecutionContext(f"{WSL2_PREFIX}{selected}", selected)
    if value.startswith(WSL2_PREFIX):
        selected = _valid_distribution(value[len(WSL2_PREFIX):], "Frozen WSL2 execution context is invalid")
        if distribution is not None and distribution != selected:
            raise ValueError("CLI distribution does not match frozen execution context")
        return ExecutionContext(value, selected)
    raise ValueError(f"Unsupported execution context: {value}")


def require_context_match(*, requested: str, frozen: str,
                          distribution: str | None = None) -> ExecutionContext:
    requested_context = parse_execution_context(requested, distribution=distribution)
    frozen_context = parse_execution_context(frozen)
    if requested_context.identity != frozen_context.identity:
        raise ValueError(
            f"Requested execution context {requested_context.identity} does not match frozen {frozen_context.identity}"
        )
    return frozen_context


def require_native_linux_host(*, host_system: str | None = None,
                              kernel_release: str | None = None) -> None:
    """Reject Windows, WSL Linux, and unsupported hosts for native qualification."""
    system = host_system or platform.system()
    release = kernel_release if kernel_release is not None else platform.release()
    if system != "Linux":
        raise ValueError(f"Native Linux execution is unavailable on host system: {system}")
    if "microsoft" in release.casefold():
        raise ValueError("WSL Linux cannot be qualified as native Linux")
