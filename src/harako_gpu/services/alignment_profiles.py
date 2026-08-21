"""Fixed Parabricks alignment profiles and workstation qualification gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Mapping


ONE_PASS_PROFILE_ID = "parabricks_star_one_pass_workstation"
TWO_PASS_PROFILE_ID = "parabricks_star_two_pass_high_memory"
ALIGNMENT_PROFILE_CATALOG_VERSION = "harako-alignment-profiles-v1"
PARABRICKS_IMAGE_IDENTITY = "sha256:d0761eb4b9921bc046c53520287316d545eb79feaeb8f22387e9bb5734650447"
REFERENCE_PACK_ID = "human_grch38p14_gencode49_harako_gpu_v1"
STAR_INDEX_ID = "star-2.7.2a-c15a9d6fe6df9716"


ONE_PASS_LIMITATION_JA = (
    "このprofileは、既知annotationを利用するone-pass alignmentです。"
    "BAM作成、GeneCounts、既知遺伝子発現解析を主目的とします。"
    "two-pass profileと比べ、未知または低発現のnovel splice junctionを"
    "またぐreadの検出感度が低下する可能性があります。"
)
ONE_PASS_LIMITATION_EN = (
    "This profile uses annotation-backed one-pass alignment. It is intended for BAM generation, "
    "GeneCounts, and known-gene expression analysis. Sensitivity for reads spanning novel or "
    "low-abundance splice junctions may be lower than with the high-memory two-pass profile."
)


@dataclass(frozen=True)
class AlignmentProfile:
    profile_id: str
    display_name_ja: str
    display_name_en: str
    backend: str
    version: str
    mode: str
    two_pass: bool
    annotation_backed: bool
    low_memory: bool
    mark_duplicates: bool
    quant_modes: tuple[str, ...]
    image_identity: str
    index_id: str
    reference_pack_id: str
    resource_class: str
    host_qualification_status: str
    product_status: str
    limitations: tuple[str, ...]
    qualification_report_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


_PROFILES = {
    ONE_PASS_PROFILE_ID: AlignmentProfile(
        ONE_PASS_PROFILE_ID,
        "ワークステーション向けone-pass",
        "Workstation one-pass",
        "Parabricks STAR",
        "4.6.0-1",
        "one_pass",
        False,
        True,
        True,
        False,
        ("TranscriptomeSAM", "GeneCounts"),
        PARABRICKS_IMAGE_IDENTITY,
        STAR_INDEX_ID,
        REFERENCE_PACK_ID,
        "host_overlay_required",
        "evaluated_by_host_capability_matrix",
        "capability_matrix_required",
        (
            ONE_PASS_LIMITATION_EN,
            "not equivalent to high-memory two-pass",
            "not for novel-splice-discovery-first studies",
            "host-specific full-size qualification is evaluated separately",
            "research use only; non-diagnostic; non-clinical",
        ),
        ("parabricks-one-pass-workstation-profile",),
    ),
    TWO_PASS_PROFILE_ID: AlignmentProfile(
        TWO_PASS_PROFILE_ID,
        "高メモリ向けtwo-pass",
        "High-memory two-pass",
        "Parabricks STAR",
        "4.6.0-1",
        "two_pass",
        True,
        True,
        True,
        False,
        ("TranscriptomeSAM", "GeneCounts"),
        PARABRICKS_IMAGE_IDENTITY,
        STAR_INDEX_ID,
        REFERENCE_PACK_ID,
        "host_overlay_required",
        "evaluated_by_host_capability_matrix",
        "capability_matrix_required",
        (
            "host-specific resource qualification is mandatory",
            "no dynamic memory escalation",
            "research use only; non-diagnostic; non-clinical",
        ),
        ("medium-human-capacity-resource-envelope",),
    ),
}


def alignment_profiles() -> tuple[AlignmentProfile, ...]:
    return (_PROFILES[ONE_PASS_PROFILE_ID], _PROFILES[TWO_PASS_PROFILE_ID])


def get_alignment_profile(profile_id: str) -> AlignmentProfile:
    try:
        return _PROFILES[profile_id]
    except KeyError as exc:
        raise ValueError(f"Unknown alignment profile: {profile_id}") from exc


def validate_alignment_profile_selection(
    profile_id: str, *, allow_qualification_candidate: bool = False,
    reject_current_host_two_pass: bool = True,
) -> AlignmentProfile:
    # Kept as a compatibility entry point. Host availability belongs to the
    # reference-aware capability matrix, not the scientific profile catalog.
    return get_alignment_profile(profile_id)


def fixed_parabricks_extra_args(
    profile_id: str, *, sjdb_overhang: int = 74, qualification_debug_x3: bool = False,
) -> str:
    profile = get_alignment_profile(profile_id)
    if sjdb_overhang not in {74, 100}:
        raise ValueError("STAR index sjdbOverhang must be an explicitly qualified index value")
    pieces = ["--low-memory"]
    if qualification_debug_x3:
        pieces.append("--x3")
    pieces.extend((
        "--quantMode", "TranscriptomeSAM", "GeneCounts",
        "--sjdb-overhang", str(sjdb_overhang),
        "--two-pass-mode", "Basic" if profile.two_pass else "None",
    ))
    return " ".join(pieces)


def scientific_parameter_diff() -> dict[str, Mapping[str, str]]:
    return {
        "--two-pass-mode": {TWO_PASS_PROFILE_ID: "Basic", ONE_PASS_PROFILE_ID: "None"},
    }


class WorkstationResourceClass(StrEnum):
    COMFORTABLE = "COMFORTABLE"
    CONSTRAINED = "CONSTRAINED"
    UNSAFE = "UNSAFE"
    RESOURCE_FAILED = "RESOURCE_FAILED"
    NOT_RUN_SAFETY_GATE = "NOT_RUN_SAFETY_GATE"


@dataclass(frozen=True)
class OnePassResourceObservation:
    terminal_success: bool
    required_artifacts_valid: bool
    peak_ram_bytes: int
    total_ram_bytes: int
    minimum_available_ram_bytes: int
    peak_swap_used_bytes: int
    peak_vram_mib: float
    total_vram_mib: float
    disk_reserve_maintained: bool
    sigkill_or_oom: bool = False
    docker_instability: bool = False


def classify_one_pass_resources(value: OnePassResourceObservation) -> WorkstationResourceClass:
    ram_fraction = value.peak_ram_bytes / value.total_ram_bytes
    vram_fraction = value.peak_vram_mib / value.total_vram_mib
    unsafe = (
        ram_fraction >= 0.90
        or value.minimum_available_ram_bytes < 4 * 1024**3
        or value.peak_swap_used_bytes >= 4 * 1024**3
        or vram_fraction >= 0.95
        or not value.disk_reserve_maintained
        or value.sigkill_or_oom
        or value.docker_instability
    )
    if not value.terminal_success:
        return WorkstationResourceClass.RESOURCE_FAILED if unsafe else WorkstationResourceClass.UNSAFE
    if not value.required_artifacts_valid or unsafe:
        return WorkstationResourceClass.UNSAFE
    constrained = (
        ram_fraction >= 0.80
        or value.minimum_available_ram_bytes < 8 * 1024**3
        or value.peak_swap_used_bytes >= 1024**3
        or vram_fraction >= 0.90
    )
    return WorkstationResourceClass.CONSTRAINED if constrained else WorkstationResourceClass.COMFORTABLE


def may_progress_from(level: str, classification: WorkstationResourceClass, value: OnePassResourceObservation) -> bool:
    if classification is not WorkstationResourceClass.COMFORTABLE:
        return False
    if level == "C3_10M":
        return (
            value.peak_ram_bytes / value.total_ram_bytes < 0.75
            and value.minimum_available_ram_bytes >= 10 * 1024**3
            and value.peak_swap_used_bytes < 1024**3
            and value.peak_vram_mib / value.total_vram_mib < 0.90
        )
    return level in {"C1_1M", "C2_5M"}
