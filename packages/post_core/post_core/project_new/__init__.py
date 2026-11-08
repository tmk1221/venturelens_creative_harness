"""T34: a new project from a local recording in one call (`post project new`, the API's
ingest job). `placement` says where a project may live; `steps` are the idempotent pieces;
`op.new_project` runs them in order and reports each one."""
from __future__ import annotations

from .op import NewProjectError, new_project, plan_steps, validate_request
from .placement import RootPlacementError, check_root_placement
from .steps import NoTranscript, ensure_first_cut

__all__ = [
    "NewProjectError", "NoTranscript", "RootPlacementError", "check_root_placement", "ensure_first_cut",
    "new_project", "plan_steps", "validate_request",
]
