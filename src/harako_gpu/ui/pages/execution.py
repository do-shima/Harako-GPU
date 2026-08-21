from __future__ import annotations

import streamlit as st

from harako_gpu.services.gui import launch_gui_controller, poll_run_status, reconnect_run
from harako_gpu.ui import state as keys
from harako_gpu.ui.components.status_panel import render as status_panel
from harako_gpu.ui.errors import capture
from harako_gpu.ui.labels import text
from harako_gpu.ui.components.message import MessageLevel, render as message
from harako_gpu.ui.components.page_intro import render as page_intro


def _identity() -> tuple[dict | None, str | None]:
    run_dir = st.session_state.get(keys.RUN_DIR) or ""
    if not run_dir:
        return None, "No selected run"
    payload, error = capture(lambda: reconnect_run(run_dir))
    return payload, error


def _status_body() -> None:
    run_dir = st.session_state.get(keys.RUN_DIR) or ""
    if not run_dir:
        return
    result, error = capture(lambda: poll_run_status(
        run_dir, last_valid=st.session_state.get(keys.LAST_STATUS)))
    if error:
        if st.session_state.get(keys.LAST_STATUS):
            st.session_state[keys.STATUS_STALE] = True
            status_panel(st, st.session_state[keys.LAST_STATUS], stale=True,
                         language=st.session_state[keys.LANGUAGE])
        else:
            st.error(error)
        return
    st.session_state[keys.LAST_STATUS] = result["snapshot"]
    st.session_state[keys.STATUS_STALE] = result["stale"]
    status_panel(st, result["snapshot"], stale=result["stale"],
                 language=st.session_state[keys.LANGUAGE])


@st.fragment(run_every=2.0)
def _live_status_2s() -> None:
    _status_body()


@st.fragment(run_every=5.0)
def _live_status_5s() -> None:
    _status_body()


def render() -> None:
    language = st.session_state[keys.LANGUAGE]
    st.header(text("run", language))
    page_intro(st, "run", language)
    message(st, MessageLevel.INFO, text("browser_continues", language), text("no_cancel", language),
            language=language)
    payload, error = _identity()
    if error:
        st.error(error)
        return
    identity = payload["run"]["identity"]
    state = payload["status"]["state"]
    st.write({"run_id": identity["run_id"], "project": identity["project_slug"],
              "route": identity.get("execution_route"), "primary": identity["primary_profile_id"],
              "secondary": identity.get("secondary_profile_id"),
              "workflow_backend": identity.get("workflow_backend"),
              "alignment_profile": identity.get("alignment_profile_id"),
              "execution_context": identity.get("execution_context"),
              "run_directory": st.session_state[keys.RUN_DIR]})
    confirmed = st.checkbox(text("review_confirm", language))
    if st.button(text("start_run", language), disabled=state != "PREPARED" or not confirmed):
        launched, launch_error = capture(lambda: launch_gui_controller(
            action="start", run_directory=st.session_state[keys.RUN_DIR],
            approval_hash=identity["approval_hash"]))
        if launch_error:
            st.error(launch_error)
        else:
            st.success(f"Controller PID {launched.pid}; browser/page reruns do not stop the run.")
    controls = st.columns((2, 2, 1))
    with controls[0]:
        st.toggle(text("auto_refresh", language), key=keys.AUTO_REFRESH)
    with controls[1]:
        st.selectbox(text("refresh_interval", language), (2, 5), key=keys.REFRESH_INTERVAL,
                     format_func=lambda value: f"{value} s")
    with controls[2]:
        refresh_now = st.button(text("refresh_now", language))
    if st.session_state[keys.AUTO_REFRESH]:
        (_live_status_2s if st.session_state[keys.REFRESH_INTERVAL] == 2 else _live_status_5s)()
    elif refresh_now or st.session_state.get(keys.LAST_STATUS) is None:
        _status_body()
    else:
        st.caption(text("polling_paused", language))
        status_panel(st, st.session_state[keys.LAST_STATUS],
                     stale=bool(st.session_state.get(keys.STATUS_STALE)), language=language)
