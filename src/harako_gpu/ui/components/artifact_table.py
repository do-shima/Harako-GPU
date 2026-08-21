from __future__ import annotations

from typing import Any, Sequence, Mapping


def render(st: Any, artifacts: Sequence[Mapping[str, Any]]) -> None:
    rows = [{key: artifact.get(key) for key in (
        "role", "profile_id", "relative_path", "size", "state", "sha256_status", "limitation",
    )} for artifact in artifacts]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    paths = [str(row["relative_path"]) for row in rows if row.get("relative_path")]
    if paths:
        selected = st.selectbox("Artifact path", paths, key="artifact-path-copy")
        st.code(selected, language=None, wrap_lines=True)
