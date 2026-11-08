"""T30b: `/api/projects/{pid}/cuts/{cut_id}/decisions` -- the renamed-from-"Needs you"
project-wide decisions list (spec, "Additions" section). Pure translation of `post_core.
recipes.decisions` into HTTP; the aggregation itself lives there so a future top-bar count
badge or CLI command can reuse it without going through this router."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from post_core.recipes.decisions import counts_by_kind, decisions_for_cut
from post_core.store import store as store_module

from ..deps import get_project_root
from ..models import DecisionRowOut, DecisionsOut

router = APIRouter(prefix="/api/projects/{pid}/cuts/{cut_id}/decisions", tags=["decisions"])


@router.get("", response_model=DecisionsOut)
def list_decisions(cut_id: str, root: Path = Depends(get_project_root)) -> DecisionsOut:
    cut, _rev = store_module.read(root, "cut", cut_id)
    rows = decisions_for_cut(root, cut)
    return DecisionsOut(
        rows=[DecisionRowOut(kind=r.kind, span_id=r.span_id, node_id=r.node_id, cause=r.cause, link=r.link) for r in rows],
        counts=counts_by_kind(rows),
    )


__all__ = ["router"]
