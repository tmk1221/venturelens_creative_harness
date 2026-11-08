"""T13b: `/api/projects/{pid}/cuts/{cut_id}/suggested-visuals` -- the automated "Suggest
visuals" pass. Generation/validation/persistence all live in `post_core.edit.suggest`; this
module only translates HTTP, the same split `cuts.py` and `enrich.py` use. Brand kit context
comes from the project's own kit (T33: `post_core.brand`, the helper `enrich.py` shares)."""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from post_core import brand as brand_mod
from post_core.edit import suggest as suggest_mod
from post_core.edit.suggest_store import read_suggestions
from post_core.store import store as store_module

from ..deps import get_project_root
from ..models import AcceptAllOut, AcceptSuggestionOut, SuggestionVariantOut, SuggestVisualsResult, VisualSuggestionOut

router = APIRouter(prefix="/api/projects/{pid}/cuts/{cut_id}/suggested-visuals", tags=["suggest"])


def _transcripts_for(root: Path) -> list:
    from post_core.store.paths import store_root

    d = store_root(root) / "transcripts"
    out = []
    if d.is_dir():
        for f in sorted(d.glob("*.json")):
            obj, _rev = store_module.read(root, "transcript", f.stem)
            out.append(obj)
    return out


def _out(s) -> VisualSuggestionOut:
    return VisualSuggestionOut(
        id=s.id, transcript_id=s.start_anchor.transcript_id,
        start_word_id=s.start_anchor.word_id, end_word_id=s.end_anchor.word_id,
        medium=s.medium, overlay_depth=s.overlay_depth, overlay_position=s.overlay_position,
        brief=s.brief, direction_note=s.direction_note, flags=list(s.flags),
        cast_refs=list(s.cast_refs), density_hint=s.density_hint, rationale=s.rationale,
        variants=[SuggestionVariantOut(**v.model_dump()) for v in s.variants], active_variant=s.active_variant,
    )


@router.get("", response_model=SuggestVisualsResult)
def list_pending(cut_id: str, root: Path = Depends(get_project_root)) -> SuggestVisualsResult:
    file = read_suggestions(root, cut_id)
    return SuggestVisualsResult(items=[_out(s) for s in file.items])


class SuggestVisualsRequest(BaseModel):
    scope: Literal["cut", "selection"] = "cut"
    sync_group_id: Optional[str] = None
    start_word_id: Optional[str] = None
    end_word_id: Optional[str] = None


@router.post("", response_model=SuggestVisualsResult)
def suggest_visuals(cut_id: str, body: SuggestVisualsRequest, root: Path = Depends(get_project_root)) -> SuggestVisualsResult:
    """Run the pass (whole cut, or the given selection) and return every currently-pending
    proposal. T42: the run replaces the pending proposals inside its scope (those elsewhere
    stay); the project's picture mode steers it (`audio_only` = full coverage)."""
    cut, _rev = store_module.read(root, "cut", cut_id)
    transcripts = _transcripts_for(root)
    if not transcripts:
        raise HTTPException(status_code=400, detail="project has no transcripts to suggest against")

    if body.scope == "selection":
        if not (body.sync_group_id and body.start_word_id and body.end_word_id):
            raise HTTPException(status_code=400, detail="selection scope requires sync_group_id/start_word_id/end_word_id")
        scope = suggest_mod.Scope(
            kind="selection", sync_group_id=body.sync_group_id,
            start_word_id=body.start_word_id, end_word_id=body.end_word_id,
        )
    else:
        if not cut.passages:
            return SuggestVisualsResult(items=[])
        first, last = cut.passages[0], cut.passages[-1]
        if first.sync_group_id != last.sync_group_id:
            # Multi-sync-group cuts aren't in this demo's shape yet -- run against the first
            # passage's sync group rather than guess at a cross-group scope.
            last = first
        scope = suggest_mod.Scope(
            kind="cut", sync_group_id=first.sync_group_id,
            start_word_id=first.start_word_id, end_word_id=last.end_word_id,
        )

    # Real mode asks the project's terminal agent (T36); an `AgentError` becomes a 502 with
    # its `reason` (errors.py) and leaves the pending list untouched.
    items = suggest_mod.suggest_visuals(
        root, cut_id, transcripts, scope, cut=cut, writer_context=brand_mod.project_writer_context(root),
    )
    return SuggestVisualsResult(items=[_out(s) for s in items])


@router.post("/{suggestion_id}/accept", response_model=AcceptSuggestionOut)
def accept(cut_id: str, suggestion_id: str, root: Path = Depends(get_project_root)) -> AcceptSuggestionOut:
    new_cut, suggestion = suggest_mod.accept_suggestion(root, cut_id, suggestion_id)
    _cut, revision = store_module.read(root, "cut", cut_id)
    span = next(
        (s for s in new_cut.spans if s.start_anchor == suggestion.start_anchor and s.end_anchor == suggestion.end_anchor),
        None,
    )
    return AcceptSuggestionOut(cut_id=cut_id, revision=revision, span_id=span.id if span else "")


@router.post("/{suggestion_id}/dismiss", response_model=VisualSuggestionOut)
def dismiss(cut_id: str, suggestion_id: str, root: Path = Depends(get_project_root)) -> VisualSuggestionOut:
    dismissed = suggest_mod.dismiss_suggestion(root, cut_id, suggestion_id)
    return _out(dismissed)


class SuggestionPatch(BaseModel):
    """T40: inline edits on a proposed card. Only the fields sent are changed; `medium: null`
    means "overlay only" (refused unless the proposal carries an overlay)."""

    model_config = ConfigDict(extra="forbid")

    brief: Optional[str] = None
    direction_note: Optional[str] = None
    medium: Optional[Literal["aroll", "provided", "live_action", "motion_graphic"]] = None


@router.patch("/{suggestion_id}", response_model=VisualSuggestionOut)
def edit(cut_id: str, suggestion_id: str, body: SuggestionPatch, root: Path = Depends(get_project_root)) -> VisualSuggestionOut:
    changes = body.model_dump(include=body.model_fields_set)
    for key in ("brief", "direction_note"):
        if key in changes and changes[key] is None:
            raise HTTPException(status_code=400, detail=f"{key} cannot be null")
    return _out(suggest_mod.update_suggestion(root, cut_id, suggestion_id, changes))


class VariantSwitch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int


@router.post("/{suggestion_id}/variant", response_model=VisualSuggestionOut)
def switch_variant(cut_id: str, suggestion_id: str, body: VariantSwitch, root: Path = Depends(get_project_root)) -> VisualSuggestionOut:
    """T42: make another of the proposal's ideas (Variant A, B, ...) the active one."""
    return _out(suggest_mod.switch_variant(root, cut_id, suggestion_id, body.index))


@router.post("/accept-all", response_model=AcceptAllOut)
def accept_all(cut_id: str, root: Path = Depends(get_project_root)) -> AcceptAllOut:
    result = suggest_mod.accept_all(root, cut_id)
    return AcceptAllOut(accepted=result.accepted, blocked=result.blocked)


__all__ = ["router"]
