from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from harako_gpu.services.gui import create_gui_plan, prepare_gui_run
from harako_gpu.ui import state as keys
from harako_gpu.ui.draft import from_state
from harako_gpu.ui.errors import capture
from harako_gpu.ui.labels import text
from harako_gpu.ui.components.message import MessageLevel, render as message
from harako_gpu.ui.components.page_intro import render as page_intro


def render() -> None:
    language = st.session_state[keys.LANGUAGE]
    st.header(text("review", language))
    draft = from_state(st.session_state)
    capability = st.session_state.get(keys.CAPABILITY_RESULT) or {}
    available = capability.get("status") in {"AVAILABLE_QUALIFIED", "AVAILABLE_WITH_LIMITATION"}
    eligibility = st.session_state.get(keys.LAUNCH_ELIGIBILITY) or {}
    if draft.execution_context == "native_linux":
        assets = eligibility.get("asset_readiness") or {}
        eligibility_matches = (
            eligibility.get("execution_context") == draft.execution_context
            and eligibility.get("detected_host_profile_id") == draft.host_profile_id
            and eligibility.get("workflow_backend") == draft.workflow_backend
            and eligibility.get("alignment_profile_id") == draft.alignment_profile_id
            and assets.get("reference_pack_id") == draft.reference_pack_id
            and assets.get("quantification_mode") == draft.quantification_mode
            and assets.get("primary_profile_id") == draft.primary_profile_id
        )
        available = available and eligibility.get("allowed") is True and eligibility_matches
    page_intro(st, "review", language, blocker="" if available else text("blocker.route", language))
    summary = {
        "project": draft.project_slug, "samples": len(draft.samples),
        "execution_route": "fastq_quantification_only" if draft.bam_output_mode == "none" else "gpu_bam_alignment",
        "bam_output_mode": draft.bam_output_mode, "GPU_used": draft.bam_output_mode != "none",
        "reference_pack_id": draft.reference_pack_id, "library_type": draft.explicit_library_type,
        "primary_profile": draft.primary_profile_id, "quantification_mode": draft.quantification_mode,
        "workflow_backend": draft.workflow_backend,
        "alignment_profile": draft.alignment_profile_id,
        "resource_contract": eligibility.get("resource_contract_id"),
        "execution_context": draft.execution_context,
        "host_profile_id": draft.host_profile_id,
        "output_root": draft.output_root, "work_root": draft.work_root,
        "capability_status": capability.get("status"),
    }
    st.write(summary)
    with st.expander(text("details", language)):
        st.json({**summary, "capability": capability, "launch_eligibility": eligibility})
    if draft.bam_output_mode == "none":
        message(st, MessageLevel.INFO, text("quant_only", language), text("quant.copy", language),
                language=language)
    if st.button("Create immutable plan", disabled=not available):
        plan_path, error = capture(lambda: create_gui_plan(draft))
        if error:
            st.error(error)
        else:
            st.session_state[keys.PLAN_PATH] = str(plan_path)
            st.session_state[keys.PLAN_REVIEW] = False
    plan_path_value = str(st.session_state.get(keys.PLAN_PATH) or "")
    plan_payload = None
    if plan_path_value:
        plan_payload, plan_error = capture(
            lambda: json.loads(Path(plan_path_value).read_text(encoding="utf-8"))
        )
        if plan_error:
            st.error(plan_error)
            st.session_state[keys.PLAN_PATH] = ""
            st.session_state[keys.PLAN_REVIEW] = False
        else:
            st.subheader("Immutable plan review")
            st.json({
                "plan_id": plan_payload.get("plan_id"),
                "approval_hash": plan_payload.get("approval_hash"),
                "workflow_backend": plan_payload.get("workflow_backend"),
                "alignment_profile": plan_payload.get("alignment_profile_id"),
                "resource_contract": plan_payload.get("resource_contract_id"),
                "quantification": plan_payload.get("quantification"),
                "execution_context": plan_payload.get("execution_context"),
                "host_profile": (plan_payload.get("capability_snapshot") or {}).get("result", {}).get(
                    "host_profile_id"
                ),
                "reference": plan_payload.get("reference"),
                "output_root": plan_payload.get("output_root"),
                "work_root": plan_payload.get("work_root"),
                "limitations": eligibility.get("limitations") or (),
            })
            st.checkbox("I reviewed the immutable plan and approval hash", key=keys.PLAN_REVIEW)
    can_prepare = available and bool(plan_payload) and bool(st.session_state.get(keys.PLAN_REVIEW))
    if st.button(text("prepare_run", language), disabled=not can_prepare):
        prepared, error = capture(lambda: prepare_gui_run(
            draft, existing_plan_path=Path(plan_path_value),
        ))
        if error:
            st.error(error)
        else:
            st.session_state[keys.RUN_DIR] = prepared.run_directory
            st.query_params["run"] = prepared.run_directory
            st.success("Run prepared; draft changes will require a new preparation.")
            st.info(text("prepared.next", language))
            st.json({"run_id": prepared.run_id, "run_directory": prepared.run_directory,
                     "plan_id": prepared.plan_id, "analysis_series_id": prepared.analysis_series_id,
                     "approval_hash": prepared.approval_hash, "capability": prepared.capability})
