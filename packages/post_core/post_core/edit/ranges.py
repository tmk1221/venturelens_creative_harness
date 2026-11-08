"""Passages -> keep ranges and timeline time. The ONLY place timeline time is computed.

`TranscriptIndex` is a fast lookup over a set of Transcripts, shared by `ops.py` and by the
functions here. `keep_ranges` turns a Cut's passages into merged source-second ranges per
sync group (for conform / render). `timeline` turns a Cut's passages into ordered, rational
timeline segments at a given fps -- frame boundaries are computed by a running cumulative
rounding so segment durations always sum exactly to the rounded total, regardless of any
individual segment's fractional-frame duration. `word_at` / `time_of` map between timeline
frames and transcript words, for playback-follow.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from ..model.common import Rational, WordAnchor
from ..model.cut import Cut, Passage
from ..model.transcript import Transcript, Word

DEFAULT_MERGE_GAP = 0.35  # seconds
DEFAULT_HANDLE = 0.0  # seconds, extra padding pulled in on each side of a keep range


class TranscriptIndex:
    """Word-id lookups over a set of Transcripts, keyed by sync_group_id and transcript_id."""

    def __init__(self, transcripts: Iterable[Transcript]):
        self._by_sync_group: dict[str, Transcript] = {}
        self._by_transcript_id: dict[str, Transcript] = {}
        self._word_pos: dict[tuple[str, str], int] = {}
        for t in transcripts:
            self._by_sync_group[t.sync_group_id] = t
            self._by_transcript_id[t.id] = t
            for i, w in enumerate(t.words):
                self._word_pos[(t.sync_group_id, w.id)] = i

    def transcript_for(self, sync_group_id: str) -> Transcript:
        try:
            return self._by_sync_group[sync_group_id]
        except KeyError:
            raise KeyError(f"No transcript for sync_group_id {sync_group_id!r}") from None

    def transcript_by_id(self, transcript_id: str) -> Transcript:
        try:
            return self._by_transcript_id[transcript_id]
        except KeyError:
            raise KeyError(f"No transcript with id {transcript_id!r}") from None

    def sync_group_of(self, transcript_id: str) -> str:
        return self.transcript_by_id(transcript_id).sync_group_id

    def words(self, sync_group_id: str) -> list[Word]:
        return self.transcript_for(sync_group_id).words

    def index_of(self, sync_group_id: str, word_id: str) -> int:
        try:
            return self._word_pos[(sync_group_id, word_id)]
        except KeyError:
            raise KeyError(f"word {word_id!r} not found in sync_group {sync_group_id!r}") from None

    def word_ids_between(self, sync_group_id: str, start_word_id: str, end_word_id: str) -> list[str]:
        start_i = self.index_of(sync_group_id, start_word_id)
        end_i = self.index_of(sync_group_id, end_word_id)
        if start_i > end_i:
            raise ValueError("start_word_id must come at or before end_word_id")
        return [w.id for w in self.words(sync_group_id)[start_i : end_i + 1]]


def passage_source_range(passage: Passage, index: TranscriptIndex) -> tuple[float, float]:
    """The passage's (start, end) in source seconds, trims applied."""
    words = index.words(passage.sync_group_id)
    start_i = index.index_of(passage.sync_group_id, passage.start_word_id)
    end_i = index.index_of(passage.sync_group_id, passage.end_word_id)
    start = words[start_i].start + passage.trims.head
    end = words[end_i].end - passage.trims.tail
    if end < start:
        end = start
    return start, end


@dataclass(frozen=True)
class KeepRange:
    sync_group_id: str
    start: float
    end: float


def keep_ranges(
    cut: Cut,
    index: TranscriptIndex,
    merge_gap: float = DEFAULT_MERGE_GAP,
    handle: float = DEFAULT_HANDLE,
) -> dict[str, list[KeepRange]]:
    """Merged source-second ranges to keep, per sync group, for conform/render."""
    by_group: dict[str, list[tuple[float, float]]] = {}
    for passage in cut.passages:
        start, end = passage_source_range(passage, index)
        start = max(0.0, start - handle)
        end = end + handle
        by_group.setdefault(passage.sync_group_id, []).append((start, end))
    result: dict[str, list[KeepRange]] = {}
    for sync_group_id, spans in by_group.items():
        spans.sort(key=lambda r: r[0])
        merged: list[list[float]] = []
        for start, end in spans:
            if merged and start - merged[-1][1] <= merge_gap:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        result[sync_group_id] = [KeepRange(sync_group_id, s, e) for s, e in merged]
    return result


@dataclass(frozen=True)
class TimelineSegment:
    passage_id: str
    sync_group_id: str
    angle_source_id: str
    source_start: float
    source_end: float
    start_frame: int
    duration_frames: int


def timeline(cut: Cut, index: TranscriptIndex, fps: Optional[Rational] = None) -> list[TimelineSegment]:
    """Ordered timeline segments, one per passage, with derived start/duration in frames.

    Frame boundaries are cumulative-rounded (not each segment rounded independently), so
    `sum(seg.duration_frames) == round(total_source_seconds * fps)` always holds exactly.
    `fps` defaults to `cut.fps` and is otherwise an override (e.g. for previewing a cut at
    a different delivery rate).
    """
    fps = fps if fps is not None else cut.fps
    fps_f = fps.as_float()
    segments: list[TimelineSegment] = []
    cumulative_seconds = 0.0
    frame_cursor = 0
    for passage in cut.passages:
        start, end = passage_source_range(passage, index)
        cumulative_seconds += max(0.0, end - start)
        next_frame_cursor = round(cumulative_seconds * fps_f)
        duration_frames = next_frame_cursor - frame_cursor
        segments.append(
            TimelineSegment(
                passage_id=passage.id,
                sync_group_id=passage.sync_group_id,
                angle_source_id=passage.angle_source_id,
                source_start=start,
                source_end=end,
                start_frame=frame_cursor,
                duration_frames=duration_frames,
            )
        )
        frame_cursor = next_frame_cursor
    return segments


def _word_at_source_time(passage: Passage, index: TranscriptIndex, source_time: float) -> Optional[Word]:
    start_i = index.index_of(passage.sync_group_id, passage.start_word_id)
    end_i = index.index_of(passage.sync_group_id, passage.end_word_id)
    words = index.words(passage.sync_group_id)[start_i : end_i + 1]
    for word in words:
        if word.start <= source_time <= word.end:
            return word
    if not words:
        return None
    return min(words, key=lambda w: min(abs(w.start - source_time), abs(w.end - source_time)))


def word_at(
    cut: Cut,
    index: TranscriptIndex,
    fps: Optional[Rational] = None,
    timeline_frame: Optional[int] = None,
) -> Optional[WordAnchor]:
    """The word playing at `timeline_frame`, or None if the frame falls outside the cut.

    `fps` defaults to `cut.fps` (pass an explicit value to override). `timeline_frame` is
    required (kept as a plain default of `None` only so `fps` can precede it and still
    default); omitting it raises `TypeError`.
    """
    if timeline_frame is None:
        raise TypeError("word_at() missing required argument: 'timeline_frame'")
    fps = fps if fps is not None else cut.fps
    for seg, passage in zip(timeline(cut, index, fps), cut.passages):
        if seg.start_frame <= timeline_frame < seg.start_frame + max(1, seg.duration_frames):
            if seg.duration_frames <= 0:
                frac = 0.0
            else:
                frac = (timeline_frame - seg.start_frame) / seg.duration_frames
            source_time = seg.source_start + frac * (seg.source_end - seg.source_start)
            word = _word_at_source_time(passage, index, source_time)
            if word is not None:
                transcript = index.transcript_for(passage.sync_group_id)
                return WordAnchor(transcript_id=transcript.id, word_id=word.id)
    return None


def time_of(
    cut: Cut,
    index: TranscriptIndex,
    fps: Optional[Rational] = None,
    anchor: Optional[WordAnchor] = None,
) -> Optional[int]:
    """The timeline frame where `anchor`'s word plays, or None if it is not in the cut.

    `fps` defaults to `cut.fps` (pass an explicit value to override). `anchor` is required
    (kept as a plain default of `None` only so `fps` can precede it and still default);
    omitting it raises `TypeError`.
    """
    if anchor is None:
        raise TypeError("time_of() missing required argument: 'anchor'")
    fps = fps if fps is not None else cut.fps
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
            span = seg.source_end - seg.source_start
            frac = 0.0 if span <= 0 else (word.start - seg.source_start) / span
            return seg.start_frame + round(frac * seg.duration_frames)
    return None
