"""Project Linux runtime paths onto the current host filesystem."""

from __future__ import annotations

import platform
from pathlib import Path

from harako_gpu.adapters.filesystem import require_safe_linux_runtime_path
from harako_gpu.adapters.wsl import linux_path_to_unc


def host_path_from_linux(
    value: str,
    *,
    distribution: str = "Ubuntu",
    host_system: str | None = None,
) -> Path:
    """Return a host-visible path without broadening execution qualification.

    Linux processes, including processes running inside WSL, access the Linux
    path directly. A Windows host reaches the same WSL path through the
    existing UNC projection. Other host systems remain unsupported.
    """
    linux_path = require_safe_linux_runtime_path(value)
    system = platform.system() if host_system is None else host_system
    if system == "Linux":
        return Path(linux_path)
    if system == "Windows":
        return Path(linux_path_to_unc(linux_path, distribution=distribution))
    raise ValueError(f"Unsupported host system for Linux path projection: {system or '<empty>'}")
