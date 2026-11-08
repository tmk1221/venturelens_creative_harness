"""Span -> timeline-frame-range mapping.

`edit.ranges.time_of` maps a `WordAnchor` to the frame where that word *starts* playing --
exactly what V1/word-follow needs, but a Span's `end_anchor` needs the frame where its last
word *ends*, which `ranges.py` has no public helper for. Rather than touch `ranges.py`
beyond its T09 fps carry-over, this mirrors `time_of`'s own logic locally, parameterized on
word start vs. word end, using only `ranges.py`'s public `timeline()`/`TranscriptIndex`.
"""
from __future__ import annotations

from typing import Optional

from ..edit.ranges import TranscriptIndex, timeline
from ..model.common import Rational, WordAnchor
from ..model.cut import Cut, Span


def _frame_for_word(
    cut: Cut, index: TranscriptIndex, fps: Rational, anchor: WordAnchor, *, at_end: bool
) -> Optional[int]:
    for seg, passage in zip(timeline(cut, index, fps), cut.passages):
        transcript = index.transcript_for(passage.sync_group_id)
        if transcript.id != anchor.transcript_id:
            continue
        start_i = index.index_of(passage.sync_group_id, passage.start_word_id)
        end_i = index.index_of(passage.sync_group_id, passage.end_word_id)
        try:
            word_i = index.index_of(passage.sync_group_id, anchor.word_id)
        except KeyError:
            continue
        if start_i <= word_i <= end_i:
            word = index.words(passage.sync_group_id)[word_i]
            span_secs = seg.source_end - seg.source_start
            reference = word.end if at_end else word.start
            frac = 0.0 if span_secs <= 0 else (reference - seg.source_start) / span_secs
            return seg.start_frame + round(frac * seg.duration_frames)
    return None


def span_frame_range(
    cut: Cut, index: TranscriptIndex, fps: Rational, span: Span
) -> Optional[tuple[int, int]]:
    """`(start_frame, duration_frames)` for `span` on the current timeline, or `None` if
    its anchors no longer resolve to a surviving word (i.e. it is orphaned)."""
    start_frame = _frame_for_word(cut, index, fps, span.start_anchor, at_end=False)
    if start_frame is None:
        return None
    end_frame = _frame_for_word(cut, index, fps, span.end_anchor, at_end=True)
    if end_frame is None:
        return None
    duration = max(1, end_frame - start_frame)
    return start_frame, duration
