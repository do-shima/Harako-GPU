"""Fixed navigation order and draft-access presentation gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Any


PAGES = (
    "Project", "Samples", "Reference & capability", "Analysis",
    "Review & prepare", "Run", "Results", "Recovery & support",
)


@dataclass(frozen=True)
class PageAccess:
    enabled: bool
    reason: str = ""


def access_map(state: Mapping[str, Any], *, capability_available: bool = False,
               samples_valid: bool = False) -> dict[str, PageAccess]:
    project = bool(state.get("project_slug"))
    run = bool(state.get("current_run_directory"))
    return {
        "Project": PageAccess(True),
        "Samples": PageAccess(project, "Select a project first."),
        "Reference & capability": PageAccess(project and samples_valid, "Validate samples first."),
        "Analysis": PageAccess(project and samples_valid, "Validate samples first."),
        "Review & prepare": PageAccess(project and samples_valid and capability_available,
                                         "Select an available route."),
        "Run": PageAccess(run, "Prepare a run first."),
        "Results": PageAccess(run, "Prepare or reconnect to a run first."),
        "Recovery & support": PageAccess(run, "Select a run first."),
    }
