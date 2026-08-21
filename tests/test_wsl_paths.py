from __future__ import annotations

import pytest

from harako_gpu.adapters.wsl import unc_path_to_linux


def test_wsl_unc_path_is_converted_without_shell() -> None:
    assert unc_path_to_linux(
        r"\\wsl.localhost\Ubuntu\home\researcher\harako-gpu-runtime\work",
        distribution="Ubuntu",
    ) == "/home/researcher/harako-gpu-runtime/work"


def test_wsl_unc_path_rejects_wrong_distribution_and_windows_drive() -> None:
    with pytest.raises(ValueError, match="expected Ubuntu"):
        unc_path_to_linux(r"\\wsl$\Debian\home\researcher", distribution="Ubuntu")
    with pytest.raises(ValueError, match="requires"):
        unc_path_to_linux(r"D:\runtime", distribution="Ubuntu")
