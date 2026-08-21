"""Hardware/runtime preflight orchestration; never installs, pulls, or executes containers."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from harako_gpu.adapters import docker, environment, wsl
from harako_gpu.adapters.process import CommandResult, ProcessRunner
from harako_gpu.core.contracts import (
    GpuInfo,
    HardwareReport,
    JavaVersionStatus,
    MINIMUM_NEXTFLOW_VERSION,
    MINIMUM_WORK_ROOT_FREE_BYTES,
    MINIMUM_WSL_CPU_THREADS,
    NextflowVersionStatus,
    PrerequisiteFinding,
    PrerequisiteSeverity,
    ProbeStatus,
    QUALIFIED_NEXTFLOW_VERSION,
    QualificationStatus,
    RECOMMENDED_PARABRICKS_HOST_RAM_BYTES,
)
from harako_gpu.services.runtime_versions import JavaAssessment, NextflowAssessment, assess_java, assess_nextflow


LOW_MEMORY_THRESHOLD_BYTES = 32 * 1024**3


def _detail(result: CommandResult) -> dict[str, Any]:
    return {
        "argv": list(result.argv), "returncode": result.returncode, "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(), "timed_out": result.timed_out, "exception": result.exception,
    }


def _probe(result: CommandResult, label: str) -> ProbeStatus:
    if result.timed_out:
        return ProbeStatus(False, "timeout", result.exception, result.stderr.strip())
    if result.exception:
        return ProbeStatus(False, "unavailable", result.exception, result.stderr.strip())
    if result.returncode != 0:
        return ProbeStatus(False, "failed", f"{label} exited with {result.returncode}", result.stderr.strip())
    detail = result.stdout.strip() or result.stderr.strip()
    return ProbeStatus(True, "available", detail, result.stderr.strip())


def _java_probe(result: CommandResult) -> tuple[ProbeStatus, JavaAssessment]:
    assessment = assess_java(result)
    found = assessment.status is not JavaVersionStatus.JAVA_NOT_FOUND
    detail = f"Detected Java {assessment.version} (major {assessment.major})" if assessment.version else result.exception or "Java version could not be parsed"
    return ProbeStatus(found, assessment.status.value, detail, result.stderr.strip(), assessment.status.value, assessment.version), assessment


def _nextflow_probe(result: CommandResult) -> tuple[ProbeStatus, NextflowAssessment]:
    assessment = assess_nextflow(result)
    found = assessment.status is not NextflowVersionStatus.NEXTFLOW_NOT_FOUND
    detail = f"Detected Nextflow {assessment.version}" if assessment.version else result.exception or "Nextflow version could not be parsed"
    return ProbeStatus(found, assessment.status.value, detail, result.stderr.strip(), assessment.status.value, assessment.version), assessment


def parse_nvidia_smi(result: CommandResult) -> tuple[tuple[GpuInfo, ...], str | None, ProbeStatus]:
    base = _probe(result, "nvidia-smi")
    if not base.available:
        return (), None, replace(base, reason_code="WSL_GPU_UNAVAILABLE")
    gpus: list[GpuInfo] = []
    drivers: set[str] = set()
    malformed: list[str] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 5:
            malformed.append(line)
            continue
        name, uuid, total_mib, free_mib, driver = fields
        try:
            gpus.append(GpuInfo(name, uuid, int(float(total_mib)) * 1024**2, int(float(free_mib)) * 1024**2))
        except ValueError:
            malformed.append(line)
            continue
        if driver:
            drivers.add(driver)
    if malformed or not gpus:
        message = "Malformed nvidia-smi CSV output"
        if malformed:
            message += ": " + " | ".join(malformed)
        return tuple(gpus), next(iter(drivers), None), ProbeStatus(False, "malformed", message, result.stderr.strip(), "NVIDIA_SMI_OUTPUT_MALFORMED")
    driver = sorted(drivers)[0] if len(drivers) == 1 else ", ".join(sorted(drivers))
    return tuple(gpus), driver, ProbeStatus(True, "available", f"Detected {len(gpus)} NVIDIA GPU(s)", result.stderr.strip())


def _image_probe(result: CommandResult, label: str) -> ProbeStatus:
    if result.ok and result.stdout.strip():
        return ProbeStatus(True, "present", result.stdout.strip(), result.stderr.strip())
    if result.timed_out:
        return ProbeStatus(False, "timeout", result.exception, result.stderr.strip())
    return ProbeStatus(False, "not_present", f"{label} is not present locally", result.stderr.strip() or result.exception)


def _json_object(result: CommandResult) -> dict[str, Any] | None:
    if not result.ok:
        return None
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _parse_meminfo(result: CommandResult) -> tuple[int | None, int | None]:
    if not result.ok:
        return None, None
    values: dict[str, int] = {}
    try:
        for line in result.stdout.splitlines():
            key, raw = line.split(":", 1)
            values[key] = int(raw.strip().split()[0]) * 1024
    except (ValueError, IndexError):
        return None, None
    return values.get("MemTotal"), values.get("MemAvailable")


def _parse_df_free(result: CommandResult) -> int | None:
    if not result.ok:
        return None
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    try:
        return int(lines[-1].split()[3]) * 1024
    except (ValueError, IndexError):
        return None


def _finding(code: str, severity: PrerequisiteSeverity, active: bool, detail: str) -> PrerequisiteFinding:
    return PrerequisiteFinding(code, severity, active, detail)


def _version_findings(java: JavaAssessment, nextflow: NextflowAssessment) -> list[PrerequisiteFinding]:
    findings: list[PrerequisiteFinding] = []
    java_code = java.status.value
    findings.append(_finding(
        java_code,
        PrerequisiteSeverity.HARD_BLOCKER,
        java.status is not JavaVersionStatus.VERSION_GATE_PASS,
        f"Java {java.version or 'not detected'}; minimum major is 17.",
    ))
    unsupported = nextflow.status in {
        NextflowVersionStatus.NEXTFLOW_NOT_FOUND,
        NextflowVersionStatus.NEXTFLOW_VERSION_UNSUPPORTED,
        NextflowVersionStatus.NEXTFLOW_VERSION_MALFORMED,
    }
    findings.append(_finding(
        nextflow.status.value,
        PrerequisiteSeverity.HARD_BLOCKER if unsupported else PrerequisiteSeverity.WARNING,
        unsupported or nextflow.status is NextflowVersionStatus.VERSION_SUPPORTED_BUT_NOT_YET_QUALIFIED,
        f"Nextflow {nextflow.version or 'not detected'}; minimum/initial-qualified version is 25.04.3.",
    ))
    return findings


def collect_preflight(
    *, runner: ProcessRunner | None = None, cwd: Path | None = None,
    snapshot: dict[str, Any] | None = None, wsl_work_root: str = "/",
) -> HardwareReport:
    process = runner or ProcessRunner()
    working = (cwd or Path.cwd()).resolve()
    host = dict(snapshot or environment.host_snapshot(working))
    support: dict[str, Any] = {}
    findings: list[PrerequisiteFinding] = []

    host_nvidia_result = process.run([
        "nvidia-smi", "--query-gpu=name,uuid,memory.total,memory.free,driver_version",
        "--format=csv,noheader,nounits",
    ])
    support["host_nvidia_smi"] = _detail(host_nvidia_result)
    host_gpus, host_driver, host_nvidia = parse_nvidia_smi(host_nvidia_result)

    docker_result = docker.daemon_info(process)
    support["docker_info"] = _detail(docker_result)
    docker_status = _probe(docker_result, "docker info")
    findings.append(_finding("DOCKER_DAEMON_UNAVAILABLE", PrerequisiteSeverity.HARD_BLOCKER, not bool(docker_status.available), docker_status.detail))
    if docker_result.ok:
        runtime_available = "nvidia" in docker_result.stdout.lower()
        docker_gpu = ProbeStatus(runtime_available, "available" if runtime_available else "missing",
                                 "NVIDIA runtime indication found" if runtime_available else "Docker info has no NVIDIA runtime indication",
                                 docker_result.stderr.strip(), None if runtime_available else "DOCKER_GPU_ACCESS_UNAVAILABLE")
        parabricks_result = docker.inspect_image(process, docker.PARABRICKS_IMAGE)
        images_result = docker.local_images(process)
    else:
        docker_gpu = ProbeStatus(False, "not_tested", "Docker daemon unavailable", docker_result.stderr.strip(), "DOCKER_GPU_ACCESS_UNAVAILABLE")
        parabricks_result = CommandResult(("docker", "image", "inspect", docker.PARABRICKS_IMAGE), None, "", "", exception="Docker daemon unavailable")
        images_result = CommandResult(("docker", "image", "ls"), None, "", "", exception="Docker daemon unavailable")
    support["parabricks_image"] = _detail(parabricks_result)
    support["docker_images"] = _detail(images_result)
    parabricks = _image_probe(parabricks_result, docker.PARABRICKS_IMAGE)
    findings.append(_finding("PARABRICKS_IMAGE_UNAVAILABLE", PrerequisiteSeverity.HARD_BLOCKER, not bool(parabricks.available), parabricks.detail))
    cuda_lines = [
        line for line in images_result.stdout.splitlines()
        if "nvidia/cuda" in line.lower() or "cuda-sample" in line.lower()
    ]
    cuda_image = ProbeStatus(True, "present", ", ".join(cuda_lines)) if images_result.ok and cuda_lines else ProbeStatus(False, "not_tested", "GPU container qualification test has not run; no local CUDA sample image detected", images_result.stderr.strip() or images_result.exception, "GPU_CONTAINER_TEST_NOT_RUN")
    findings.append(_finding("GPU_CONTAINER_TEST_NOT_RUN", PrerequisiteSeverity.OPTIONAL, not bool(cuda_image.available), cuda_image.detail))

    host_tools = {
        "java": process.run(["java", "-version"]),
        "nextflow": process.run(
            ["nextflow", "-version"], timeout=30,
            env={"NXF_VER": QUALIFIED_NEXTFLOW_VERSION},
        ),
        "nf_core": process.run(["nf-core", "--version"]),
    }
    for name, result in host_tools.items():
        support[f"host_{name}"] = _detail(result)

    wsl_status: dict[str, Any] = {"available": None, "status": "not_applicable"}
    gpus, driver, nvidia_status = host_gpus, host_driver, host_nvidia
    docker_gpu_access = docker_gpu
    effective_java_result = host_tools["java"]
    effective_nextflow_result = host_tools["nextflow"]
    effective_nf_core_result = host_tools["nf_core"]

    if host.get("os") == "Windows":
        wsl_status = wsl.inspect_wsl(process)
        support["wsl"] = wsl_status
        default_v2 = any(item.get("default") and item.get("version") == 2 for item in wsl_status.get("distributions", []))
        wsl_status["default_is_wsl2"] = default_v2
        findings.append(_finding("WSL2_UNAVAILABLE", PrerequisiteSeverity.HARD_BLOCKER, not default_v2, "A default WSL2 distribution is required."))

        nvidia_probe = wsl.probe_nvidia(process)
        wsl_gpus, wsl_driver, wsl_nvidia_status = parse_nvidia_smi(nvidia_probe.result)
        if nvidia_probe.result.ok:
            gpus, driver = wsl_gpus, wsl_driver
        nvidia_status = replace(
            wsl_nvidia_status,
            reason_code=nvidia_probe.reason_code or wsl_nvidia_status.reason_code,
            detail=f"{wsl_nvidia_status.detail}; executed path: {nvidia_probe.executed_path or 'none'}",
        )
        wsl_status["nvidia"] = {
            "executed_path": nvidia_probe.executed_path,
            "path_exported": nvidia_probe.path_exported,
            "reason_code": nvidia_probe.reason_code,
            "recommended_path": nvidia_probe.recommended_path,
            "attempts": [_detail(result) for result in nvidia_probe.attempts],
        }
        findings.append(_finding("WSL_GPU_UNAVAILABLE", PrerequisiteSeverity.HARD_BLOCKER, not bool(nvidia_status.available), nvidia_status.detail))
        findings.append(_finding("NVIDIA_SMI_PATH_NOT_EXPORTED", PrerequisiteSeverity.WARNING, nvidia_probe.reason_code == "NVIDIA_SMI_PATH_NOT_EXPORTED", "Add /usr/lib/wsl/lib to PATH; do not install a Linux NVIDIA driver in WSL."))

        docker_probe = wsl.probe_docker_integration(process)
        version_payload = _json_object(docker_probe.version)
        info_payload = _json_object(docker_probe.info)
        server = dict((version_payload or {}).get("Server") or {})
        engine_os = str((info_payload or {}).get("OSType") or server.get("Os") or "").lower()
        context = docker_probe.context.stdout.strip() if docker_probe.context.ok else ""
        integration_available = bool(docker_probe.version.ok and docker_probe.info.ok and docker_probe.context.ok and server and engine_os == "linux")
        wsl_status["docker"] = {
            "available": integration_available, "engine_os": engine_os or None, "context": context or None,
            "server_section_present": bool(server), "version": _detail(docker_probe.version),
            "info": _detail(docker_probe.info), "context_probe": _detail(docker_probe.context),
        }
        findings.append(_finding("DOCKER_WSL_INTEGRATION_UNAVAILABLE", PrerequisiteSeverity.HARD_BLOCKER, not integration_available, "WSL docker version/info/context must expose a Linux server."))
        gpu_visible = integration_available and bool(docker_gpu.available) and "nvidia" in docker_probe.info.stdout.lower()
        docker_gpu_access = ProbeStatus(gpu_visible, "available" if gpu_visible else "unavailable", "WSL Docker exposes NVIDIA capability" if gpu_visible else "WSL Docker GPU access was not detected", docker_probe.info.stderr.strip(), None if gpu_visible else "DOCKER_GPU_ACCESS_UNAVAILABLE")
        findings.append(_finding("DOCKER_GPU_ACCESS_UNAVAILABLE", PrerequisiteSeverity.HARD_BLOCKER, not gpu_visible, docker_gpu_access.detail))

        effective_java_result = wsl.run_in_wsl(process, ["java", "-version"])
        effective_nextflow_result, nextflow_path_result = wsl.probe_nextflow(
            process, version=QUALIFIED_NEXTFLOW_VERSION,
        )
        support["wsl_nextflow_path"] = _detail(nextflow_path_result)
        effective_nf_core_result = wsl.run_in_wsl(process, ["nf-core", "--version"])
        resource_probe = wsl.probe_resources(process, wsl_work_root)
        cpu_threads = int(resource_probe.cpu.stdout.strip()) if resource_probe.cpu.ok and resource_probe.cpu.stdout.strip().isdigit() else None
        total_ram, available_ram = _parse_meminfo(resource_probe.meminfo)
        root_free = _parse_df_free(resource_probe.root_disk)
        work_free = _parse_df_free(resource_probe.work_disk)
        wsl_status["resources"] = {
            "logical_cpu_count": cpu_threads, "total_ram_bytes": total_ram,
            "available_ram_bytes": available_ram, "root_free_bytes": root_free,
            "work_root": wsl_work_root, "work_root_free_bytes": work_free,
            "probes": {
                "cpu": _detail(resource_probe.cpu), "meminfo": _detail(resource_probe.meminfo),
                "root_disk": _detail(resource_probe.root_disk), "work_disk": _detail(resource_probe.work_disk),
            },
        }
        findings.append(_finding("WSL_CPU_THREADS_BELOW_CANDIDATE", PrerequisiteSeverity.WARNING, cpu_threads is None or cpu_threads < MINIMUM_WSL_CPU_THREADS, f"WSL logical CPU count is {cpu_threads}; candidate threshold is {MINIMUM_WSL_CPU_THREADS}."))
        findings.append(_finding("PARABRICKS_HOST_MEMORY_BELOW_RECOMMENDED", PrerequisiteSeverity.WARNING, total_ram is None or total_ram < RECOMMENDED_PARABRICKS_HOST_RAM_BYTES, f"WSL total RAM is {total_ram}; recommendation is {RECOMMENDED_PARABRICKS_HOST_RAM_BYTES} bytes."))
        findings.append(_finding("WSL_WORK_ROOT_SCRATCH_INSUFFICIENT", PrerequisiteSeverity.HARD_BLOCKER, work_free is None or work_free < MINIMUM_WORK_ROOT_FREE_BYTES, f"WSL work-root free space is {work_free}; minimum candidate gate is {MINIMUM_WORK_ROOT_FREE_BYTES} bytes."))
        support["wsl_resources"] = wsl_status["resources"]
    else:
        findings.append(_finding("GPU_UNAVAILABLE", PrerequisiteSeverity.HARD_BLOCKER, not bool(nvidia_status.available), nvidia_status.detail))
        findings.append(_finding("DOCKER_GPU_ACCESS_UNAVAILABLE", PrerequisiteSeverity.HARD_BLOCKER, not bool(docker_gpu.available), docker_gpu.detail))
        cpu_threads = (host.get("cpu") or {}).get("logical_count")
        findings.append(_finding("CPU_THREADS_BELOW_CANDIDATE", PrerequisiteSeverity.WARNING, cpu_threads is None or cpu_threads < MINIMUM_WSL_CPU_THREADS, f"Logical CPU count is {cpu_threads}; candidate threshold is {MINIMUM_WSL_CPU_THREADS}."))
        total_ram = host.get("host_ram_bytes")
        findings.append(_finding("PARABRICKS_HOST_MEMORY_BELOW_RECOMMENDED", PrerequisiteSeverity.WARNING, total_ram is None or total_ram < RECOMMENDED_PARABRICKS_HOST_RAM_BYTES, f"Host RAM is {total_ram}; recommendation is {RECOMMENDED_PARABRICKS_HOST_RAM_BYTES} bytes."))
        free_disk = (host.get("disk") or {}).get("free_bytes")
        findings.append(_finding("WORK_ROOT_SCRATCH_INSUFFICIENT", PrerequisiteSeverity.HARD_BLOCKER, free_disk is None or free_disk < MINIMUM_WORK_ROOT_FREE_BYTES, f"Current filesystem free space is {free_disk}; minimum candidate gate is {MINIMUM_WORK_ROOT_FREE_BYTES} bytes."))

    support["effective_java"] = _detail(effective_java_result)
    support["effective_nextflow"] = _detail(effective_nextflow_result)
    support["effective_nf_core"] = _detail(effective_nf_core_result)
    java_status, java_assessment = _java_probe(effective_java_result)
    nextflow_status, nextflow_assessment = _nextflow_probe(effective_nextflow_result)
    nf_core_status = _probe(effective_nf_core_result, "nf-core")
    findings.extend(_version_findings(java_assessment, nextflow_assessment))
    findings.append(_finding("NF_CORE_CLI_UNAVAILABLE", PrerequisiteSeverity.OPTIONAL, not bool(nf_core_status.available), "nf-core CLI is optional; Nextflow can launch the pinned pipeline directly."))

    hard_blocked = any(item.active and item.severity is PrerequisiteSeverity.HARD_BLOCKER for item in findings)
    if hard_blocked:
        qualification = QualificationStatus.BLOCKED
    elif any(gpu.total_vram_bytes < LOW_MEMORY_THRESHOLD_BYTES for gpu in gpus):
        qualification = QualificationStatus.PREFLIGHT_READY_LOW_MEMORY_CANDIDATE
    else:
        qualification = QualificationStatus.PREFLIGHT_READY

    return HardwareReport(
        os=str(host.get("os", "Unknown")), execution_context=str(host.get("execution_context", "unknown")),
        wsl_status=wsl_status, cpu=dict(host.get("cpu") or {}), host_ram_bytes=host.get("host_ram_bytes"),
        disk=dict(host.get("disk") or {}), nvidia_gpus=gpus, driver_version=driver,
        nvidia_smi=nvidia_status, docker=docker_status, docker_gpu_runtime=docker_gpu,
        docker_gpu_access=docker_gpu_access, java=java_status, nextflow=nextflow_status,
        nf_core=nf_core_status, parabricks_image=parabricks, cuda_test_image=cuda_image,
        minimum_nextflow_version=MINIMUM_NEXTFLOW_VERSION,
        qualified_nextflow_version=QUALIFIED_NEXTFLOW_VERSION,
        detected_nextflow_version=nextflow_assessment.version,
        nextflow_version_status=nextflow_assessment.status,
        prerequisites=tuple(findings), qualification_status=qualification,
        python=dict(host.get("python") or {}), support_details=support,
    )


def human_summary(report: HardwareReport) -> str:
    active = [finding for finding in report.prerequisites if finding.active]
    lines = [
        f"Qualification: {report.qualification_status.value}",
        f"OS/context: {report.os} / {report.execution_context}",
        f"NVIDIA GPUs: {len(report.nvidia_gpus)}",
        f"Docker daemon: {report.docker.status}",
        f"Docker GPU access: {report.docker_gpu_access.status}",
        f"Java: {report.java.status} ({report.java.detected_version or 'not detected'})",
        f"Nextflow: {report.nextflow_version_status.value} ({report.detected_nextflow_version or 'not detected'})",
        f"nf-core CLI: {report.nf_core.status} (optional)",
        f"Parabricks image: {report.parabricks_image.status}",
        "Active prerequisites:",
        *[f"- [{item.severity.value}] {item.code}: {item.detail}" for item in active],
        "Scientific qualification: NOT_TESTED",
    ]
    return "\n".join(lines)


def report_json(report: HardwareReport) -> str:
    return json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
