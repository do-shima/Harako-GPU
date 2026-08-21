from __future__ import annotations

from typing import Any, Mapping


def render(st: Any, profile: Mapping[str, Any], *, selected: bool = False) -> None:
    border = "**Selected** · " if selected else ""
    st.markdown(f"{border}**{profile['display_name_ja']} / {profile['display_name_en']}**")
    st.caption(f"Salmon {profile['version']} · {profile['reproducibility_class']} · {profile['product_status']}")
