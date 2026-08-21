from __future__ import annotations

from typing import Any, Mapping

from harako_gpu.ui.labels import text


def render(st: Any, identity: Mapping[str, Any], *, language: str = "en") -> None:
    route = identity.get("execution_route")
    st.write({
        "project": identity.get("project_slug"),
        "run": identity.get("run_id"),
        "route": route,
        "workflow_backend": identity.get("workflow_backend"),
        "alignment_profile": identity.get("alignment_profile_id"),
        "execution_context": identity.get("execution_context"),
        "BAM": identity.get("bam_output_mode"),
        "GPU": route == "gpu_bam_alignment",
        "primary": identity.get("primary_profile_id"),
        "secondary": identity.get("secondary_profile_id"),
    })
    with st.expander(text("details", language)):
        st.json({key: identity.get(key) for key in (
        "run_id", "project_slug", "plan_id", "analysis_series_id", "execution_route",
        "reference_pack_id", "primary_profile_id", "secondary_profile_id", "bam_output_mode",
        "workflow_backend", "alignment_backend", "alignment_profile_id", "execution_context",
        "output_artifact_contract",
        )})
