from __future__ import annotations

import pytest

from harako_gpu.adapters.process import CommandResult
from harako_gpu.core.contracts import JavaVersionStatus, NextflowVersionStatus
from harako_gpu.services.runtime_versions import assess_java, assess_nextflow


def command(output="", *, stderr="", code=0, exception=""):
    return CommandResult(("tool", "--version"), code, output, stderr, exception=exception)


@pytest.mark.parametrize(
    ("output", "major", "status"),
    [
        ('java version "1.8.0_402"', 8, JavaVersionStatus.JAVA_VERSION_UNSUPPORTED),
        ('openjdk version "11.0.31" 2026-04-21', 11, JavaVersionStatus.JAVA_VERSION_UNSUPPORTED),
        ('openjdk version "17.0.12" 2024-07-16', 17, JavaVersionStatus.VERSION_GATE_PASS),
        ('openjdk 21.0.2 2024-01-16', 21, JavaVersionStatus.VERSION_GATE_PASS),
    ],
)
def test_java_major_version_gate(output, major, status) -> None:
    assessment = assess_java(command(stderr=output))
    assert assessment.major == major
    assert assessment.status is status


def test_java_malformed_and_unavailable() -> None:
    assert assess_java(command("unexpected output")).status is JavaVersionStatus.JAVA_VERSION_MALFORMED
    assert assess_java(command(code=None, exception="FileNotFoundError")).status is JavaVersionStatus.JAVA_NOT_FOUND
    assert assess_java(command(stderr="execvpe(java) failed: No such file", code=1)).status is JavaVersionStatus.JAVA_NOT_FOUND


@pytest.mark.parametrize(
    ("version", "status"),
    [
        ("25.04.2", NextflowVersionStatus.NEXTFLOW_VERSION_UNSUPPORTED),
        ("25.04.3", NextflowVersionStatus.QUALIFIED_VERSION_MATCH),
        ("25.04.8", NextflowVersionStatus.VERSION_SUPPORTED_BUT_NOT_YET_QUALIFIED),
        ("26.04.6", NextflowVersionStatus.VERSION_SUPPORTED_BUT_NOT_YET_QUALIFIED),
    ],
)
def test_nextflow_version_policy(version, status) -> None:
    assessment = assess_nextflow(command(f"nextflow version {version} build 9999"))
    assert assessment.version == version
    assert assessment.status is status


def test_nextflow_malformed_and_unavailable() -> None:
    assert assess_nextflow(command("Nextflow unknown")).status is NextflowVersionStatus.NEXTFLOW_VERSION_MALFORMED
    assert assess_nextflow(command(code=None, exception="FileNotFoundError")).status is NextflowVersionStatus.NEXTFLOW_NOT_FOUND
    assert assess_nextflow(command(stderr="execvpe(nextflow) failed: No such file", code=1)).status is NextflowVersionStatus.NEXTFLOW_NOT_FOUND
