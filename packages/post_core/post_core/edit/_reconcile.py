"""Shared plumbing for `ops.py`: span reconciliation and passage-list normalisation.

Private to the `edit` package (leading underscore) -- `ops.py` re-exports the pieces other
modules need (`EditReport`, `merge_adjacent`). Split out purely to keep `ops.py` under the
project's ~400-line file budget; there is no independent public surface here.
"""
from __future__ import annotations

from typing import Iterable, Union

from ..model.common import WordAnchor
from ..model.cut import Cut, Passage, Section, Span, Trim
from ..model.transcript import Transcript
from .ranges import TranscriptIndex

TranscriptsArg = Union[TranscriptIndex, Iterable[Transcript]]


class EditReport:
    """What an op changed about spans. `affected_spans` shrank or un-orphaned; `orphaned_spans`
    lost every word they anchored to (kept in the cut, but flagged)."""

    __slots__ = ("affected_spans", "orphaned_spans")

    def __init__(self, affected_spans: list[str] | None = None, orphaned_spans: list[str] | None = None):
        self.affected_spans = affected_spans or []
        self.orphaned_spans = orphaned_spans or []

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EditReport):
            return NotImplemented
        return self.affected_spans == other.affected_spans and self.orphaned_spans == other.orphaned_spans

    def __repr__(self) -> str:
        return f"EditReport(affected_spans={self.affected_spans!r}, orphaned_spans={self.orphaned_spans!r})"


def index_of(transcripts: TranscriptsArg) -> TranscriptIndex:
    if isinstance(transcripts, TranscriptIndex):
        return transcripts
    return TranscriptIndex(transcripts)


def covered_word_ids(passages: list[Passage], index: TranscriptIndex) -> dict[str, set[str]]:
    covered: dict[str, set[str]] = {}
    for passage in passages:
        ids = index.word_ids_between(passage.sync_group_id, passage.start_word_id, passage.end_word_id)
        covered.setdefault(passage.sync_group_id, set()).update(ids)
    return covered


def reconcile_spans(
    spans: list[Span], index: TranscriptIndex, covered: dict[str, set[str]]
) -> tuple[list[Span], EditReport]:
    new_spans: list[Span] = []
    affected: list[str] = []
    orphaned: list[str] = []
    for span in spans:
        if span.start_anchor.transcript_id != span.end_anchor.transcript_id:
            new_spans.append(span)  # cross-transcript span: not our shrink/orphan model, leave alone
            continue
        try:
            sync_group_id = index.sync_group_of(span.start_anchor.transcript_id)
            word_ids = index.word_ids_between(sync_group_id, span.start_anchor.word_id, span.end_anchor.word_id)
        except KeyError:
            new_spans.append(span)
            continue
        present = [wid for wid in word_ids if wid in covered.get(sync_group_id, set())]
        if not present:
            if not span.orphaned:
                span = span.model_copy(update={"orphaned": True})
            orphaned.append(span.id)
            new_spans.append(span)
            continue
        new_start, new_end = present[0], present[-1]
        changed = span.orphaned or new_start != span.start_anchor.word_id or new_end != span.end_anchor.word_id
        if changed:
            span = span.model_copy(
                update={
                    "orphaned": False,
                    "start_anchor": WordAnchor(transcript_id=span.start_anchor.transcript_id, word_id=new_start),
                    "end_anchor": WordAnchor(transcript_id=span.end_anchor.transcript_id, word_id=new_end),
                }
            )
            affected.append(span.id)
        new_spans.append(span)
    return new_spans, EditReport(affected_spans=affected, orphaned_spans=orphaned)


def rewrite_sections(sections: list[Section], id_map: dict[str, list[str]]) -> list[Section]:
    new_sections = []
    for section in sections:
        new_ids: list[str] = []
        for pid in section.passage_ids:
            new_ids.extend(id_map.get(pid, [pid]))
        new_sections.append(section.model_copy(update={"passage_ids": new_ids}))
    return new_sections


def finalize(
    cut: Cut, new_passages: list[Passage], new_sections: list[Section], index: TranscriptIndex
) -> tuple[Cut, EditReport]:
    covered = covered_word_ids(new_passages, index)
    new_spans, report = reconcile_spans(cut.spans, index, covered)
    new_cut = cut.model_copy(update={"passages": new_passages, "sections": new_sections, "spans": new_spans})
    new_cut = merge_adjacent(new_cut, index)
    return new_cut, report


def _mergeable(a: Passage, b: Passage, index: TranscriptIndex) -> bool:
    if a.sync_group_id != b.sync_group_id or a.angle_source_id != b.angle_source_id:
        return False
    if a.trims.tail != 0.0 or b.trims.head != 0.0:
        return False
    if a.framing != b.framing:
        return False
    a_end_i = index.index_of(a.sync_group_id, a.end_word_id)
    b_start_i = index.index_of(b.sync_group_id, b.start_word_id)
    return b_start_i == a_end_i + 1


def merge_adjacent(cut: Cut, transcripts: TranscriptsArg) -> Cut:
    """Adjacent passages, contiguous in the same transcript with the same angle and framing
    and no boundary trim, merge into one. Run after every structural op."""
    index = index_of(transcripts)
    if not cut.passages:
        return cut
    merged: list[Passage] = [cut.passages[0]]
    id_map: dict[str, str] = {cut.passages[0].id: cut.passages[0].id}
    for passage in cut.passages[1:]:
        prev = merged[-1]
        if _mergeable(prev, passage, index):
            merged[-1] = Passage(
                id=prev.id,
                sync_group_id=prev.sync_group_id,
                start_word_id=prev.start_word_id,
                end_word_id=passage.end_word_id,
                trims=Trim(head=prev.trims.head, tail=passage.trims.tail),
                angle_source_id=prev.angle_source_id,
                framing=prev.framing,
            )
            id_map[passage.id] = prev.id
        else:
            merged.append(passage)
            id_map[passage.id] = passage.id
    new_sections = []
    for section in cut.sections:
        seen: list[str] = []
        for pid in section.passage_ids:
            mapped = id_map.get(pid, pid)
            if mapped not in seen:
                seen.append(mapped)
        new_sections.append(section.model_copy(update={"passage_ids": seen}))
    return cut.model_copy(update={"passages": merged, "sections": new_sections})
