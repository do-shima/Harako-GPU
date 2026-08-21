from __future__ import annotations

from pathlib import Path

import pytest

from harako_gpu.adapters.process import CommandResult
from harako_gpu.core.contracts import NextflowVersionStatus, PrerequisiteSeverity, QualificationStatus
from harako_gpu.services.preflight import collect_preflight, parse_nvidia_smi, report_json


GPU_CSV = "NVIDIA RTX, GPU-1, 24576, 20000, 555.10\n"


def result(argv, *, code=0, out="", err="", timeout=False, exception=""):
    return CommandResult(tuple(argv), code, out, err, timeout, exception)


class FakeRunner:
    def __init__(
        self, *, gpu=GPU_CSV, docker="ready", wsl="ready", wsl_gpu="path",
        java="17.0.12", nextflow="25.04.3", nf_core=True, parabricks=True,
        cuda_image=True, cpu=32, total_ram_gib=128, work_free_gib=500, overrides=None,
    ):
        self.gpu = gpu
        self.docker = docker
        self.wsl = wsl
        self.wsl_gpu = wsl_gpu
        self.java = java
        self.nextflow = nextflow
        self.nf_core = nf_core
        self.parabricks = parabricks
        self.cuda_image = cuda_image
        self.cpu = cpu
        self.total_ram_gib = total_ram_gib
        self.work_free_gib = work_free_gib
        self.overrides = overrides or {}
        self.calls = []

    def run(self, argv, **kwargs):
        self.calls.append((tuple(argv), kwargs))
        key = tuple(argv)
        if key in self.overrides:
            return self.overrides[key]
        if argv[0] == "nvidia-smi":
            return result(argv, out=self.gpu)
        if argv[:2] == ["docker", "info"]:
            if self.docker == "missing":
                return result(argv, code=None, exception="FileNotFoundError: docker")
            if self.docker == "daemon_down":
                return result(argv, code=1, err="Cannot connect to the Docker daemon")
            return result(argv, out='{"Runtimes":{"nvidia":{}},"OSType":"linux"}')
        if argv[:3] == ["docker", "image", "inspect"]:
            return result(argv, out="sha256:parabricks") if self.parabricks else result(argv, code=1, err="No such image")
        if argv[:3] == ["docker", "image", "ls"]:
            return result(argv, out="nvidia/cuda:12.6-base\n" if self.cuda_image else "other/image:latest\n")
        if argv[0] == "java":
            return result(argv, err=f'openjdk version "{self.java}"') if self.java else result(argv, code=None, exception="FileNotFoundError: java")
        if argv[0] == "nextflow":
            return result(argv, out=f"nextflow version {self.nextflow}") if self.nextflow else result(argv, code=None, exception="FileNotFoundError: nextflow")
        if argv[0] == "nf-core":
            return result(argv, out="nf-core 3") if self.nf_core else result(argv, code=None, exception="FileNotFoundError: nf-core")
        if argv[:2] == ["wsl.exe", "--status"]:
            return result(argv, out="Default Distribution: Ubuntu\nDefault Version: 2\n") if self.wsl == "ready" else result(argv, code=None, exception="FileNotFoundError: wsl.exe")
        if argv[:3] == ["wsl.exe", "--list", "--verbose"]:
            return result(argv, out="  NAME STATE VERSION\n* Ubuntu Running 2\n") if self.wsl == "ready" else result(argv, code=None, exception="FileNotFoundError: wsl.exe")
        if argv[:2] == ["wsl.exe", "--exec"]:
            return self._wsl(argv)
        raise AssertionError(f"Unexpected command: {argv}")

    def _wsl(self, argv):
        command = argv[2:]
        if self.wsl != "ready":
            return result(argv, code=1, err="WSL unavailable")
        if command[:3] == ["sh", "-lc", "command -v nvidia-smi"]:
            return result(argv, out="/usr/bin/nvidia-smi\n") if self.wsl_gpu == "path" else result(argv, code=1)
        if command[:3] == ["sh", "-lc", "command -v nextflow"]:
            return result(argv, out="/usr/bin/nextflow\n") if self.nextflow else result(argv, code=1)
        if command and command[0] == "nvidia-smi":
            return result(argv, out=self.gpu) if self.wsl_gpu == "path" else result(argv, code=1, err="not found")
        if command and command[0] == "/usr/lib/wsl/lib/nvidia-smi":
            if self.wsl_gpu == "fallback":
                return result(argv, out=self.gpu)
            if self.wsl_gpu == "malformed":
                return result(argv, out="not,csv\n")
            return result(argv, code=1, err="not found")
        if command[:2] == ["docker", "version"]:
            return result(argv, out='{"Client":{"Os":"linux"},"Server":{"Os":"linux","Version":"29"}}') if self.docker == "ready" else result(argv, code=1, err="cannot connect")
        if command[:2] == ["docker", "info"]:
            return result(argv, out='{"OSType":"linux","Runtimes":{"nvidia":{}}}') if self.docker == "ready" else result(argv, code=1, err="cannot connect")
        if command[:3] == ["docker", "context", "show"]:
            return result(argv, out="default\n") if self.docker == "ready" else result(argv, code=1)
        if command == ["java", "-version"]:
            return result(argv, err=f'openjdk version "{self.java}"') if self.java else result(argv, code=None, exception="FileNotFoundError: java")
        if command == ["env", "NXF_VER=25.04.3", "/usr/bin/nextflow", "-version"]:
            return result(argv, out=f"nextflow version {self.nextflow}") if self.nextflow else result(argv, code=None, exception="FileNotFoundError: nextflow")
        if command == ["nf-core", "--version"]:
            return result(argv, out="nf-core 3") if self.nf_core else result(argv, code=None, exception="FileNotFoundError: nf-core")
        if command == ["getconf", "_NPROCESSORS_ONLN"]:
            return result(argv, out=f"{self.cpu}\n")
        if command == ["cat", "/proc/meminfo"]:
            total_kib = self.total_ram_gib * 1024**2
            return result(argv, out=f"MemTotal: {total_kib} kB\nMemAvailable: {total_kib // 2} kB\n")
        if command[:4] == ["df", "-Pk", "--", "/"]:
            free_kib = self.work_free_gib * 1024**2
            return result(argv, out=f"Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/sda 999999 1 {free_kib} 1% /\n")
        raise AssertionError(f"Unexpected WSL command: {command}")


def snapshot(system="Linux"):
    return {
        "os": system,
        "execution_context": "windows" if system == "Windows" else "native_linux",
        "cpu": {"logical_count": 32},
        "host_ram_bytes": 128 * 1024**3,
        "disk": {"path": ".", "total_bytes": 1024**4, "free_bytes": 500 * 1024**3},
        "python": {"version": "3.12", "executable": "python"},
    }


def active_codes(report):
    return {item.code for item in report.prerequisites if item.active}


def test_native_linux_with_nvidia_gpu_is_low_memory_candidate() -> None:
    report = collect_preflight(runner=FakeRunner(), snapshot=snapshot())
    assert report.qualification_status is QualificationStatus.PREFLIGHT_READY_LOW_MEMORY_CANDIDATE
    assert report.nvidia_gpus[0].uuid == "GPU-1"


def test_windows_without_wsl_is_blocked() -> None:
    report = collect_preflight(runner=FakeRunner(wsl="missing"), snapshot=snapshot("Windows"))
    assert report.qualification_status is QualificationStatus.BLOCKED
    assert "WSL2_UNAVAILABLE" in active_codes(report)


def test_wsl_nvidia_smi_in_path() -> None:
    report = collect_preflight(runner=FakeRunner(wsl_gpu="path"), snapshot=snapshot("Windows"))
    assert report.nvidia_smi.available is True
    assert report.wsl_status["nvidia"]["executed_path"] == "/usr/bin/nvidia-smi"
    assert "NVIDIA_SMI_PATH_NOT_EXPORTED" not in active_codes(report)


def test_wsl_nvidia_smi_full_path_fallback_is_warning_not_gpu_failure() -> None:
    report = collect_preflight(runner=FakeRunner(wsl_gpu="fallback"), snapshot=snapshot("Windows"))
    assert report.nvidia_smi.available is True
    assert report.wsl_status["nvidia"]["executed_path"] == "/usr/lib/wsl/lib/nvidia-smi"
    assert report.wsl_status["nvidia"]["recommended_path"] == "/usr/lib/wsl/lib"
    assert "NVIDIA_SMI_PATH_NOT_EXPORTED" in active_codes(report)
    assert "WSL_GPU_UNAVAILABLE" not in active_codes(report)


@pytest.mark.parametrize("mode", ["missing", "malformed"])
def test_wsl_gpu_missing_or_malformed_blocks(mode) -> None:
    report = collect_preflight(runner=FakeRunner(wsl_gpu=mode), snapshot=snapshot("Windows"))
    assert report.qualification_status is QualificationStatus.BLOCKED
    assert "WSL_GPU_UNAVAILABLE" in active_codes(report)


def test_nf_core_cli_absence_does_not_block() -> None:
    report = collect_preflight(runner=FakeRunner(nf_core=False), snapshot=snapshot("Windows"))
    finding = next(item for item in report.prerequisites if item.code == "NF_CORE_CLI_UNAVAILABLE")
    assert finding.active is True and finding.severity is PrerequisiteSeverity.OPTIONAL
    assert report.qualification_status is QualificationStatus.PREFLIGHT_READY_LOW_MEMORY_CANDIDATE


def test_cuda_sample_image_absence_does_not_block() -> None:
    report = collect_preflight(runner=FakeRunner(cuda_image=False), snapshot=snapshot("Windows"))
    assert report.cuda_test_image.reason_code == "GPU_CONTAINER_TEST_NOT_RUN"
    assert report.qualification_status is QualificationStatus.PREFLIGHT_READY_LOW_MEMORY_CANDIDATE


def test_docker_wsl_integration_absence_blocks() -> None:
    report = collect_preflight(runner=FakeRunner(docker="daemon_down"), snapshot=snapshot("Windows"))
    assert "DOCKER_WSL_INTEGRATION_UNAVAILABLE" in active_codes(report)
    assert report.qualification_status is QualificationStatus.BLOCKED


def test_java_11_blocks_with_explicit_reason() -> None:
    report = collect_preflight(runner=FakeRunner(java="11.0.31"), snapshot=snapshot("Windows"))
    assert report.java.detected_version == "11.0.31"
    assert "JAVA_VERSION_UNSUPPORTED" in active_codes(report)
    assert report.qualification_status is QualificationStatus.BLOCKED


def test_newer_nextflow_is_supported_but_unqualified_and_does_not_block() -> None:
    report = collect_preflight(runner=FakeRunner(nextflow="25.04.8"), snapshot=snapshot("Windows"))
    assert report.nextflow_version_status is NextflowVersionStatus.VERSION_SUPPORTED_BUT_NOT_YET_QUALIFIED
    assert report.qualification_status is QualificationStatus.PREFLIGHT_READY_LOW_MEMORY_CANDIDATE


def test_parabricks_image_absence_blocks_execution_readiness() -> None:
    report = collect_preflight(runner=FakeRunner(parabricks=False), snapshot=snapshot("Windows"))
    assert "PARABRICKS_IMAGE_UNAVAILABLE" in active_codes(report)
    assert report.qualification_status is QualificationStatus.BLOCKED


def test_wsl_resource_thresholds_are_distinct_and_scratch_blocks() -> None:
    report = collect_preflight(
        runner=FakeRunner(cpu=12, total_ram_gib=64, work_free_gib=50), snapshot=snapshot("Windows")
    )
    assert report.wsl_status["resources"]["logical_cpu_count"] == 12
    assert "WSL_CPU_THREADS_BELOW_CANDIDATE" in active_codes(report)
    assert "PARABRICKS_HOST_MEMORY_BELOW_RECOMMENDED" in active_codes(report)
    assert "WSL_WORK_ROOT_SCRATCH_INSUFFICIENT" in active_codes(report)
    assert report.qualification_status is QualificationStatus.BLOCKED


def test_multiple_gpus_are_all_reported() -> None:
    gpu = "A, GPU-A, 49152, 40000, 555.10\nB, GPU-B, 49152, 30000, 555.10\n"
    report = collect_preflight(runner=FakeRunner(gpu=gpu), snapshot=snapshot())
    assert report.qualification_status is QualificationStatus.PREFLIGHT_READY
    assert [item.uuid for item in report.nvidia_gpus] == ["GPU-A", "GPU-B"]


def test_malformed_command_output_is_not_silently_accepted() -> None:
    parsed, driver, status = parse_nvidia_smi(result(["nvidia-smi"], out="not,csv\n"))
    assert parsed == () and driver is None
    assert status.status == "malformed"


def test_timeout_retains_raw_stderr() -> None:
    argv = ("nextflow", "-version")
    runner = FakeRunner(overrides={argv: result(argv, code=None, err="partial error", timeout=True, exception="Timed out after 8 seconds")})
    report = collect_preflight(runner=runner, snapshot=snapshot())
    assert report.nextflow.stderr == "partial error"
    assert report.support_details["effective_nextflow"]["timed_out"] is True


def test_report_json_contains_version_contract() -> None:
    payload = report_json(collect_preflight(runner=FakeRunner(), snapshot=snapshot()))
    assert '"minimum_nextflow_version": "25.04.3"' in payload
    assert '"qualified_nextflow_version": "25.04.3"' in payload


def test_wsl_nextflow_probe_uses_pinned_structured_environment() -> None:
    runner = FakeRunner()
    collect_preflight(runner=runner, snapshot=snapshot("Windows"))
    expected = ("wsl.exe", "--exec", "env", "NXF_VER=25.04.3", "/usr/bin/nextflow", "-version")
    assert any(argv == expected and kwargs["timeout"] == 30 for argv, kwargs in runner.calls)
