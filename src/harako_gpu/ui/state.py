"""Centralized draft-only Streamlit session keys and refresh-safe initialization."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, MutableMapping


PROJECT = "project"
PROJECT_SLUG = "project_slug"
SAMPLES = "draft_samples"
REFERENCE = "reference_pack_id"
BAM_MODE = "bam_output_mode"
ALIGNMENT_PROFILE = "alignment_profile_id"
QUANT_MODE = "quantification_mode"
PRIMARY_PROFILE = "primary_profile_id"
RUN_DIR = "current_run_directory"
PAGE = "active_page"
LANGUAGE = "language"
LAST_STATUS = "last_valid_status"
STATUS_STALE = "status_stale"
OUTPUT_ROOT = "output_root"
WORK_ROOT = "work_root"
RUNTIME_ROOT = "runtime_root"
LIBRARY_TYPE = "library_type"
FASTQ_DIRECTORY = "fastq_directory"
READ_LAYOUT = "read_layout"
SAMPLES_VALID = "samples_valid"
CAPABILITY_RESULT = "capability_result"
LAUNCH_ELIGIBILITY = "scientific_launch_eligibility"
EXECUTION_CONTEXT = "execution_context"
HOST_PROFILE_ID = "host_profile_id"
WORKFLOW_BACKEND = "workflow_backend"
PLAN_PATH = "reviewed_plan_path"
PLAN_REVIEW = "plan_review_confirmed"
AUTO_REFRESH = "auto_refresh"
REFRESH_INTERVAL = "refresh_interval_seconds"

DEFAULTS: dict[str, Any] = {
    PROJECT: "",
    PROJECT_SLUG: "",
    SAMPLES: [],
    REFERENCE: "human_grch38p14_gencode49_harako_gpu_v1",
    BAM_MODE: "none",
    ALIGNMENT_PROFILE: "none",
    QUANT_MODE: "recommended_only",
    PRIMARY_PROFILE: "salmon_2_5_1_deterministic",
    RUN_DIR: "",
    PAGE: "Project",
    LANGUAGE: "en",
    LAST_STATUS: None,
    STATUS_STALE: False,
    OUTPUT_ROOT: "",
    WORK_ROOT: "",
    RUNTIME_ROOT: "",
    LIBRARY_TYPE: "U",
    FASTQ_DIRECTORY: "",
    READ_LAYOUT: "paired",
    SAMPLES_VALID: False,
    CAPABILITY_RESULT: None,
    LAUNCH_ELIGIBILITY: None,
    EXECUTION_CONTEXT: "wsl2:Ubuntu",
    HOST_PROFILE_ID: "windows_wsl2_rtx3090_ram64_v1",
    WORKFLOW_BACKEND: "nfcore_rnaseq_3_26_reference",
    PLAN_PATH: "",
    PLAN_REVIEW: False,
    AUTO_REFRESH: True,
    REFRESH_INTERVAL: 2,
}


def initialize(state: MutableMapping[str, Any], *, persisted_run_dir: str = "",
               environment: Mapping[str, str] | None = None) -> None:
    existing_keys = set(state)
    for key, value in DEFAULTS.items():
        if key not in state:
            state[key] = deepcopy(value)
    if persisted_run_dir:
        state[RUN_DIR] = persisted_run_dir
    if environment:
        for key, value in (
            (EXECUTION_CONTEXT, environment.get("execution_context")),
            (HOST_PROFILE_ID, environment.get("host_profile_id")),
            (WORKFLOW_BACKEND, environment.get("workflow_backend")),
        ):
            if value and key not in existing_keys:
                state[key] = value


def invalidate_scientific_selection(state: MutableMapping[str, Any]) -> None:
    state[CAPABILITY_RESULT] = None
    state[LAUNCH_ELIGIBILITY] = None
    state[PLAN_PATH] = ""
    state[PLAN_REVIEW] = False


def preserve_across_pages(state: MutableMapping[str, Any]) -> None:
    """Interrupt Streamlit's widget cleanup for centralized cross-page draft keys."""
    for key in DEFAULTS:
        if key in state:
            state[key] = state[key]


def draft_snapshot(state: MutableMapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(state.get(key)) for key in (
        PROJECT, PROJECT_SLUG, SAMPLES, REFERENCE, BAM_MODE, ALIGNMENT_PROFILE,
        QUANT_MODE, PRIMARY_PROFILE, OUTPUT_ROOT, WORK_ROOT, RUNTIME_ROOT, LIBRARY_TYPE,
        FASTQ_DIRECTORY, READ_LAYOUT, EXECUTION_CONTEXT, HOST_PROFILE_ID, WORKFLOW_BACKEND,
    )}
