"""`add_span` / `remove_span`: T24's "Add visual" / "Remove" ops.

Split out of `ops.py` purely to keep that file under the project's ~400-line budget (same
reason `_reconcile.py` exists) -- there is no independent public surface here; `ops.py`
re-exports both functions.
"""
from __future__ import annotations

from typing import Optional

from ._reconcile import EditReport, TranscriptsArg, index_of
from ..model.common import WordAnchor
from ..model.cut import Brief, Cut, Span

__all__ = ["add_span", "remove_span", "add_beat_spans"]


def add_span(
    cut: Cut,
    transcripts: TranscriptsArg,
    sync_group_id: str,
    start_word_id: str,
    end_word_id: str,
    layer: str,
    kind: str,
    note: str = "",
    provenance: str = "human",
) -> tuple[Cut, EditReport]:
    """Add a word-anchored Span (picture or overlay) to the cut. Minimal op: just appends --
    callers that want "replace whatever's here" remove the overlapping span(s) first.
    `provenance="agent"` is how T13b's accepted suggestions mark themselves as machine-
    originated rather than a manual "Add visual" pick."""
    index = index_of(transcripts)
    transcript = index.transcript_for(sync_group_id)
    start_i = index.index_of(sync_group_id, start_word_id)
    end_i = index.index_of(sync_group_id, end_word_id)
    if start_i > end_i:
        raise ValueError("start_word_id must come at or before end_word_id")
    span = Span(
        layer=layer,
        kind=kind,
        note=note,
        provenance=provenance,  # type: ignore[arg-type]
        start_anchor=WordAnchor(transcript_id=transcript.id, word_id=start_word_id),
        end_anchor=WordAnchor(transcript_id=transcript.id, word_id=end_word_id),
    )
    new_cut = cut.model_copy(update={"spans": [*cut.spans, span]})
    return new_cut, EditReport()


def add_beat_spans(
    cut: Cut,
    transcripts: TranscriptsArg,
    sync_group_id: str,
    start_word_id: str,
    end_word_id: str,
    picture_kind: Optional[str] = None,
    brief_text: str = "",
    direction_note: str = "",
    flags: Optional[list[str]] = None,
    cast_refs: Optional[list[str]] = None,
    density_hint: Optional[str] = None,
    overlay_depth: Optional[str] = None,
    overlay_position: Optional[str] = None,
    provenance: str = "agent",
) -> tuple[Cut, EditReport]:
    """T30b: the automated suggester's "Accept creates both layers" op -- appends a picture
    Span (iff `picture_kind` is given) and/or an overlay Span (iff `overlay_depth`/
    `overlay_position` are given) sharing the same anchors, in one atomic cut write (so
    `Cut`'s own depth/position matrix validator, which needs the sibling picture span
    present to check an overlay against, sees both at once rather than racing a two-step
    apply). At least one of the two must be given."""
    if picture_kind is None and overlay_depth is None:
        raise ValueError("add_beat_spans: must add a picture and/or an overlay span")
    index = index_of(transcripts)
    transcript = index.transcript_for(sync_group_id)
    start_i = index.index_of(sync_group_id, start_word_id)
    end_i = index.index_of(sync_group_id, end_word_id)
    if start_i > end_i:
        raise ValueError("start_word_id must come at or before end_word_id")

    start_anchor = WordAnchor(transcript_id=transcript.id, word_id=start_word_id)
    end_anchor = WordAnchor(transcript_id=transcript.id, word_id=end_word_id)
    brief = Brief(text=brief_text, provenance="agent" if provenance == "agent" else "human")

    new_spans = list(cut.spans)
    if picture_kind is not None:
        new_spans.append(Span(
            layer="picture", kind=picture_kind, provenance=provenance,  # type: ignore[arg-type]
            start_anchor=start_anchor, end_anchor=end_anchor, brief=brief,
            direction_note=direction_note, flags=flags or [], cast_refs=cast_refs or [],
            density_hint=density_hint,
        ))
    if overlay_depth is not None:
        new_spans.append(Span(
            layer="overlay", kind="overlay", provenance=provenance,  # type: ignore[arg-type]
            start_anchor=start_anchor, end_anchor=end_anchor, brief=brief,
            overlay_depth=overlay_depth, overlay_position=overlay_position,  # type: ignore[arg-type]
        ))
    new_cut = cut.model_copy(update={"spans": new_spans})
    return new_cut, EditReport()


def remove_span(cut: Cut, transcripts: TranscriptsArg, span_id: str) -> tuple[Cut, EditReport]:
    """Remove a span by id (undo-able the same way any other op is: `EditSession.undo()`)."""
    index_of(transcripts)  # validate the transcripts arg the same way every op does
    new_spans = [s for s in cut.spans if s.id != span_id]
    if len(new_spans) == len(cut.spans):
        raise ValueError(f"No span {span_id!r} in cut")
    new_cut = cut.model_copy(update={"spans": new_spans})
    return new_cut, EditReport()
