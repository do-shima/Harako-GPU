"""Pure parsing and policy assessment for external runtime versions."""

from __future__ import annotations

import re
from dataclasses import dataclass

from harako_gpu.adapters.process import CommandResult
from harako_gpu.core.contracts import (
    JavaVersionStatus,
    MINIMUM_JAVA_MAJOR,
    MINIMUM_NEXTFLOW_VERSION,
    NextflowVersionStatus,
    QUALIFIED_NEXTFLOW_VERSION,
)


@dataclass(frozen=True)
class JavaAssessment:
    major: int | None
    version: str | None
    status: JavaVersionStatus


@dataclass(frozen=True)
class NextflowAssessment:
    version: str | None
    status: NextflowVersionStatus


JAVA_PATTERNS = (
    re.compile(r"(?i)\b(?:openjdk|java)\s+version\s+[\"'](?P<version>[^\"']+)[\"']"),
    re.compile(r"(?i)\b(?:openjdk|java)\s+(?P<version>(?:1\.)?\d+(?:[._+\-][0-9A-Za-z]+)*)"),
)
NEXTFLOW_PATTERN = re.compile(r"(?i)\b(?:nextflow(?:\s+version)?\s*)?v?(?P<version>\d{2}\.\d{2}\.\d+)\b")


def parse_java_version(output: str) -> tuple[str, int] | None:
    for pattern in JAVA_PATTERNS:
        match = pattern.search(output)
        if not match:
            continue
        version = match.group("version")
        first = int(version.split(".", 1)[0])
        major = int(version.split(".", 2)[1]) if first == 1 and version.startswith("1.") else first
        return version, major
    return None


def assess_java(result: CommandResult) -> JavaAssessment:
    if result.returncode is None or result.exception:
        return JavaAssessment(None, None, JavaVersionStatus.JAVA_NOT_FOUND)
    output = "\n".join((result.stdout, result.stderr))
    parsed = parse_java_version(output)
    if parsed is None:
        if result.returncode != 0 and _looks_not_found(output):
            return JavaAssessment(None, None, JavaVersionStatus.JAVA_NOT_FOUND)
        return JavaAssessment(None, None, JavaVersionStatus.JAVA_VERSION_MALFORMED)
    version, major = parsed
    status = JavaVersionStatus.VERSION_GATE_PASS if major >= MINIMUM_JAVA_MAJOR else JavaVersionStatus.JAVA_VERSION_UNSUPPORTED
    return JavaAssessment(major, version, status)


def parse_nextflow_version(output: str) -> str | None:
    match = NEXTFLOW_PATTERN.search(output)
    return match.group("version") if match else None


def version_tuple(version: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        raise ValueError(f"Malformed semantic version: {version}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def assess_nextflow(result: CommandResult) -> NextflowAssessment:
    if result.returncode is None or result.exception:
        return NextflowAssessment(None, NextflowVersionStatus.NEXTFLOW_NOT_FOUND)
    output = "\n".join((result.stdout, result.stderr))
    version = parse_nextflow_version(output)
    if version is None:
        if result.returncode != 0 and _looks_not_found(output):
            return NextflowAssessment(None, NextflowVersionStatus.NEXTFLOW_NOT_FOUND)
        return NextflowAssessment(None, NextflowVersionStatus.NEXTFLOW_VERSION_MALFORMED)
    if version_tuple(version) < version_tuple(MINIMUM_NEXTFLOW_VERSION):
        return NextflowAssessment(version, NextflowVersionStatus.NEXTFLOW_VERSION_UNSUPPORTED)
    if version == QUALIFIED_NEXTFLOW_VERSION:
        return NextflowAssessment(version, NextflowVersionStatus.QUALIFIED_VERSION_MATCH)
    return NextflowAssessment(version, NextflowVersionStatus.VERSION_SUPPORTED_BUT_NOT_YET_QUALIFIED)


def _looks_not_found(output: str) -> bool:
    lowered = output.lower()
    return any(marker in lowered for marker in ("not found", "no such file", "execvpe", "command not found"))
