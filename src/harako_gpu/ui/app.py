"""Local-only Streamlit presentation shell for existing Harako-GPU services."""

from __future__ import annotations

import argparse
import sys

import streamlit as st

from harako_gpu.services.gui import gui_environment_defaults
from harako_gpu.ui import state as keys
from harako_gpu.ui.labels import assert_complete, page_label, text
from harako_gpu.ui.navigation import PAGES, access_map
from harako_gpu.ui.pages import (
    analysis, execution, projects, recovery, reference_capability, results,
    review_prepare, samples,
)
from harako_gpu.version import VERSION


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--output-root", default="")
    values, _ = parser.parse_known_args(sys.argv[1:])
    return values


def main() -> None:
    st.set_page_config(page_title="Harako-GPU", page_icon="🧬", layout="wide")
    st.markdown("""
    <style>
    [data-testid="stCode"] code { white-space: pre-wrap; overflow-wrap: anywhere; }
    [data-testid="stButton"] button { min-height: 2.75rem; }
    </style>
    """, unsafe_allow_html=True)
    assert_complete()
    arguments = _arguments()
    persisted_run = str(st.query_params.get("run", ""))
    keys.initialize(
        st.session_state, persisted_run_dir=persisted_run,
        environment=gui_environment_defaults(),
    )
    keys.preserve_across_pages(st.session_state)
    if arguments.output_root and not st.session_state[keys.OUTPUT_ROOT]:
        st.session_state[keys.OUTPUT_ROOT] = arguments.output_root
    language = st.sidebar.selectbox(text("language", st.session_state[keys.LANGUAGE]), ("ja", "en"), key=keys.LANGUAGE,
                                    format_func=lambda value: "日本語" if value == "ja" else "English")
    st.sidebar.caption(f"Harako-GPU {VERSION}")
    st.sidebar.info(text("local_only", language))
    access = access_map(st.session_state,
                        capability_available=(st.session_state.get(keys.CAPABILITY_RESULT) or {}).get("status")
                        in {"AVAILABLE_QUALIFIED", "AVAILABLE_WITH_LIMITATION"},
                        samples_valid=bool(st.session_state.get(keys.SAMPLES_VALID)))
    selected = st.sidebar.radio(text("navigation", language), PAGES, key=keys.PAGE,
                                format_func=lambda page: page_label(page, language))
    st.title(text("app.title", language))
    gate = access[selected]
    if not gate.enabled:
        reason_key = {
            "Select a project first.": "blocker.project", "Validate samples first.": "blocker.samples",
            "Select an available route.": "blocker.route", "Prepare a run first.": "blocker.prepare",
            "Prepare or reconnect to a run first.": "blocker.prepare", "Select a run first.": "blocker.run",
        }.get(gate.reason)
        reason = text(reason_key, language) if reason_key else gate.reason
        st.warning(f"⛔ **{text('current_blocker', language)}:** {reason}")
        return
    renderers = {
        "Project": projects.render,
        "Samples": samples.render,
        "Reference & capability": reference_capability.render,
        "Analysis": analysis.render,
        "Review & prepare": review_prepare.render,
        "Run": execution.render,
        "Results": results.render,
        "Recovery & support": recovery.render,
    }
    renderers[selected]()


main()
