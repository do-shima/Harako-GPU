from __future__ import annotations

import streamlit as st

from harako_gpu.services.gui import matrix_preview, poll_run_status, read_small_artifact, reconnect_run
from harako_gpu.ui import state as keys
from harako_gpu.ui.components.artifact_table import render as artifact_table
from harako_gpu.ui.components.run_identity import render as run_identity
from harako_gpu.ui.errors import capture
from harako_gpu.ui.labels import text
from harako_gpu.ui.components.page_intro import render as page_intro
from harako_gpu.ui.view_models import result_generation_summary


def render() -> None:
    language = st.session_state[keys.LANGUAGE]
    st.header(text("results", language))
    page_intro(st, "results", language)
    run_dir = st.session_state.get(keys.RUN_DIR) or ""
    payload, error = capture(lambda: reconnect_run(run_dir))
    if error:
        st.error(error)
        return
    identity = payload["run"]["identity"]
    run_identity(st, identity, language=language)
    status, status_error = capture(lambda: poll_run_status(run_dir, last_valid=st.session_state.get(keys.LAST_STATUS)))
    if status_error:
        st.error(status_error)
        return
    state = status["snapshot"]["state"]
    if state not in {"COMPLETED", "COMPLETED_WITH_LIMITATION", "RETENTION_PENDING"}:
        st.info(f"ℹ️ **{state}:** {text('results.pending', language)}")
        return
    artifacts = payload["artifacts"]["artifacts"]
    summary = result_generation_summary(identity, artifacts)
    st.subheader(f"{text('generated', language)} / {text('not_generated', language)}")
    generated_column, absent_column = st.columns(2)
    with generated_column:
        st.markdown(f"**✓ {text('generated', language)}**")
        for key in summary["generated"]:
            st.write(f"- {text(key, language)}")
    with absent_column:
        st.markdown(f"**— {text('not_generated', language)}**")
        for key in summary["not_generated"]:
            st.write(f"- {text(key, language)}")
    st.success(f"✓ **{text('primary_result', language)}:** {identity.get('primary_profile_id')}")
    if identity.get("secondary_profile_id"):
        st.info(f"◇ **{text('comparison_only', language)}:** {identity['secondary_profile_id']}\n\n"
                f"{text('profile.secondary', language)}")
    if identity.get("execution_route") == "fastq_quantification_only":
        st.caption(text("quant.copy", language))
    artifact_table(st, artifacts)
    matrices = [item for item in artifacts if str(item["role"]).startswith("matrix_")
                and item["state"] in {"PRESENT", "VALIDATED"}]
    if matrices:
        selected = st.selectbox("Matrix preview", [item["relative_path"] for item in matrices])
        preview, preview_error = capture(lambda: matrix_preview(run_dir, selected))
        st.error(preview_error) if preview_error else st.dataframe(preview["rows"], use_container_width=True)
    reports = [item for item in artifacts if item["role"] in {"self_contained_report", "concordance_html"}
               and item["state"] in {"PRESENT", "VALIDATED"}]
    for report in reports:
        if st.button(f"Open {report['role']}", key=f"open-{report['artifact_id']}"):
            content, report_error = capture(lambda: read_small_artifact(run_dir, report["relative_path"]))
            if report_error:
                st.error(report_error)
            else:
                st.components.v1.html(content["content"], height=700, scrolling=True)
