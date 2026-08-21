from __future__ import annotations

import streamlit as st

from harako_gpu.services.gui import (
    create_gui_support_bundle, export_gui_handoff, launch_gui_controller,
    reconnect_run, verify_gui_artifacts,
)
from harako_gpu.ui import state as keys
from harako_gpu.ui.errors import capture
from harako_gpu.ui.labels import text
from harako_gpu.services.capabilities import FULL_HUMAN_REFERENCE_PACK_ID
from harako_gpu.ui.components.page_intro import render as page_intro
from harako_gpu.ui.components.message import MessageLevel, render as message


def render() -> None:
    language = st.session_state[keys.LANGUAGE]
    st.header(text("recovery", language))
    page_intro(st, "recovery", language)
    run_dir = st.session_state.get(keys.RUN_DIR) or ""
    payload, error = capture(lambda: reconnect_run(run_dir))
    if error:
        st.error(error)
        return
    identity = payload["run"]["identity"]
    status = payload["status"]
    if status["state"] in {"FAILED", "INTERRUPTED"}:
        failure = status.get("failure") or {}
        message(st, MessageLevel.FAILURE, str(failure.get("classification") or status["state"]),
                str(failure.get("user_facing_explanation") or failure.get("message") or
                    "Review the preserved evidence before resuming."), language=language,
                next_action="Create a support bundle, then resume only if the run is marked resumable.")
    recovery_summary = {"state": status["state"], "attempt_count": len(payload["attempts"]),
                        "resumable": status.get("resumable", False),
                        "failure_class": (status.get("failure") or {}).get("classification")}
    st.write(recovery_summary)
    with st.expander(text("details", language)):
        st.json({"attempts": payload["attempts"], "lock": payload["lock_state"],
                 "failure": status.get("failure")})
    if st.button("Resume", disabled=status["state"] not in {"FAILED", "INTERRUPTED"}
                 or not status.get("resumable", False)):
        result, launch_error = capture(lambda: launch_gui_controller(
            action="resume", run_directory=run_dir, approval_hash=identity["approval_hash"]))
        st.error(launch_error) if launch_error else st.success(f"Resume controller PID {result.pid}")
    deep = st.checkbox("Deep verification (large BAM SHA may be expensive)")
    if st.button("Verify artifacts"):
        result, verify_error = capture(lambda: verify_gui_artifacts(run_dir, deep=deep))
        st.error(verify_error) if verify_error else st.json(result)
    if st.button("Create sanitized support bundle"):
        result, bundle_error = capture(lambda: create_gui_support_bundle(run_dir))
        st.error(bundle_error) if bundle_error else st.success(result)
    if identity.get("reference_pack_id") == FULL_HUMAN_REFERENCE_PACK_ID:
        handoff = f"{st.session_state[keys.RUNTIME_ROOT].rstrip('/')}/handoff/high-memory-host-handoff.json"
        if st.button("Create high-memory host handoff"):
            result, handoff_error = capture(lambda: export_gui_handoff(handoff))
            st.error(handoff_error) if handoff_error else st.success(result)
