"""Explicit fail-closed provisioning for the fixed Ubuntu host qualification."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import tempfile
from typing import Any, Mapping

from harako_gpu.adapters.filesystem import sha256_path
from harako_gpu.adapters.process import ProcessRunner
from harako_gpu.services.host_profiles import (
    ARCHIVE_RECEIPT_SHA256,
    FULL_HUMAN_REFERENCE_PACK_ID,
    FULL_HUMAN_TASK_IMAGES,
    ONE_PASS_REPORT_ID,
    ONE_PASS_REPORT_SHA256,
    ONE_PASS_RESOURCE_CONTRACT_ID,
    PARABRICKS_AMD64_MANIFEST_DIGEST,
    PARABRICKS_CONFIG_IMAGE_ID,
    PARABRICKS_MANIFEST_LIST_DIGEST,
    PARABRICKS_SOURCE_REFERENCE,
    PLUGIN_CLOSURE_ID,
    QUALIFICATION_REPOSITORY_COMMIT,
    QUALIFICATION_REPOSITORY_TREE,
    SALMON_251_INDEX_ID,
    STAR_INDEX_ID,
    TASK_IMAGE_CLOSURE_EVIDENCE_SHA256,
    TASK_IMAGE_CLOSURE_ID,
    TWO_PASS_REPORT_ID,
    TWO_PASS_REPORT_SHA256,
    TWO_PASS_RESOURCE_CONTRACT_ID,
    UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
    HostQualificationReceipt,
    OfflinePlatformImageProvenance,
    PluginClosureReceipt,
    validate_task_image_closure,
)


BUNDLE_ID = "ubuntu-high-memory-host-capability-v1"
BUNDLE_EVIDENCE_SHA256 = "d13224114bdd9990bb4d299a654982380fcb85c253e95ee99120447be758f324"
BUNDLE_SOURCE_MAP_SHA256 = "0dbece6a8896d271fabeac9f6dfa61371b80b137d1b36a9d74ae0db90b01ff02"
BUNDLE_MANIFEST_SHA256 = "2775b48d226c107c99c29f6257431b132c05a480ede52ef61b3d73d8eb99afc9"
PLUGIN_INVENTORY_SHA256 = "629fcd902958e2cb42a36ca77d083f4860800a984d67aa3f9f72e5f4fa93cd35"
PLUGIN_MANIFEST_SHA256 = "78285a59f38118ecaa3b875620f01c1f1712c97a834e17cb603f6c5e64f8d2e6"
PARABRICKS_ARCHIVE_NAME = "parabricks-4.6.0-1.tar"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _bundle_checksums(root: Path) -> dict[str, str]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Evidence bundle root is missing or unsafe")
    for path in root.rglob("*"):
        mode = path.lstat().st_mode
        if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise ValueError(f"Evidence bundle contains an unsafe entry: {path}")
    checksums: dict[str, str] = {}
    for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        try:
            digest, relative = line.split("  ", 1)
        except ValueError as exc:
            raise ValueError("Malformed evidence bundle SHA256SUMS") from exc
        pure = PurePosixPath(relative)
        if (not _SHA256.fullmatch(digest) or pure.is_absolute() or ".." in pure.parts
                or relative in checksums):
            raise ValueError("Unsafe evidence bundle SHA256SUMS entry")
        checksums[relative] = digest
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if len(checksums) != 40 or actual != set(checksums) | {"SHA256SUMS"}:
        raise ValueError("Evidence bundle fileset is not the fixed 40-entry payload")
    for relative, expected in checksums.items():
        if sha256_path(root / relative) != expected:
            raise ValueError(f"Evidence bundle identity mismatch: {relative}")
    return checksums


def _leaf_pointers(value: Any, pointer: str = "") -> set[str]:
    if isinstance(value, dict):
        result: set[str] = set()
        for key, item in value.items():
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            result |= _leaf_pointers(item, f"{pointer}/{escaped}")
        return result
    if isinstance(value, list):
        result = set()
        for index, item in enumerate(value):
            result |= _leaf_pointers(item, f"{pointer}/{index}")
        return result
    return {pointer}


def _validate_bundle(root: Path, repository_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    checksums = _bundle_checksums(root)
    fixed = {
        "host-capability-evidence.json": BUNDLE_EVIDENCE_SHA256,
        "evidence-source-map.json": BUNDLE_SOURCE_MAP_SHA256,
        "bundle-manifest.json": BUNDLE_MANIFEST_SHA256,
    }
    if any(checksums.get(name) != digest for name, digest in fixed.items()):
        raise ValueError("Normalized evidence bundle fixed identity mismatch")
    evidence = _json_object(root / "host-capability-evidence.json", "normalized host evidence")
    source_map = _json_object(root / "evidence-source-map.json", "evidence source map")
    mapped = {str(item.get("normalized_json_pointer")) for item in source_map.get("fields", ())}
    if (_leaf_pointers(evidence) != mapped
            or source_map.get("normalized_evidence_sha256") != BUNDLE_EVIDENCE_SHA256):
        raise ValueError("Evidence source map does not cover the normalized evidence")
    if (evidence.get("evidence_bundle_id") != BUNDLE_ID
            or evidence.get("host_profile_id") != UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID
            or evidence.get("repository_sha") != QUALIFICATION_REPOSITORY_COMMIT
            or evidence.get("repository_tree") != QUALIFICATION_REPOSITORY_TREE
            or evidence.get("reference_pack_id") != FULL_HUMAN_REFERENCE_PACK_ID
            or evidence.get("star_index_id") != STAR_INDEX_ID
            or evidence.get("salmon_index_id") != SALMON_251_INDEX_ID
            or evidence.get("pipeline_version") != "3.26.0"):
        raise ValueError("Normalized host qualification identity mismatch")
    if (dict(evidence.get("one_pass") or {}).get("terminal_classification")
            != "HARAKO_GPU_NATIVE_LINUX_FULL_SIZE_ONE_PASS_END_TO_END_FEASIBLE"
            or dict(evidence.get("two_pass") or {}).get("terminal_classification")
            != "HARAKO_GPU_NATIVE_LINUX_FULL_SIZE_TWO_PASS_END_TO_END_FEASIBLE"):
        raise ValueError("Normalized host qualification terminal evidence mismatch")
    if evidence.get("product_docker_provenance") != "PENDING":
        raise ValueError("Normalized evidence must retain the historical PENDING provenance state")
    receipt_hashes = set()
    for relative in ("f1/archive-receipt.json", "f2/archive-receipt.json"):
        receipt = _json_object(root / relative, relative)
        if (receipt.get("status") != "VERIFIED_COMPLETE"
                or receipt.get("archive", {}).get("member_audit_pass") is not True
                or receipt.get("archive", {}).get("tar_compare_exit_code") != 0):
            raise ValueError(f"Terminal archive receipt is not verified: {relative}")
        receipt_hashes.add(sha256_path(root / relative))
    if receipt_hashes != set(ARCHIVE_RECEIPT_SHA256):
        raise ValueError("Terminal archive receipt identities mismatch")
    reports = repository_root / "docs/qualification"
    expected_reports = {
        ONE_PASS_REPORT_ID: ONE_PASS_REPORT_SHA256,
        TWO_PASS_REPORT_ID: TWO_PASS_REPORT_SHA256,
    }
    for report_id, expected in expected_reports.items():
        if sha256_path(reports / f"{report_id}.json") != expected:
            raise ValueError(f"Qualification report missing or changed: {report_id}")
    return evidence, {"checksums": checksums, "archive_receipt_sha256": sorted(receipt_hashes)}


def _validate_host(runner: ProcessRunner) -> dict[str, Any]:
    if platform.system() != "Linux" or "microsoft" in platform.release().lower():
        raise ValueError("Ubuntu high-memory receipt requires native Linux")
    meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
    match = re.search(r"^MemTotal:\s+(\d+)\s+kB$", meminfo, re.MULTILINE)
    if match is None:
        raise ValueError("Cannot determine physical RAM")
    ram_bytes = int(match.group(1)) * 1024
    gpu = runner.run(("nvidia-smi", "--query-gpu=name,uuid,memory.total,driver_version",
                      "--format=csv,noheader,nounits"), timeout=15)
    if not gpu.ok:
        raise ValueError("Cannot validate NVIDIA GPU identity")
    rows = [row.strip() for row in gpu.stdout.splitlines() if row.strip()]
    if len(rows) != 1:
        raise ValueError("Exactly one qualified NVIDIA GPU is required")
    parts = [part.strip() for part in rows[0].split(",")]
    if len(parts) != 4 or parts[0] != "NVIDIA GeForce RTX 3090" or int(parts[2]) < 24_576:
        raise ValueError("Current GPU does not match the fixed Ubuntu host profile")
    if ram_bytes < 128_000_000_000:
        raise ValueError("Current RAM does not match the fixed Ubuntu host profile")
    return {"operating_system_family": "linux", "execution_context": "native_linux",
            "physical_ram_bytes": ram_bytes, "gpu_model": parts[0], "gpu_uuid": parts[1],
            "vram_mib": int(parts[2]), "driver_version": parts[3]}


def _validate_plugin(bundle_root: Path, plugin_dir: Path) -> PluginClosureReceipt:
    source = _json_object(bundle_root / "f2/plugin-receipt.json", "plugin evidence receipt")
    installed = dict(source.get("installed_tree") or {})
    plugin = dict(source.get("plugin") or {})
    nextflow = dict(source.get("nextflow") or {})
    probe = dict(source.get("offline_actual_pipeline_probe") or {})
    receipt = PluginClosureReceipt(
        1, str(plugin.get("name")), str(plugin.get("version")), str(nextflow.get("version")),
        str(installed.get("inventory_sha256")), str(installed.get("manifest_sha256")),
        str(probe.get("result")),
    )
    receipt.validate()
    cache = plugin_dir.expanduser().resolve()
    versions = sorted(path.name for path in cache.glob("nf-schema-*") if path.is_dir())
    manifest = cache / "nf-schema-2.5.1/classes/META-INF/MANIFEST.MF"
    if versions != ["nf-schema-2.5.1"] or sha256_path(manifest) != PLUGIN_MANIFEST_SHA256:
        raise ValueError("Installed nf-schema cache does not match the verified receipt")
    return receipt


def _inspect_image(runner: ProcessRunner, reference: str) -> Mapping[str, Any]:
    result = runner.run(("docker", "image", "inspect", reference), timeout=20)
    if not result.ok:
        raise ValueError(f"Required local image unavailable: {reference}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("Docker image inspection returned malformed JSON") from exc
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise ValueError("Docker image inspection must return one object")
    return value[0]


def _validate_images(bundle_root: Path, runner: ProcessRunner) -> dict[str, Mapping[str, Any]]:
    closure_path = bundle_root / "f2/image-closure.json"
    source = _json_object(closure_path, "task image closure evidence")
    if (sha256_path(closure_path) != TASK_IMAGE_CLOSURE_EVIDENCE_SHA256
            or source.get("closure_complete") is not True
            or source.get("expected_unique_references") != 18
            or source.get("resolved_count") != 18):
        raise ValueError("Task-image closure evidence mismatch")
    inspected = {item.contract.reference: _inspect_image(runner, item.contract.execution_reference)
                 for item in FULL_HUMAN_TASK_IMAGES}
    validate_task_image_closure(inspected)
    return inspected


def _find_handoff_archive(manifest: Mapping[str, Any], handoff_root: Path) -> tuple[Path, str]:
    matches = [dict(item) for item in manifest.get("docker_archives", ())
               if item.get("path") == f"payload/docker/{PARABRICKS_ARCHIVE_NAME}"]
    if len(matches) != 1 or not _SHA256.fullmatch(str(matches[0].get("sha256"))):
        raise ValueError("Handoff Parabricks archive identity is missing")
    path = handoff_root / str(matches[0]["path"])
    return path, str(matches[0]["sha256"])


def _validate_provenance(
    *, handoff_root: Path, execution_receipt_path: Path, runner: ProcessRunner,
) -> tuple[OfflinePlatformImageProvenance, str]:
    handoff = _json_object(handoff_root / "handoff-manifest.json", "handoff manifest")
    execution = _json_object(execution_receipt_path, "Parabricks execution receipt")
    archive_path, expected_archive = _find_handoff_archive(handoff, handoff_root)
    if sha256_path(archive_path) != expected_archive:
        raise ValueError("Parabricks offline archive SHA-256 mismatch")
    source_receipt_sha = sha256_path(execution_receipt_path)
    if (execution.get("handoff_id") != handoff.get("handoff_id")
            or execution.get("archive_sha256") != expected_archive
            or execution.get("source_multi_platform_descriptor") != PARABRICKS_MANIFEST_LIST_DIGEST
            or execution.get("source_linux_amd64_platform_descriptor") != PARABRICKS_AMD64_MANIFEST_DIGEST
            or execution.get("loaded_docker_id") != PARABRICKS_CONFIG_IMAGE_ID
            or execution.get("loaded_architecture") != "amd64"
            or execution.get("loaded_os") != "linux"
            or execution.get("execution_only_status") != "PASS_RUNTIME_PROBE"):
        raise ValueError("Parabricks offline execution evidence mismatch")
    probe = dict(execution.get("runtime_probe") or {})
    actions = dict(execution.get("actions") or {})
    if (probe.get("gpu_visible") is not True
            or probe.get("pbrun_rna_fq2bam_help_available") is not True
            or probe.get("pbrun_version") != "4.6.0-1"
            or any(actions.get(key) is not False for key in ("pull", "retag", "login", "automatic_terms_acceptance"))):
        raise ValueError("Parabricks version/executable or offline-action evidence mismatch")
    provenance = OfflinePlatformImageProvenance(
        1, PARABRICKS_SOURCE_REFERENCE, PARABRICKS_MANIFEST_LIST_DIGEST, "linux/amd64",
        PARABRICKS_AMD64_MANIFEST_DIGEST, PARABRICKS_CONFIG_IMAGE_ID, expected_archive,
        "pbrun 4.6.0-1", "PASS", source_receipt_sha,
    )
    provenance.validate(
        observed_image=_inspect_image(runner, PARABRICKS_SOURCE_REFERENCE),
        expected_receipt_sha256=source_receipt_sha,
        expected_archive_sha256=expected_archive,
    )
    return provenance, source_receipt_sha


def _write_receipts_atomically(root: Path, payloads: Mapping[str, Mapping[str, Any]], *, replace: bool) -> None:
    root.mkdir(parents=True, exist_ok=True)
    existing = [root / name for name in payloads if (root / name).exists()]
    if existing and not replace:
        raise ValueError("Installed receipt exists; explicit --replace is required")
    if replace:
        host_path = root / f"{UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID}.json"
        if host_path.exists():
            existing_host = HostQualificationReceipt.load(host_path)
            if existing_host.host_profile_id != UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID:
                raise ValueError("--replace cannot change the installed host profile")
    temporary: list[tuple[Path, Path]] = []
    try:
        for name, payload in payloads.items():
            destination = root / name
            descriptor, raw = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=root)
            temp = Path(raw)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.append((temp, destination))
        for temp, destination in temporary:
            os.replace(temp, destination)
        directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        for temp, _ in temporary:
            if temp.exists():
                temp.unlink()


def provision_ubuntu_high_memory_host(
    *, bundle_root: Path, runtime_root: Path, plugin_dir: Path, handoff_root: Path,
    parabricks_execution_receipt: Path, replace: bool = False,
    runner: ProcessRunner | None = None, repository_root: Path | None = None,
) -> dict[str, Any]:
    """Validate fixed external evidence and atomically install three product receipts."""
    process = runner or ProcessRunner()
    repository = (repository_root or Path(__file__).resolve().parents[3]).resolve()
    bundle = bundle_root.expanduser().resolve(strict=True)
    runtime = runtime_root.expanduser().resolve(strict=True)
    handoff = handoff_root.expanduser().resolve(strict=True)
    evidence, bundle_result = _validate_bundle(bundle, repository)
    host = _validate_host(process)
    plugin = _validate_plugin(bundle, plugin_dir)
    images = _validate_images(bundle, process)
    provenance, provenance_identity = _validate_provenance(
        handoff_root=handoff,
        execution_receipt_path=parabricks_execution_receipt.expanduser().resolve(strict=True),
        runner=process,
    )
    host_receipt = HostQualificationReceipt(
        schema_version=1,
        host_profile_id=UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
        evidence_version=BUNDLE_ID,
        qualification_report_sha256={
            ONE_PASS_REPORT_ID: ONE_PASS_REPORT_SHA256,
            TWO_PASS_REPORT_ID: TWO_PASS_REPORT_SHA256,
        },
        repository_commit=QUALIFICATION_REPOSITORY_COMMIT,
        repository_tree=QUALIFICATION_REPOSITORY_TREE,
        operating_system_family="linux",
        execution_context="native_linux",
        minimum_physical_ram_bytes=int(host["physical_ram_bytes"]),
        gpu_model=str(host["gpu_model"]),
        minimum_vram_mib=int(host["vram_mib"]),
        resource_contract_ids=(ONE_PASS_RESOURCE_CONTRACT_ID, TWO_PASS_RESOURCE_CONTRACT_ID),
        reference_pack_id=FULL_HUMAN_REFERENCE_PACK_ID,
        star_index_id=STAR_INDEX_ID,
        salmon_index_id=SALMON_251_INDEX_ID,
        pipeline_version="3.26.0",
        pipeline_commit=str(evidence["pipeline_commit"]),
        plugin_closure_id=PLUGIN_CLOSURE_ID,
        plugin_cache_inventory_sha256=PLUGIN_INVENTORY_SHA256,
        task_image_closure_id=TASK_IMAGE_CLOSURE_ID,
        task_image_closure_sha256=TASK_IMAGE_CLOSURE_EVIDENCE_SHA256,
        archive_receipt_sha256=tuple(bundle_result["archive_receipt_sha256"]),
        parabricks_archive_sha256=provenance.archive_sha256,
        parabricks_provenance_receipt_sha256=provenance_identity,
        product_docker_provenance_status="VERIFIED",
        created_at=datetime.now(UTC).isoformat(),
        product_cli_verified=False,
    )
    host_receipt.validate(report_root=repository / "docs/qualification")
    installed_root = runtime / "host-profiles"
    payloads = {
        f"{UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID}.json": asdict(host_receipt),
        f"{PLUGIN_CLOSURE_ID}.json": asdict(plugin),
        "parabricks-offline-linux-amd64-v1.json": asdict(provenance),
    }
    _write_receipts_atomically(installed_root, payloads, replace=replace)
    installed = {name: {"path": str(installed_root / name), "sha256": sha256_path(installed_root / name)}
                 for name in payloads}
    return {
        "schema_version": 1,
        "status": "INSTALLED_VERIFIED",
        "host_profile_id": UBUNTU_HIGH_MEMORY_HOST_PROFILE_ID,
        "bundle_id": BUNDLE_ID,
        "bundle_evidence_sha256": BUNDLE_EVIDENCE_SHA256,
        "host": host,
        "plugin": {"status": "PASS", "receipt": asdict(plugin)},
        "task_images": {"status": "PASS", "count": len(images),
                        "closure_sha256": TASK_IMAGE_CLOSURE_EVIDENCE_SHA256},
        "parabricks_provenance": {"status": "PASS", "receipt_identity": provenance_identity,
                                   "archive_sha256": provenance.archive_sha256,
                                   "config_image_id": provenance.config_image_id},
        "installed_receipts": installed,
        "contains_credentials": False,
        "contains_biological_data": False,
    }
