from __future__ import annotations

import json
import platform
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harako_gpu.adapters.bio_validation import (
    LEGACY_WSL_UTILITY_SAMTOOLS_IMAGE_ID,
    validate_bam,
)
from harako_gpu.adapters.docker import DockerImageContract
from harako_gpu.adapters.execution import CommandSpec, run_native_streaming
from harako_gpu.adapters.execution_context import (
    ExecutionContext, NATIVE_LINUX, parse_execution_context, require_context_match, require_native_linux_host,
)
from harako_gpu.adapters.filesystem import ensure_within
from harako_gpu.adapters.process import CommandResult
from harako_gpu.adapters.resources import ResourceMonitor
from harako_gpu.services.run_preparation import (
    EXPECTED_IMAGES, IMAGE_CONTRACTS, PreparationContext, _copy_pipeline, _freeze_pipeline,
    build_native_linux_preparation_context,
)
from harako_gpu.services.run_execution import _transport_argv
from harako_gpu.commands.root import app


NATIVE_CONTEXT = parse_execution_context(NATIVE_LINUX)
WSL_CONTEXT = parse_execution_context("wsl2", distribution="Ubuntu")
IS_GENUINE_NATIVE_LINUX = platform.system() == "Linux" and "microsoft" not in platform.release().casefold()
native_linux_runtime = pytest.mark.skipif(
    not IS_GENUINE_NATIVE_LINUX, reason="requires genuine native Linux filesystem/process semantics",
)


def result(argv, *, code=0, out="", err="") -> CommandResult:
    return CommandResult(tuple(argv), code, out, err)


def test_execution_contexts_are_explicit_and_frozen() -> None:
    native = parse_execution_context("native-linux", distribution="ignored")
    assert native.identity == NATIVE_LINUX and native.distribution is None
    wsl = parse_execution_context("wsl2", distribution="Ubuntu")
    assert wsl.identity == "wsl2:Ubuntu" and wsl.distribution == "Ubuntu"
    with pytest.raises(ValueError, match="Unsupported"):
        parse_execution_context("remote")
    with pytest.raises(ValueError, match="does not match"):
        require_context_match(requested="native-linux", frozen="wsl2:Ubuntu", distribution="Ubuntu")
    with pytest.raises(ValueError, match="distribution"):
        parse_execution_context("wsl2")
    assert _transport_argv(native, ("docker", "version")) == ("docker", "version")
    assert _transport_argv(wsl, ("docker", "version")) == (
        "wsl.exe", "--distribution", "Ubuntu", "--exec", "docker", "version",
    )


def test_native_host_gate_rejects_windows_wsl_and_macos() -> None:
    require_native_linux_host(host_system="Linux", kernel_release="6.14.0-generic")
    with pytest.raises(ValueError, match="WSL"):
        require_native_linux_host(host_system="Linux", kernel_release="5.15-microsoft-standard-WSL2")
    for system in ("Windows", "Darwin"):
        with pytest.raises(ValueError, match="unavailable"):
            require_native_linux_host(host_system=system, kernel_release="fixture")


class StreamingRunner:
    def __init__(self, returncode: int = 0):
        self.returncode = returncode
        self.call = None

    def run_streaming(self, argv, **kwargs):
        self.call = (tuple(argv), kwargs)
        kwargs["on_started"](4321)
        return result(argv, code=self.returncode)


@native_linux_runtime
def test_native_streaming_preserves_argv_env_pid_logs_and_nonzero(tmp_path: Path) -> None:
    runner = StreamingRunner(returncode=42)
    spec = CommandSpec(("/usr/bin/false", "fixed"), str(tmp_path),
                       {"PATH": "/usr/bin", "NXF_VER": "25.04.3"}, str(tmp_path / "child.pid"))
    observed = []
    value = run_native_streaming(
        spec, runner=runner, stdout_path=tmp_path / "stdout.log", stderr_path=tmp_path / "stderr.log",
        on_started=observed.append,
    )
    assert value.returncode == 42 and observed == [4321]
    assert (tmp_path / "child.pid").read_text() == "4321\n"
    argv, kwargs = runner.call
    assert argv == spec.argv and kwargs["cwd"] == tmp_path
    assert kwargs["env"] == spec.env and kwargs["inherit_env"] is False


class PreparationRunner:
    def __init__(self, version: str = "25.04.3", missing_role: str | None = None):
        self.version = version
        self.missing_role = missing_role
        self.calls = []

    def run(self, argv, **kwargs):
        command = tuple(argv)
        self.calls.append((command, kwargs))
        if command[-1] == "-version":
            return result(command, out=f"nextflow version {self.version}\n")
        if command[:3] == ("docker", "image", "inspect"):
            image = command[-1]
            if self.missing_role and self.missing_role in image:
                return result(command, code=1, err="missing")
            contract = next(value for value in IMAGE_CONTRACTS.values() if image in {
                value.reference, value.execution_reference,
            })
            payload = {"Id": contract.identity if contract.identity_kind == "image_id" else "sha256:" + "f" * 64}
            if contract.identity_kind == "repo_digest":
                payload["RepoDigests"] = [f"{contract.repository}@{contract.identity}"]
            return result(command, out=json.dumps([payload]))
        raise AssertionError(command)


@native_linux_runtime
def test_native_preparation_resolves_exact_nextflow_and_direct_image_inspect(tmp_path: Path) -> None:
    nextflow = tmp_path / "nextflow"
    nextflow.write_text("fixture")
    runner = PreparationRunner()
    context = build_native_linux_preparation_context(
        runtime_root=str(tmp_path), nextflow_executable=str(nextflow), runner=runner,
        host_system="Linux", kernel_release="fixture", hardware_report={"schema_version": 1},
    )
    assert context.execution.identity == NATIVE_LINUX and context.execution.distribution is None
    assert context.nextflow_executable == str(nextflow)
    assert context.observed_image_ids == EXPECTED_IMAGES
    assert all(call[0] != "wsl.exe" for call, _ in runner.calls)
    assert any(call[:3] == ("docker", "image", "inspect") for call, _ in runner.calls)


@native_linux_runtime
@pytest.mark.parametrize(("version", "missing_role", "missing_executable", "message"), (
    ("25.04.4", None, False, "25.04.3"),
    ("25.04.3", "nvcr.io", False, "parabricks"),
    ("25.04.3", None, True, "missing"),
))
def test_native_preparation_rejects_invalid_toolchain(
    tmp_path: Path, version: str, missing_role: str | None,
    missing_executable: bool, message: str,
) -> None:
    nextflow = tmp_path / "nextflow"
    if not missing_executable:
        nextflow.write_text("fixture")
    with pytest.raises(ValueError, match=message):
        build_native_linux_preparation_context(
            runtime_root=str(tmp_path), nextflow_executable=str(nextflow),
            runner=PreparationRunner(version, missing_role), host_system="Linux",
            kernel_release="fixture", hardware_report={},
        )


@native_linux_runtime
def test_native_pipeline_freeze_is_read_only(tmp_path: Path) -> None:
    pipeline = tmp_path / "pipeline"
    pipeline.mkdir()
    source = pipeline / "main.nf"
    source.write_text("workflow {}\n")
    context = PreparationContext(
        NATIVE_CONTEXT, str(pipeline), "/usr/bin/nextflow", {}, {}, tmp_path,
        PreparationRunner(),
    )
    _freeze_pipeline(str(pipeline), context)
    assert source.stat().st_mode & 0o222 == 0


@native_linux_runtime
def test_native_pipeline_copy_uses_filesystem_without_wsl(tmp_path: Path) -> None:
    source = tmp_path / "source"; source.mkdir(); (source / "main.nf").write_text("workflow {}\n")
    destination = tmp_path / "destination"
    runner = PreparationRunner()
    context = PreparationContext(
        NATIVE_CONTEXT, str(source), "/usr/bin/nextflow", {}, {}, tmp_path, runner,
    )
    _copy_pipeline(str(source), str(destination), context)
    assert (destination / "main.nf").read_text() == "workflow {}\n"
    assert runner.calls == []


def test_symlink_escape_is_rejected_by_runtime_boundary(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir(); outside.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes"):
        ensure_within(root / "escape" / "run", root)


class BamRunner:
    def __init__(self):
        self.calls = []

    def run(self, argv, **_kwargs):
        command = tuple(argv)
        self.calls.append(command)
        if "view" in command:
            return result(command, out="@HD\tSO:coordinate\n@SQ\tSN:chr1\n@RG\tID:r1\n")
        if "checksum" in command:
            return result(command, out="checksum\n")
        return result(command, out="ok\n")


@pytest.mark.parametrize(("context", "prefix"), (
    (NATIVE_CONTEXT, ("docker",)),
    (WSL_CONTEXT, ("wsl.exe", "--distribution", "Ubuntu", "--exec")),
))
def test_bam_validation_transport_prefix(context: ExecutionContext, prefix: tuple[str, ...]) -> None:
    runner = BamRunner()
    validation = validate_bam(bam="/data/a.bam", bai="/data/a.bam.bai", execution=context, runner=runner)
    assert validation.valid and all(call[:len(prefix)] == prefix for call in runner.calls)
    assert all(LEGACY_WSL_UTILITY_SAMTOOLS_IMAGE_ID in call for call in runner.calls)


def test_bam_validation_uses_supplied_frozen_image_contract() -> None:
    runner = BamRunner()
    contract = DockerImageContract(
        "community.wave.seqera.io/library/htslib_samtools:1.23.1--5b6bb4ede7e612e5",
        "sha256:b762af53a769d82aa0111bfbc4574c8bb8c07f9257a8e09c8403c4f540a10a07",
        "image_id",
    )

    validation = validate_bam(
        bam="/data/a.bam",
        bai="/data/a.bam.bai",
        execution=NATIVE_CONTEXT,
        image_contract=contract,
        runner=runner,
    )

    assert validation.valid
    assert all(contract.execution_reference in call for call in runner.calls)
    assert all(LEGACY_WSL_UTILITY_SAMTOOLS_IMAGE_ID not in call for call in runner.calls)
    assert all("--pull=never" in call for call in runner.calls)


def test_bam_validation_uses_repository_digest_execution_reference() -> None:
    runner = BamRunner()
    contract = DockerImageContract(
        "example.invalid/samtools:fixed",
        "sha256:" + "a" * 64,
        "repo_digest",
    )
    validate_bam(
        bam="/data/a.bam",
        bai="/data/a.bam.bai",
        execution=NATIVE_CONTEXT,
        image_contract=contract,
        runner=runner,
    )
    assert all(f"example.invalid/samtools@{contract.identity}" in call for call in runner.calls)
    assert all(f"{contract.reference}@{contract.identity}" not in call for call in runner.calls)


def test_bam_validation_rejects_split_artifact_directories() -> None:
    with pytest.raises(ValueError, match="share"):
        validate_bam(
            bam="/data/a.bam", bai="/other/a.bam.bai",
            execution=NATIVE_CONTEXT, runner=BamRunner(),
        )


class ResourceRunner:
    def __init__(self):
        self.calls = []

    def run(self, argv, **_kwargs):
        command = tuple(argv); self.calls.append(command)
        joined = " ".join(command)
        if "nvidia-smi" in joined:
            return result(command, out="GPU-1, 100, 24576, 10, 120, 40, P2, Active\n")
        if "/proc/meminfo" in command:
            return result(command, out="MemTotal: 1000 kB\nMemAvailable: 500 kB\nCached: 10 kB\nBuffers: 5 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n")
        if "/proc/stat" in command:
            return result(command, out="cpu 1 1 1 10 0 0 0 0\n")
        if "/proc/loadavg" in command:
            return result(command, out="0.1 0.2 0.3 1/1 1\n")
        if "/sys/fs/cgroup/memory.current" in command:
            return result(command, out="100\n")
        if "/proc/pressure/memory" in command:
            return result(command, out="some avg10=0.00 avg60=0.00 avg300=0.00 total=0\n")
        if any(part.endswith("/df") for part in command):
            return result(command, out="Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/x 100 1 99 1% /\n/dev/x 100 1 98 1% /\n")
        if any(part.endswith("/du") for part in command):
            return result(command, out="1\t/work\n2\t/result\n")
        if any(part.endswith("/ps") for part in command):
            return result(command, out="100 1.0 java\n")
        raise AssertionError(command)


def test_native_resource_monitor_uses_direct_commands_and_common_schema(tmp_path: Path) -> None:
    runner = ResourceRunner()
    native = ResourceMonitor(
        NATIVE_CONTEXT, "/work", "/result", tmp_path / "resources.tsv", runner,
    )
    sample = native.sample()
    assert sample["gpu_uuid"] == "GPU-1" and sample["ram_total_bytes"] == 1000 * 1024
    assert runner.calls[0][0] == "nvidia-smi"
    assert all("wsl.exe" not in call for call in runner.calls)
    native.start(); native.stop()
    assert native._thread is not None and not native._thread.is_alive()
    wsl_runner = ResourceRunner()
    wsl = ResourceMonitor(WSL_CONTEXT, "/work", "/result", tmp_path / "wsl.tsv", wsl_runner)
    wsl.sample()
    assert wsl_runner.calls[0][:4] == ("wsl.exe", "--distribution", "Ubuntu", "--exec")
    assert "/usr/lib/wsl/lib/nvidia-smi" in wsl_runner.calls[0]


def test_resource_monitor_failure_is_best_effort(tmp_path: Path) -> None:
    class MissingRunner:
        def run(self, argv, **_kwargs):
            return CommandResult(tuple(argv), 1, "", "missing")
    monitor = ResourceMonitor(
        NATIVE_CONTEXT, "/work", "/result", tmp_path / "missing.tsv", MissingRunner(),
    )
    assert monitor.sample()["status"] == "RESOURCE_MONITOR_UNAVAILABLE"
    assert monitor.snapshot["status"] == "RESOURCE_MONITOR_UNAVAILABLE"


def test_resource_monitor_keeps_host_samples_when_du_is_partial(tmp_path: Path) -> None:
    class PartialDuRunner(ResourceRunner):
        def run(self, argv, **kwargs):
            command = tuple(argv)
            if any(part.endswith("/du") for part in command):
                self.calls.append(command)
                return result(
                    command, code=1, out="1\t/work\n2\t/result\n",
                    err="du: cannot read completed task scratch: Permission denied\n",
                )
            return super().run(argv, **kwargs)

    monitor = ResourceMonitor(
        NATIVE_CONTEXT, "/work", "/result", tmp_path / "partial.tsv", PartialDuRunner(),
    )

    sample = monitor.sample()

    assert sample["gpu_uuid"] == "GPU-1"
    assert sample["work_current_bytes"] == 1
    assert sample["result_current_bytes"] == 2
    assert "RESOURCE_STORAGE_PARTIAL" in (monitor.warning or "")
    assert (tmp_path / "partial.tsv").is_file()


def _native_run_fixture(root: Path) -> None:
    for relative in ("tasks", "frozen", "execution/attempts", "artifacts", "support"):
        (root / relative).mkdir(parents=True)
    identity = {
        "run_id": "20260818T000000Z-aaaaaaaa", "project_slug": "fixture",
        "analysis_series_id": "series", "primary_profile_id": "primary",
        "secondary_profile_id": None, "execution_context": NATIVE_LINUX,
    }
    (root / "run.json").write_text(__import__("json").dumps({"schema_version": 1, "identity": identity}))
    (root / "status.json").write_text(__import__("json").dumps({
        "schema_version": 1, "run_id": identity["run_id"], "state": "PREPARED",
        "current_stage": None, "current_task": None, "attempt_id": None,
        "updated_at": "2026-08-18T00:00:00Z",
    }))
    (root / "tasks/tasks.json").write_text('{"schema_version":1,"tasks":[]}')
    (root / "frozen/plan.json").write_text(__import__("json").dumps({
        "samples": [], "alignment_profile_id": "profile",
        "quantification": {"primary_profile_id": "primary", "secondary_profile_id": None},
    }))


@native_linux_runtime
def test_native_cli_inspect_status_artifacts_and_support_use_frozen_context(tmp_path: Path) -> None:
    _native_run_fixture(tmp_path)
    cli = CliRunner()
    for argv in (
        ["run", "inspect", str(tmp_path), "--json", "--execution-context", "native-linux"],
        ["run", "status", str(tmp_path), "--json", "--execution-context", "native-linux"],
        ["artifacts", "list", str(tmp_path), "--json", "--execution-context", "native-linux"],
        ["support-bundle", "create", str(tmp_path), "--execution-context", "native-linux"],
    ):
        response = cli.invoke(app, argv)
        assert response.exit_code == 0, response.stdout
    assert list((tmp_path / "support").glob("*-support.zip"))
    mismatch = cli.invoke(app, [
        "run", "inspect", str(tmp_path), "--execution-context", "wsl2",
    ])
    assert mismatch.exit_code != 0
    invalid = cli.invoke(app, [
        "run", "inspect", str(tmp_path), "--execution-context", "remote",
    ])
    assert invalid.exit_code != 0
