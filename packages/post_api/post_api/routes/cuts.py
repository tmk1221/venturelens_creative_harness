"""`/api/projects/{pid}/cuts`: new, show, `POST .../ops` (optimistic concurrency via
`expected_rev` -> 409 on conflict), undo/redo, derive. Mirrors `post cut ...`; all editing
logic stays in `post_core.edit` (ops.py/session.py) -- this module only translates HTTP."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from post_core.edit import ops as ops_mod
from post_core.edit.ranges import TranscriptIndex, timeline as timeline_fn
from post_core.edit.session import EditSession
from post_core.edit.similarity import find_swap_candidates
from post_core.model.common import Rational
from post_core.model.cut import Cut
from post_core.model.shoot import Shoot, clean_audio_source
from post_core.model.transcript import Transcript
from post_core.store import store as store_module
from post_core.store.errors import RevisionConflict, StoreError
from post_core.store.paths import store_root
from pydantic import BaseModel

from ..deps import get_project_root
from ..models import CutOpResult, CutShowOut, CutSummaryOut, EditReportOut, SwapCandidateOut, TimelineSegmentOut

router = APIRouter(prefix="/api/projects/{pid}/cuts", tags=["cuts"])

_OP_NAMES = (
    "delete_words", "restore_words", "insert_range", "move_passage", "move_words",
    "replace_range_with", "set_angle", "set_trim", "add_span", "remove_span",
    # T30c: the "Add visual"/card-edit dialog's own op -- creates a beat's picture and/or
    # overlay Span together (full T30 beat model), same shape as T13b's suggestion accept
    # (`edit.suggest.accept_suggestion`), just triggered manually instead of from a proposal.
    "add_beat_spans",
)


def _parse_aspect(raw: str) -> Rational:
    if ":" in raw:
        num_s, den_s = raw.split(":", 1)
        return Rational(num=int(num_s), den=int(den_s))
    return Rational(num=int(raw), den=1)


def _load_all_transcripts(root: Path) -> dict[str, Transcript]:
    d = store_root(root) / "transcripts"
    out: dict[str, Transcript] = {}
    if d.is_dir():
        for f in sorted(d.glob("*.json")):
            obj, _rev = store_module.read(root, "transcript", f.stem)
            out[f.stem] = obj  # type: ignore[assignment]
    return out


def _load_all_shoots(root: Path) -> list[Shoot]:
    d = store_root(root) / "shoots"
    out: list[Shoot] = []
    if d.is_dir():
        for f in sorted(d.glob("*.json")):
            shoot, _rev = store_module.read(root, "shoot", f.stem)
            out.append(shoot)  # type: ignore[arg-type]
    return out


def _audio_source_ids_by_group(shoots: list[Shoot]) -> dict[str, str]:
    """T22: which Source's audio proxy plays for each SyncGroup -- the group's dedicated
    audio recorder, falling back to its a_roll camera. See `clean_audio_source`."""
    mapping: dict[str, str] = {}
    for shoot in shoots:
        for group in shoot.sync_groups:
            try:
                mapping[group.id] = clean_audio_source(shoot, group).id
            except ValueError:
                continue
    return mapping


class CutNewRequest(BaseModel):
    transcript: str
    angle: str
    aspect: str = "16:9"
    variant_label: Optional[str] = None


@router.post("")
def cut_new(body: CutNewRequest, root: Path = Depends(get_project_root)) -> dict:
    transcript, _rev = store_module.read(root, "transcript", body.transcript)
    cut = ops_mod.cut_from_transcript(transcript, body.angle, _parse_aspect(body.aspect))
    if body.variant_label:
        cut = cut.model_copy(update={"variant_label": body.variant_label})
    store_module.write(root, "cut", cut, expected_rev=0)
    return {"cut_id": cut.id}


@router.get("", response_model=list[CutSummaryOut])
def cut_list(root: Path = Depends(get_project_root)) -> list[CutSummaryOut]:
    """Every Cut in the project (master + derived), for the cut switcher."""
    d = store_root(root) / "cuts"
    out: list[CutSummaryOut] = []
    if d.is_dir():
        # `*.undo.json` (per-cut undo/redo stacks, see store/undo.py) lives alongside the cut
        # files in this same dir -- an unqualified glob would try to read one as a Cut.
        for f in sorted(d.glob("*.json")):
            if f.name.endswith(".undo.json"):
                continue
            cut, _rev = store_module.read(root, "cut", f.stem)
            out.append(
                CutSummaryOut(
                    id=cut.id, aspect=cut.aspect, variant_label=cut.variant_label,
                    parent_cut_id=cut.parent_cut_id, passage_count=len(cut.passages),
                )
            )
    return out


@router.get("/{cut_id}", response_model=CutShowOut)
def cut_show(cut_id: str, root: Path = Depends(get_project_root)) -> CutShowOut:
    cut, revision = store_module.read(root, "cut", cut_id)
    return CutShowOut(revision=revision, cut=cut)


class CutOpRequest(BaseModel):
    name: str
    args: dict[str, Any] = {}
    expected_rev: int


@router.post("/{cut_id}/ops", response_model=CutOpResult)
def cut_op(cut_id: str, body: CutOpRequest, root: Path = Depends(get_project_root)) -> CutOpResult:
    if body.name not in _OP_NAMES:
        raise HTTPException(status_code=400, detail=f"unknown cut op {body.name!r}; known ops: {', '.join(_OP_NAMES)}")

    _current_cut, current_rev = store_module.read(root, "cut", cut_id)
    if current_rev != body.expected_rev:
        raise RevisionConflict("cut", cut_id, body.expected_rev, current_rev)

    import functools
    op_fn = functools.partial(getattr(ops_mod, body.name), **body.args)
    session = EditSession(root, cut_id)
    try:
        report = session.apply(op_fn)
    except (StoreError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _new_cut, new_rev = store_module.read(root, "cut", cut_id)
    return CutOpResult(
        cut_id=cut_id, revision=new_rev,
        report=EditReportOut(affected_spans=report.affected_spans, orphaned_spans=report.orphaned_spans),
    )


@router.post("/{cut_id}/undo")
def cut_undo(cut_id: str, root: Path = Depends(get_project_root)) -> dict:
    session = EditSession(root, cut_id)
    try:
        cut = session.undo()
    except StoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"cut_id": cut.id}


@router.post("/{cut_id}/redo")
def cut_redo(cut_id: str, root: Path = Depends(get_project_root)) -> dict:
    session = EditSession(root, cut_id)
    try:
        cut = session.redo()
    except StoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"cut_id": cut.id}


@router.get("/{cut_id}/timeline", response_model=list[TimelineSegmentOut])
def cut_timeline(cut_id: str, root: Path = Depends(get_project_root)) -> list[TimelineSegmentOut]:
    """Ordered playback segments for the monitor: which source plays, and where, per passage.
    The client never recomputes timeline maths -- it only follows this list."""
    cut, _rev = store_module.read(root, "cut", cut_id)
    transcripts = _load_all_transcripts(root)
    index = TranscriptIndex(transcripts.values())
    segments = timeline_fn(cut, index)
    audio_by_group = _audio_source_ids_by_group(_load_all_shoots(root))
    return [
        TimelineSegmentOut(
            passage_id=s.passage_id, sync_group_id=s.sync_group_id, angle_source_id=s.angle_source_id,
            audio_source_id=audio_by_group.get(s.sync_group_id, s.angle_source_id),
            source_start=s.source_start, source_end=s.source_end,
            start_frame=s.start_frame, duration_frames=s.duration_frames,
        )
        for s in segments
    ]


@router.get("/{cut_id}/swap-candidates", response_model=list[SwapCandidateOut])
def cut_swap_candidates(
    cut_id: str, sync_group_id: str, start_word_id: str, end_word_id: str,
    root: Path = Depends(get_project_root),
) -> list[SwapCandidateOut]:
    """Other word ranges (any sync group) whose text fuzzy-matches the selection, for the
    'Swap take' toolbar action. `cut_id` is accepted for routing symmetry but the search runs
    over every transcript in the project, not just this cut's passages."""
    store_module.read(root, "cut", cut_id)  # 404s if the cut doesn't exist
    transcripts = _load_all_transcripts(root)
    try:
        candidates = find_swap_candidates(list(transcripts.values()), sync_group_id, start_word_id, end_word_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [
        SwapCandidateOut(
            sync_group_id=c.sync_group_id, start_word_id=c.start_word_id, end_word_id=c.end_word_id,
            text=c.text, score=c.score,
        )
        for c in candidates
    ]


class CutDeriveRequest(BaseModel):
    parent: str
    passage_ids: list[str]
    aspect: str = "16:9"
    variant_label: Optional[str] = None


@router.post("/derive")
def cut_derive(body: CutDeriveRequest, root: Path = Depends(get_project_root)) -> dict:
    parent, _rev = store_module.read(root, "cut", body.parent)
    transcripts = _load_all_transcripts(root)
    try:
        derived, report = ops_mod.derive_cut(
            parent, transcripts.values(), body.passage_ids, _parse_aspect(body.aspect), body.variant_label or "",
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store_module.write(root, "cut", derived, expected_rev=0)
    return {
        "cut_id": derived.id, "parent_cut_id": parent.id,
        "report": {"affected_spans": report.affected_spans, "orphaned_spans": report.orphaned_spans},
    }


__all__ = ["router"]
