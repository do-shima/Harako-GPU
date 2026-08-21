from __future__ import annotations

import streamlit as st

from harako_gpu.services.capabilities import FULL_HUMAN_REFERENCE_PACK_ID
from harako_gpu.services.gui import visible_profile_cards
from harako_gpu.ui import state as keys
from harako_gpu.ui.components.profile_card import render as profile_card
from harako_gpu.ui.labels import text
from harako_gpu.ui.components.page_intro import render as page_intro


def render() -> None:
    language = st.session_state[keys.LANGUAGE]
    st.header(text("analysis", language))
    page_intro(st, "analysis", language)
    labels = {"recommended_only": text("recommended", language),
              "compatibility_only": text("compatibility", language),
              "compare_both": text("compare", language)}
    mode = st.radio("Quantification mode", tuple(labels), key=keys.QUANT_MODE,
                    format_func=lambda value: labels[value],
                    on_change=keys.invalidate_scientific_selection, args=(st.session_state,))
    if mode == "recommended_only":
        st.session_state[keys.PRIMARY_PROFILE] = "salmon_2_5_1_deterministic"
    elif mode == "compatibility_only":
        st.session_state[keys.PRIMARY_PROFILE] = "salmon_1_10_3_compatibility"
    else:
        st.radio("Primary profile", ("salmon_2_5_1_deterministic", "salmon_1_10_3_compatibility"),
                 key=keys.PRIMARY_PROFILE, on_change=keys.invalidate_scientific_selection,
                 args=(st.session_state,))
        st.info(text("compare.copy", language))
        st.caption(text("profile.secondary", language))
    for profile in visible_profile_cards():
        with st.container(border=True):
            profile_card(st, profile, selected=profile["profile_id"] == st.session_state[keys.PRIMARY_PROFILE])
            if mode == "compare_both" and profile["profile_id"] != st.session_state[keys.PRIMARY_PROFILE]:
                st.caption(f"◇ {text('comparison_only', language)} — {text('profile.secondary', language)}")
            with st.expander("Version, image, index and limitations"):
                st.json(profile)
    asset_requirements = {
        "recommended_only": ("salmon-2.5.1 index",),
        "compatibility_only": ("salmon-1.10.3 index",),
        "compare_both": ("salmon-2.5.1 index", "salmon-1.10.3 index"),
    }
    st.write({"required_quantification_assets": asset_requirements[mode]})
    if mode in {"compatibility_only", "compare_both"}:
        st.info("Salmon 1.10.3 is the visible bounded-numerical compatibility profile; it is not rejected.")
    if st.session_state[keys.BAM_MODE] != "none":
        resource = (
            "42 GB / 12 CPUs · ubuntu_native_rtx3090_ram128_one_pass_42gb_v1"
            if st.session_state[keys.ALIGNMENT_PROFILE] == "parabricks_star_one_pass_workstation"
            else "96 GB / 12 CPUs · ubuntu_native_rtx3090_ram128_two_pass_96gb_v1"
        )
        st.write({"fixed_alignment_resource": resource, "free_form_resource_override": False})
    st.write({"execution_route": "fastq_quantification_only" if st.session_state[keys.BAM_MODE] == "none"
              else "gpu_bam_alignment", "GPU_used": st.session_state[keys.BAM_MODE] != "none",
              "STAR_comparator": st.session_state[keys.BAM_MODE] != "none",
              "primary_profile": st.session_state[keys.PRIMARY_PROFILE], "sequential_execution": True})
    if st.session_state[keys.REFERENCE] == FULL_HUMAN_REFERENCE_PACK_ID and st.session_state[keys.BAM_MODE] == "none":
        st.info("Tested envelope: recommended up to 20M read pairs; maximum tested 36.35M, one sample on this host. Preflight re-evaluates resources.")
