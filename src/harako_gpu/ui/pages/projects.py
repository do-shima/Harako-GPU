from __future__ import annotations

import streamlit as st

from harako_gpu.services.gui import discover_projects, host_summary, project_slug_valid
from harako_gpu.ui import state as keys
from harako_gpu.ui.errors import capture
from harako_gpu.ui.labels import text
from harako_gpu.ui.components.page_intro import render as page_intro
from harako_gpu.version import VERSION


def render() -> None:
    language = st.session_state[keys.LANGUAGE]
    st.header(text("project", language))
    blocker = "" if st.session_state.get(keys.PROJECT_SLUG) else text("blocker.project", language)
    page_intro(st, "project", language, blocker=blocker)
    st.caption(f"Harako-GPU {VERSION}")
    context = st.session_state[keys.EXECUTION_CONTEXT]
    runtime_label = "Native Linux runtime root" if context == "native_linux" else "WSL runtime root"
    runtime = st.text_input(runtime_label, key=keys.RUNTIME_ROOT,
                            placeholder="/home/<user>/harako-gpu-runtime")
    if runtime and not st.session_state[keys.OUTPUT_ROOT]:
        st.session_state[keys.OUTPUT_ROOT] = f"{runtime.rstrip('/')}/gui-runs"
    if runtime and not st.session_state[keys.WORK_ROOT]:
        st.session_state[keys.WORK_ROOT] = f"{runtime.rstrip('/')}/gui-work"
    st.text_input("Output root", key=keys.OUTPUT_ROOT)
    st.text_input("Work root", key=keys.WORK_ROOT)
    display_name = st.text_input("Project display name", key=keys.PROJECT)
    st.text_input("Project slug", key=keys.PROJECT_SLUG,
                  help="lowercase letters and digits separated by single hyphens")
    if st.session_state[keys.PROJECT_SLUG] and not project_slug_valid(st.session_state[keys.PROJECT_SLUG]):
        st.error("Invalid slug: use lowercase letters/digits separated by single hyphens.")
    st.write({"display_name": display_name, "slug": st.session_state[keys.PROJECT_SLUG],
              "output_root": st.session_state[keys.OUTPUT_ROOT],
              "execution_context": context,
              "host_profile_id": st.session_state[keys.HOST_PROFILE_ID]})
    if st.button("Inspect host readiness"):
        payload, error = capture(lambda: host_summary(
            runtime_root=runtime, execution_context=context,
        ))
        st.error(error) if error else st.json(payload)
    if st.button("Discover existing projects", disabled=not bool(st.session_state[keys.OUTPUT_ROOT])):
        payload, error = capture(lambda: discover_projects(st.session_state[keys.OUTPUT_ROOT]))
        if error:
            st.error(error)
        else:
            st.session_state["project_discovery"] = payload
    discovered = st.session_state.get("project_discovery") or {}
    for project in discovered.get("projects", []):
        with st.expander(f"{project['project_slug']} · {project['run_count']} runs"):
            st.json(project["last_run"])
            if st.button("Reconnect", key=f"reconnect-{project['last_run']['run_id']}"):
                st.session_state[keys.PROJECT_SLUG] = project["project_slug"]
                st.session_state[keys.RUN_DIR] = project["last_run"]["run_directory"]
