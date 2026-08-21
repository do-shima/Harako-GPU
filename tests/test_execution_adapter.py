from __future__ import annotations

import json

import pytest

from harako_gpu.adapters.execution import CommandSpec, write_command_spec, wsl_exec_argv
from harako_gpu.adapters.wsl import linux_path_to_unc, unc_path_to_linux


def test_command_spec_is_structured_allowlisted_and_hashed(tmp_path) -> None:
    spec = CommandSpec(("nextflow", "run", "/pipeline"), "/runtime/run", {
        "NXF_VER": "25.04.3", "NXF_ANSI_LOG": "false",
    }, "/runtime/run/linux.pid")
    assert len(spec.argv_sha256) == 64 and len(spec.env_sha256) == 64
    path = tmp_path / "command.json"
    write_command_spec(path, spec)
    assert json.loads(path.read_text())["argv"] == ["nextflow", "run", "/pipeline"]
    with pytest.raises(ValueError, match="already exists"):
        write_command_spec(path, spec)
    with pytest.raises(ValueError, match="Shell"):
        CommandSpec(("bash", "-c", "x"), "/x", {}, "/x/pid").validate()
    with pytest.raises(ValueError, match="allowlisted"):
        CommandSpec(("nextflow",), "/x", {"SECRET": "x"}, "/x/pid").validate()


def test_offline_nextflow_environment_is_an_explicit_safe_key() -> None:
    spec = CommandSpec(
        ("/home/researcher/.local/bin/nextflow", "run", "/runtime/pipeline"),
        "/runtime/run", {
            "NXF_VER": "25.04.3", "NXF_OFFLINE": "true",
            "NXF_PLUGINS_DIR": "/home/user/.nextflow/plugins",
        }, "/runtime/run/pid",
    )
    spec.validate()


def test_wsl_argv_and_path_mapping_never_use_shell() -> None:
    argv = wsl_exec_argv(distribution="Ubuntu", runner_path="/runtime/runner.py", spec_path="/runtime/spec.json")
    assert argv == ("wsl.exe", "--distribution", "Ubuntu", "--exec", "python3", "/runtime/runner.py", "/runtime/spec.json")
    assert not any(value in {"sh", "bash", "-c"} for value in argv)
    unc = linux_path_to_unc("/home/u/runtime", distribution="Ubuntu")
    assert unc_path_to_linux(unc, distribution="Ubuntu") == "/home/u/runtime"
