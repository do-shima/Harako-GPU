"""Translate UI draft values into the existing application-service contract."""

from __future__ import annotations

from typing import Any, Mapping

from harako_gpu.services.gui import GuiDraft
from harako_gpu.ui import state as keys


def from_state(state: Mapping[str, Any]) -> GuiDraft:
    return GuiDraft(
        project_slug=str(state.get(keys.PROJECT_SLUG) or ""),
        samples=tuple(dict(row) for row in (state.get(keys.SAMPLES) or [])),
        reference_pack_id=str(state.get(keys.REFERENCE) or ""),
        bam_output_mode=str(state.get(keys.BAM_MODE) or "none"),
        alignment_profile_id=str(state.get(keys.ALIGNMENT_PROFILE) or "none"),
        quantification_mode=str(state.get(keys.QUANT_MODE) or "recommended_only"),
        primary_profile_id=str(state.get(keys.PRIMARY_PROFILE) or "salmon_2_5_1_deterministic"),
        explicit_library_type=str(state.get(keys.LIBRARY_TYPE) or ""),
        runtime_root=str(state.get(keys.RUNTIME_ROOT) or ""),
        output_root=str(state.get(keys.OUTPUT_ROOT) or ""),
        work_root=str(state.get(keys.WORK_ROOT) or ""),
        execution_context=str(state.get(keys.EXECUTION_CONTEXT) or "wsl2:Ubuntu"),
        host_profile_id=str(state.get(keys.HOST_PROFILE_ID) or "windows_wsl2_rtx3090_ram64_v1"),
        workflow_backend=str(state.get(keys.WORKFLOW_BACKEND) or "nfcore_rnaseq_3_26_reference"),
    )
