"""Cross-object invariants for Cut, checked on every write (per docs/tasks/T02.md).

These can't live on the Cut model alone because they need the referenced Transcripts:
  - passages reference existing words, in order (start_word at or before end_word)
  - spans on the same layer do not overlap
  - anchors (Span start/end, on a Transcript) resolve to real words
"""
from __future__ import annotations

from ..model.cut import Cut, Passage, Span, valid_overlay_positions
from ..model.transcript import Transcript
from .errors import InvariantError


def _word_index(transcript: Transcript) -> dict[str, int]:
    return {word.id: i for i, word in enumerate(transcript.words)}


def _transcript_for_sync_group(sync_group_id: str, transcripts: dict[str, Transcript]) -> Transcript | None:
    for transcript in transcripts.values():
        if transcript.sync_group_id == sync_group_id:
            return transcript
    return None


def _check_passage(passage: Passage, transcripts: dict[str, Transcript]) -> None:
    transcript = _transcript_for_sync_group(passage.sync_group_id, transcripts)
    if transcript is None:
        raise InvariantError(
            f"Passage {passage.id!r}: no transcript found for sync_group_id {passage.sync_group_id!r}"
        )
    index = _word_index(transcript)
    start_idx = index.get(passage.start_word_id)
    end_idx = index.get(passage.end_word_id)
    if start_idx is None:
        raise InvariantError(f"Passage {passage.id!r}: start_word_id {passage.start_word_id!r} not in transcript")
    if end_idx is None:
        raise InvariantError(f"Passage {passage.id!r}: end_word_id {passage.end_word_id!r} not in transcript")
    if start_idx > end_idx:
        raise InvariantError(f"Passage {passage.id!r}: start_word_id must come at or before end_word_id")


def _resolve_anchor_time(span: Span, transcripts: dict[str, Transcript], which: str) -> float:
    anchor = span.start_anchor if which == "start" else span.end_anchor
    transcript = transcripts.get(anchor.transcript_id)
    if transcript is None:
        raise InvariantError(f"Span {span.id!r}: {which}_anchor transcript_id {anchor.transcript_id!r} not found")
    index = _word_index(transcript)
    word_idx = index.get(anchor.word_id)
    if word_idx is None:
        raise InvariantError(f"Span {span.id!r}: {which}_anchor word_id {anchor.word_id!r} not in transcript")
    word = transcript.words[word_idx]
    return word.start if which == "start" else word.end


def _check_span_anchors(span: Span, transcripts: dict[str, Transcript]) -> tuple[float, float]:
    start_time = _resolve_anchor_time(span, transcripts, "start")
    end_time = _resolve_anchor_time(span, transcripts, "end")
    if end_time < start_time:
        raise InvariantError(f"Span {span.id!r}: end_anchor resolves before start_anchor")
    return start_time, end_time


def _check_spans_no_overlap(spans: list[Span], transcripts: dict[str, Transcript]) -> None:
    by_layer: dict[str, list[tuple[float, float, str]]] = {}
    for span in spans:
        start_time, end_time = _check_span_anchors(span, transcripts)
        by_layer.setdefault(span.layer, []).append((start_time, end_time, span.id))
    for layer, ranges in by_layer.items():
        ranges.sort(key=lambda r: r[0])
        for previous, current in zip(ranges, ranges[1:]):
            if current[0] < previous[1]:
                raise InvariantError(
                    f"Spans {previous[2]!r} and {current[2]!r} overlap on layer {layer!r}"
                )


def _check_overlay_matrix(spans: list[Span]) -> None:
    """T30c hardening: `Cut._overlay_depth_position_matrix` (model/cut.py) is a pydantic
    `model_validator`, which only runs on construction/parsing -- `Cut.model_copy(update=...)`
    (what every `post_core.edit` op builds its result with, `add_beat_spans` included) never
    re-triggers it. Without this, an op that lands an illegal depth/position pairing writes it
    straight to disk uncaught, and the *next* read of that cut 500s trying to re-parse it
    ("refused to read corrupt file") -- discovered via this slice's own "Add visual" dialog
    test. Re-checked here, on the one path (`EditSession.apply`) every op's result already
    goes through before `store.write`, so it's caught before it ever reaches disk."""
    def _key(span: Span) -> tuple:
        return (span.start_anchor.transcript_id, span.start_anchor.word_id, span.end_anchor.transcript_id, span.end_anchor.word_id)

    by_anchors: dict[tuple, Span] = {}
    for span in spans:
        if span.layer == "picture":
            by_anchors[_key(span)] = span
    for span in spans:
        if span.layer != "overlay" or span.overlay_depth is None:
            continue
        picture = by_anchors.get(_key(span))
        if picture is None:
            continue
        allowed = valid_overlay_positions(picture.kind, span.overlay_depth)
        if span.overlay_position not in allowed:
            raise InvariantError(
                f"Span {span.id!r}: overlay position {span.overlay_position!r} invalid for "
                f"depth={span.overlay_depth!r} over picture kind {picture.kind!r} (allowed: {sorted(allowed)})"
            )


def validate_cut_invariants(cut: Cut, transcripts: dict[str, Transcript]) -> None:
    """Raise InvariantError if `cut` violates a cross-object invariant.

    `transcripts` maps transcript_id -> Transcript, and must include every transcript
    referenced (directly by Span anchors, or by sync_group_id for Passages) by this cut.
    """
    for passage in cut.passages:
        _check_passage(passage, transcripts)
    _check_spans_no_overlap(cut.spans, transcripts)
    _check_overlay_matrix(cut.spans)
