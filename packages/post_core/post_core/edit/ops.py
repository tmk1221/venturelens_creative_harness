"""Pure `Cut -> Cut` edit operations, addressed entirely by word ids.

Every op takes the current `Cut` plus a `TranscriptIndex` (or an iterable of `Transcript` --
`_index()` accepts either) and returns `(new_cut, EditReport)`. Nothing here touches disk;
`session.py` is the only place that persists a result. Word ids never change meaning: a
Transcript's words are permanent, so "deleting" a word range only removes it from Passage
coverage -- it can always be pulled back in with `insert_range` / `restore_words`.

Span behaviour: spans anchor to words (`WordAnchor`), not to passages. After every op the
spans are reconciled against whatever words are currently covered by the cut's passages:
a span whose anchor words are still (at least partially) covered keeps `orphaned=False`
and, if only some of its words survive, shrinks to the surviving sub-range; a span with no
surviving words is kept but marked `orphaned=True` and reported. `merge_adjacent` then
normalises the passage list (contiguous, same-angle, same-framing, no-inner-trim passages
collapse into one) after every structural op. The reconciliation/merge machinery lives in
`_reconcile.py` to keep this file under the project's file-size budget.
"""
from __future__ import annotations

from typing import Optional

from ._reconcile import EditReport, TranscriptsArg, finalize, index_of, merge_adjacent, rewrite_sections
from ._spans import add_beat_spans, add_span, remove_span
from ..model.common import Rational, WordAnchor
from ..model.cut import Cut, Passage, Trim
from ..model.transcript import Transcript
from .ranges import TranscriptIndex

__all__ = [
    "EditReport",
    "merge_adjacent",
    "cut_from_transcript",
    "delete_words",
    "restore_words",
    "insert_range",
    "move_passage",
    "move_words",
    "replace_range_with",
    "set_angle",
    "set_trim",
    "derive_cut",
    "add_span",
    "add_beat_spans",
    "remove_span",
]


# --- construction -------------------------------------------------------------------------

def cut_from_transcript(transcript: Transcript, angle_source_id: str, aspect: Rational) -> Cut:
    """One passage over every word of `transcript`, played through `angle_source_id`."""
    if not transcript.words:
        return Cut(aspect=aspect)
    passage = Passage(
        sync_group_id=transcript.sync_group_id,
        start_word_id=transcript.words[0].id,
        end_word_id=transcript.words[-1].id,
        angle_source_id=angle_source_id,
    )
    return Cut(aspect=aspect, passages=[passage])


# --- delete / restore ----------------------------------------------------------------------

def _split_passage_removing_range(
    passage: Passage, index: TranscriptIndex, del_start_i: int, del_end_i: int
) -> list[Passage]:
    p_start_i = index.index_of(passage.sync_group_id, passage.start_word_id)
    p_end_i = index.index_of(passage.sync_group_id, passage.end_word_id)
    if del_end_i < p_start_i or del_start_i > p_end_i:
        return [passage]  # no overlap: untouched
    words = index.words(passage.sync_group_id)
    result: list[Passage] = []
    if del_start_i > p_start_i:
        head_end_i = del_start_i - 1
        result.append(
            Passage(
                sync_group_id=passage.sync_group_id,
                start_word_id=words[p_start_i].id,
                end_word_id=words[head_end_i].id,
                trims=Trim(head=passage.trims.head, tail=0.0),
                angle_source_id=passage.angle_source_id,
                framing=passage.framing,
            )
        )
    if del_end_i < p_end_i:
        tail_start_i = del_end_i + 1
        result.append(
            Passage(
                sync_group_id=passage.sync_group_id,
                start_word_id=words[tail_start_i].id,
                end_word_id=words[p_end_i].id,
                trims=Trim(head=0.0, tail=passage.trims.tail),
                angle_source_id=passage.angle_source_id,
                framing=passage.framing,
            )
        )
    return result


def delete_words(
    cut: Cut, transcripts: TranscriptsArg, sync_group_id: str, start_word_id: str, end_word_id: str
) -> tuple[Cut, EditReport]:
    """Remove a word range from every passage that covers it, splitting as needed."""
    index = index_of(transcripts)
    del_start_i = index.index_of(sync_group_id, start_word_id)
    del_end_i = index.index_of(sync_group_id, end_word_id)
    if del_start_i > del_end_i:
        raise ValueError("start_word_id must come at or before end_word_id")

    new_passages: list[Passage] = []
    id_map: dict[str, list[str]] = {}
    for passage in cut.passages:
        if passage.sync_group_id != sync_group_id:
            new_passages.append(passage)
            id_map[passage.id] = [passage.id]
            continue
        pieces = _split_passage_removing_range(passage, index, del_start_i, del_end_i)
        if len(pieces) == 1 and pieces[0].id == passage.id:
            new_passages.append(passage)
            id_map[passage.id] = [passage.id]
        else:
            new_passages.extend(pieces)
            id_map[passage.id] = [p.id for p in pieces]

    new_sections = rewrite_sections(cut.sections, id_map)
    return finalize(cut, new_passages, new_sections, index)


def insert_range(
    cut: Cut,
    transcripts: TranscriptsArg,
    transcript_id: str,
    start_word_id: str,
    end_word_id: str,
    angle_source_id: str,
    at: int,
) -> tuple[Cut, EditReport]:
    """Pull a take (any word range from any sync group) into the cut at passage index `at`."""
    index = index_of(transcripts)
    sync_group_id = index.sync_group_of(transcript_id)
    start_i = index.index_of(sync_group_id, start_word_id)
    end_i = index.index_of(sync_group_id, end_word_id)
    if start_i > end_i:
        raise ValueError("start_word_id must come at or before end_word_id")
    passage = Passage(
        sync_group_id=sync_group_id, start_word_id=start_word_id, end_word_id=end_word_id,
        angle_source_id=angle_source_id,
    )
    at = max(0, min(at, len(cut.passages)))
    new_passages = list(cut.passages[:at]) + [passage] + list(cut.passages[at:])
    return finalize(cut, new_passages, cut.sections, index)


def restore_words(
    cut: Cut,
    transcripts: TranscriptsArg,
    sync_group_id: str,
    angle_source_id: str,
    start_word_id: str,
    end_word_id: str,
    at: int,
) -> tuple[Cut, EditReport]:
    """Re-insert a word range previously removed by `delete_words`.

    The semantic inverse of `delete_words` when `at` is the passage index the range
    occupied before deletion -- delete then restore at that index is an identity op
    (after `merge_adjacent` normalisation).
    """
    index = index_of(transcripts)
    transcript = index.transcript_for(sync_group_id)
    return insert_range(cut, index, transcript.id, start_word_id, end_word_id, angle_source_id, at)


# --- move ------------------------------------------------------------------------------

def move_passage(cut: Cut, transcripts: TranscriptsArg, passage_id: str, at: int) -> tuple[Cut, EditReport]:
    """Reposition a whole passage to list index `at`. Spans are untouched (they anchor to
    words, not list position) but re-reconciled for consistency."""
    index = index_of(transcripts)
    passages = list(cut.passages)
    pos = next((i for i, p in enumerate(passages) if p.id == passage_id), None)
    if pos is None:
        raise ValueError(f"No passage {passage_id!r} in cut")
    passage = passages.pop(pos)
    at = max(0, min(at, len(passages)))
    passages.insert(at, passage)
    return finalize(cut, passages, cut.sections, index)


def _position_before_anchor(cut: Cut, index: TranscriptIndex, before_word: Optional[WordAnchor]) -> int:
    if before_word is None:
        return len(cut.passages)
    for i, p in enumerate(cut.passages):
        transcript = index.transcript_for(p.sync_group_id)
        if transcript.id != before_word.transcript_id:
            continue
        p_start = index.index_of(p.sync_group_id, p.start_word_id)
        p_end = index.index_of(p.sync_group_id, p.end_word_id)
        try:
            word_i = index.index_of(p.sync_group_id, before_word.word_id)
        except KeyError:
            continue
        if p_start <= word_i <= p_end:
            return i
    return len(cut.passages)


def move_words(
    cut: Cut,
    transcripts: TranscriptsArg,
    sync_group_id: str,
    start_word_id: str,
    end_word_id: str,
    before_word: Optional[WordAnchor] = None,
) -> tuple[Cut, EditReport]:
    """Move a word range (with whichever angle currently plays it) to just before `before_word`
    (end of the cut if None)."""
    index = index_of(transcripts)
    start_i = index.index_of(sync_group_id, start_word_id)
    angle_source_id = None
    for p in cut.passages:
        if p.sync_group_id != sync_group_id:
            continue
        p_start = index.index_of(sync_group_id, p.start_word_id)
        p_end = index.index_of(sync_group_id, p.end_word_id)
        if p_start <= start_i <= p_end:
            angle_source_id = p.angle_source_id
            break
    if angle_source_id is None:
        raise ValueError("word range is not currently covered by any passage in the cut")

    deleted_cut, _ = delete_words(cut, index, sync_group_id, start_word_id, end_word_id)
    at = _position_before_anchor(deleted_cut, index, before_word)
    transcript = index.transcript_for(sync_group_id)
    return insert_range(deleted_cut, index, transcript.id, start_word_id, end_word_id, angle_source_id, at)


# --- replace / re-angle / trim ----------------------------------------------------------

def _passage_list_index_for_range(cut: Cut, index: TranscriptIndex, sync_group_id: str, start_word_id: str) -> int:
    start_i = index.index_of(sync_group_id, start_word_id)
    for i, p in enumerate(cut.passages):
        if p.sync_group_id != sync_group_id:
            continue
        p_start = index.index_of(sync_group_id, p.start_word_id)
        p_end = index.index_of(sync_group_id, p.end_word_id)
        if p_start <= start_i <= p_end:
            return i
    raise ValueError("range is not covered by any passage in the cut")


def replace_range_with(
    cut: Cut,
    transcripts: TranscriptsArg,
    sync_group_id: str,
    start_word_id: str,
    end_word_id: str,
    other_sync_group_id: str,
    other_start_word_id: str,
    other_end_word_id: str,
    other_angle_source_id: str,
) -> tuple[Cut, EditReport]:
    """Swap a take: replace the passage segment covering `range` with a passage built from
    `other range` (any sync group), landing in the same list position."""
    index = index_of(transcripts)
    at = _passage_list_index_for_range(cut, index, sync_group_id, start_word_id)
    deleted_cut, _ = delete_words(cut, index, sync_group_id, start_word_id, end_word_id)
    other_transcript = index.transcript_for(other_sync_group_id)
    return insert_range(
        deleted_cut, index, other_transcript.id, other_start_word_id, other_end_word_id, other_angle_source_id, at
    )


def set_angle(
    cut: Cut,
    transcripts: TranscriptsArg,
    sync_group_id: str,
    start_word_id: str,
    end_word_id: str,
    new_angle_source_id: str,
) -> tuple[Cut, EditReport]:
    """Change the angle (Source) for a word range, splitting passages as needed. Only the
    targeted range's angle changes -- nothing else about the cut moves."""
    index = index_of(transcripts)
    start_i = index.index_of(sync_group_id, start_word_id)
    end_i = index.index_of(sync_group_id, end_word_id)
    if start_i > end_i:
        raise ValueError("start_word_id must come at or before end_word_id")
    words = index.words(sync_group_id)

    new_passages: list[Passage] = []
    id_map: dict[str, list[str]] = {}
    for passage in cut.passages:
        if passage.sync_group_id != sync_group_id:
            new_passages.append(passage)
            id_map[passage.id] = [passage.id]
            continue
        p_start = index.index_of(sync_group_id, passage.start_word_id)
        p_end = index.index_of(sync_group_id, passage.end_word_id)
        if end_i < p_start or start_i > p_end:
            new_passages.append(passage)
            id_map[passage.id] = [passage.id]
            continue

        overlap_start = max(p_start, start_i)
        overlap_end = min(p_end, end_i)
        pieces: list[Passage] = []
        if overlap_start > p_start:
            pieces.append(
                Passage(
                    sync_group_id=sync_group_id,
                    start_word_id=words[p_start].id,
                    end_word_id=words[overlap_start - 1].id,
                    trims=Trim(head=passage.trims.head, tail=0.0),
                    angle_source_id=passage.angle_source_id,
                    framing=passage.framing,
                )
            )
        pieces.append(
            Passage(
                sync_group_id=sync_group_id,
                start_word_id=words[overlap_start].id,
                end_word_id=words[overlap_end].id,
                trims=Trim(
                    head=passage.trims.head if overlap_start == p_start else 0.0,
                    tail=passage.trims.tail if overlap_end == p_end else 0.0,
                ),
                angle_source_id=new_angle_source_id,
                framing=passage.framing,
            )
        )
        if overlap_end < p_end:
            pieces.append(
                Passage(
                    sync_group_id=sync_group_id,
                    start_word_id=words[overlap_end + 1].id,
                    end_word_id=words[p_end].id,
                    trims=Trim(head=0.0, tail=passage.trims.tail),
                    angle_source_id=passage.angle_source_id,
                    framing=passage.framing,
                )
            )
        new_passages.extend(pieces)
        id_map[passage.id] = [p.id for p in pieces]

    new_sections = rewrite_sections(cut.sections, id_map)
    return finalize(cut, new_passages, new_sections, index)


def set_trim(cut: Cut, transcripts: TranscriptsArg, passage_id: str, head: float, tail: float) -> tuple[Cut, EditReport]:
    """Set a passage's head/tail trim (extra seconds cut from its word range)."""
    index = index_of(transcripts)
    new_passages = []
    found = False
    for p in cut.passages:
        if p.id == passage_id:
            found = True
            new_passages.append(p.model_copy(update={"trims": Trim(head=head, tail=tail)}))
        else:
            new_passages.append(p)
    if not found:
        raise ValueError(f"No passage {passage_id!r} in cut")
    return finalize(cut, new_passages, cut.sections, index)


# --- shorts ------------------------------------------------------------------------------

def derive_cut(
    parent: Cut, transcripts: TranscriptsArg, passage_ids: list[str], aspect: Rational, variant_label: str = ""
) -> tuple[Cut, EditReport]:
    """A new Cut over a subset of `parent`'s passages (e.g. a short), sharing word ids and
    spans with the parent. Spans are reconciled (shrunk/orphaned) against the subset."""
    from ._reconcile import covered_word_ids, reconcile_spans  # local: only derive_cut needs these directly

    index = index_of(transcripts)
    by_id = {p.id: p for p in parent.passages}
    missing = [pid for pid in passage_ids if pid not in by_id]
    if missing:
        raise ValueError(f"parent cut has no passages {missing!r}")
    passages = [by_id[pid].model_copy(deep=True) for pid in passage_ids]
    passage_id_set = set(passage_ids)
    sections = [
        s.model_copy(update={"passage_ids": [pid for pid in s.passage_ids if pid in passage_id_set]})
        for s in parent.sections
    ]
    draft = Cut(
        aspect=aspect,
        parent_cut_id=parent.id,
        variant_label=variant_label,
        passages=passages,
        spans=[s.model_copy(deep=True) for s in parent.spans],
        sections=sections,
    )
    covered = covered_word_ids(passages, index)
    new_spans, report = reconcile_spans(draft.spans, index, covered)
    result = draft.model_copy(update={"spans": new_spans})
    result = merge_adjacent(result, index)
    return result, report
