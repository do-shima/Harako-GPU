from __future__ import annotations

from typing import Any

import streamlit as st

from harako_gpu.services.gui import scan_fastqs, validate_gui_samples
from harako_gpu.ui import state as keys
from harako_gpu.ui.errors import capture
from harako_gpu.ui.labels import text
from harako_gpu.ui.components.message import error_summary
from harako_gpu.ui.components.page_intro import render as page_intro


def _records(value: Any) -> list[dict[str, str]]:
    if hasattr(value, "to_dict"):
        return [dict(row) for row in value.to_dict("records")]
    return [dict(row) for row in value]


def render() -> None:
    language = st.session_state[keys.LANGUAGE]
    st.header(text("samples", language))
    page_intro(st, "samples", language,
               blocker="" if st.session_state.get(keys.SAMPLES_VALID) else text("blocker.samples", language))
    with st.expander("FASTQ / library type help"):
        st.write(text("glossary.fastq", language))
    st.text_input("FASTQ directory", key=keys.FASTQ_DIRECTORY)
    st.selectbox("Layout", ("paired", "single"), key=keys.READ_LAYOUT)
    st.selectbox("Explicit library type", ("U", "ISF", "ISR"), key=keys.LIBRARY_TYPE,
                 help="Auto is not allowed for primary execution.")
    if st.button("Scan FASTQ", disabled=not bool(st.session_state[keys.FASTQ_DIRECTORY])):
        result, error = capture(lambda: scan_fastqs(
            st.session_state[keys.FASTQ_DIRECTORY], layout=st.session_state[keys.READ_LAYOUT],
            library_type=st.session_state[keys.LIBRARY_TYPE]))
        if error:
            st.error(error)
            st.session_state[keys.SAMPLES_VALID] = False
        else:
            st.session_state[keys.SAMPLES] = result["rows"]
            st.session_state[keys.SAMPLES_VALID] = result["valid"]
            st.session_state["sample_errors"] = result["errors"]
    rows = st.data_editor(st.session_state[keys.SAMPLES], num_rows="dynamic", use_container_width=True,
                          disabled=("fastq_1", "fastq_2", "strandedness", "library_protocol"))
    st.session_state[keys.SAMPLES] = _records(rows)
    validation = validate_gui_samples(st.session_state[keys.SAMPLES]) if st.session_state[keys.SAMPLES] else {
        "valid": False, "errors": []}
    st.session_state[keys.SAMPLES_VALID] = validation["valid"] and not bool(st.session_state.get("sample_errors"))
    errors = list(st.session_state.get("sample_errors") or []) + list(validation["errors"])
    if errors:
        error_summary(st, errors, language=language, next_action=text("samples.next", language))
    elif st.session_state[keys.SAMPLES]:
        st.success(f"{len(st.session_state[keys.SAMPLES])} sample(s) validated")
