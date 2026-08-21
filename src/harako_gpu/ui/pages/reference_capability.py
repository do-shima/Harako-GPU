from __future__ import annotations

import streamlit as st

from harako_gpu.services.alignment_profiles import ONE_PASS_PROFILE_ID, TWO_PASS_PROFILE_ID
from harako_gpu.services.capabilities import FULL_HUMAN_REFERENCE_PACK_ID
from harako_gpu.services.gui import (
    capability_for, export_gui_handoff, reference_catalog,
    scientific_launch_eligibility,
)
from harako_gpu.services.workflow_backends import HARAKO_NATIVE_V1, NFCORE_REFERENCE
from harako_gpu.ui import state as keys
from harako_gpu.ui.draft import from_state
from harako_gpu.ui.components.capability_card import render as capability_card
from harako_gpu.ui.errors import capture
from harako_gpu.ui.labels import text
from harako_gpu.ui.components.message import MessageLevel, render as message
from harako_gpu.ui.components.page_intro import render as page_intro


def render() -> None:
    language = st.session_state[keys.LANGUAGE]
    st.header(text("reference", language))
    page_intro(st, "reference", language)
    execution_context = st.session_state[keys.EXECUTION_CONTEXT]
    native = execution_context == "native_linux"
    catalog, error = capture(lambda: reference_catalog(
        runtime_root=st.session_state[keys.RUNTIME_ROOT],
        execution_context=execution_context,
    ))
    if error:
        st.error(error)
        return
    options = {item.reference_pack_id: item for item in catalog}
    selected = st.selectbox(
        "Reference pack", tuple(options), key=keys.REFERENCE,
        format_func=lambda value: options[value].display_name,
        on_change=keys.invalidate_scientific_selection, args=(st.session_state,),
    )
    reference_summary = {key: value for key, value in options[selected].as_dict().items()
                         if key in {"species", "assembly", "annotation_release", "transcript_count",
                                    "gene_count", "resource_class", "qualification_status"}}
    st.write(reference_summary)
    with st.expander(text("details", language)):
        st.json(options[selected].as_dict())
        st.write(text("glossary.bam", language))
        st.write(text("glossary.gpu", language))
    backend_options = (HARAKO_NATIVE_V1, NFCORE_REFERENCE) if native else (NFCORE_REFERENCE,)
    if st.session_state[keys.WORKFLOW_BACKEND] not in backend_options:
        st.session_state[keys.WORKFLOW_BACKEND] = backend_options[0]
    st.selectbox(
        "Workflow backend", backend_options, key=keys.WORKFLOW_BACKEND,
        format_func=lambda value: (
            "Harako-native（標準・Ubuntu検証済み）" if value == HARAKO_NATIVE_V1
            else "nf-core/rnaseq 3.26（参照・expert向け）"
        ),
        on_change=keys.invalidate_scientific_selection, args=(st.session_state,),
    )
    if not native:
        st.caption("Harako-native scientific execution is not qualified on Windows/WSL.")
    human = selected == FULL_HUMAN_REFERENCE_PACK_ID
    left, middle, right = st.columns(3)
    with left:
        st.markdown(f"**{text('quant_only', language)}**")
        st.caption("CPU · counts/TPM · no BAM/junction/STAR GeneCounts")
        if st.button(text("select", language), key="select-quant-only"):
            keys.invalidate_scientific_selection(st.session_state)
            st.session_state[keys.BAM_MODE] = "none"
            st.session_state[keys.ALIGNMENT_PROFILE] = "none"
    with middle:
        st.markdown(f"**{text('bam_keep', language)}**")
        st.caption("GPU alignment · BAM/BAI · junction · STAR GeneCounts")
        if st.button(text("select", language), key="select-bam-keep", disabled=human and not native):
            keys.invalidate_scientific_selection(st.session_state)
            st.session_state[keys.BAM_MODE] = "keep"
            st.session_state[keys.ALIGNMENT_PROFILE] = TWO_PASS_PROFILE_ID
    with right:
        st.markdown(f"**{text('bam_discard', language)}**")
        st.caption(text("unavailable_planned", language))
        st.button(text("unavailable", language), key="select-bam-discard", disabled=True)
    if human and not native:
        message(st, MessageLevel.LIMITATION, text("bam_keep", language),
                text("human.blocked", language), language=language,
                next_action=text("human_bam.next", language))
        handoff = f"{st.session_state[keys.RUNTIME_ROOT].rstrip('/')}/handoff/high-memory-host-handoff.json"
        if st.button("高メモリGPU環境向けhandoffを作成 / Create high-memory handoff",
                     key="human-handoff-visible"):
            path, handoff_error = capture(lambda: export_gui_handoff(handoff))
            st.error(handoff_error) if handoff_error else st.success(path)
    bam = st.session_state[keys.BAM_MODE]
    st.write({"requested_bam_output_mode": bam})
    if bam == "none":
        st.session_state[keys.ALIGNMENT_PROFILE] = "none"
        message(st, MessageLevel.INFO, text("quant_only", language), text("quant.copy", language),
                language=language)
    else:
        choices = (ONE_PASS_PROFILE_ID, TWO_PASS_PROFILE_ID) if human else (TWO_PASS_PROFILE_ID,)
        if st.session_state[keys.ALIGNMENT_PROFILE] not in choices:
            st.error("The previously requested alignment profile is not available for this exact reference.")
        else:
            st.selectbox(
                "Alignment profile", choices, key=keys.ALIGNMENT_PROFILE,
                on_change=keys.invalidate_scientific_selection, args=(st.session_state,),
            )
    if native:
        if st.button("Validate native launch eligibility", key="validate-native-launch"):
            result, eligibility_error = capture(lambda: scientific_launch_eligibility(
                from_state(st.session_state),
            ))
            if eligibility_error:
                st.error(eligibility_error)
                st.session_state[keys.LAUNCH_ELIGIBILITY] = None
            else:
                st.session_state[keys.LAUNCH_ELIGIBILITY] = result.as_dict()
        eligibility = st.session_state.get(keys.LAUNCH_ELIGIBILITY) or {}
        if not eligibility:
            st.info("Validate the installed receipt, assets, images, storage, and capability before preparation.")
            st.session_state[keys.CAPABILITY_RESULT] = None
            return
        result_payload = {
            "status": eligibility.get("capability_status") if eligibility.get("allowed") else "NOT_QUALIFIED",
            "gpu_used": bam != "none", "bam_generated": bam != "none",
            "explanation": eligibility.get("blocker_explanation") or "Native launch gates passed.",
            "allowed_next_actions": () if eligibility.get("allowed") else ("Resolve the reported blocker",),
            "host_profile_id": eligibility.get("detected_host_profile_id"),
            "workflow_backend": eligibility.get("workflow_backend"),
        }
        st.session_state[keys.CAPABILITY_RESULT] = result_payload
        st.json({"launch_eligibility": eligibility})
        capability_card(st, result_payload, language)
        return
    result, capability_error = capture(lambda: capability_for(
        reference_pack_id=selected, bam_output_mode=bam,
        alignment_profile_id=st.session_state[keys.ALIGNMENT_PROFILE],
        quantification_mode=st.session_state[keys.QUANT_MODE],
        primary_profile_id=st.session_state[keys.PRIMARY_PROFILE],
        runtime_root=st.session_state[keys.RUNTIME_ROOT]))
    if capability_error:
        st.error(capability_error)
        st.session_state[keys.CAPABILITY_RESULT] = None
        return
    st.session_state[keys.CAPABILITY_RESULT] = result.as_dict()
    capability_card(st, result.as_dict(), language)
