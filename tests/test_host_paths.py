from __future__ import annotations

from pathlib import Path

import pytest

from harako_gpu.adapters.host_paths import host_path_from_linux


def test_native_linux_projection_preserves_absolute_path() -> None:
    projected = host_path_from_linux("/tmp/example", host_system="Linux")

    assert projected == Path("/tmp/example")
    assert "wsl.localhost" not in str(projected)


def test_windows_projection_reuses_wsl_unc_contract() -> None:
    projected = host_path_from_linux(
        "/home/researcher/example",
        distribution="Ubuntu",
        host_system="Windows",
    )

    assert str(projected) == r"\\wsl.localhost\Ubuntu\home\researcher\example"


@pytest.mark.parametrize(
    "value",
    (
        "relative/path",
        "/home/researcher/../escape",
        "/mnt/c/data",
        "/mnt/d/data",
        "/home/researcher/control\ncharacter",
    ),
)
def test_unsafe_linux_paths_are_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        host_path_from_linux(value, host_system="Linux")


def test_unsupported_host_fails_closed() -> None:
    with pytest.raises(ValueError, match="Unsupported host system"):
        host_path_from_linux("/tmp/example", host_system="Darwin")
