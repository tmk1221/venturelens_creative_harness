"""ranges.py: keep ranges, timeline derivation (the only place timeline time is computed),
and word<->timeline-frame mappings."""
from __future__ import annotations

import pytest
from conftest import make_transcript

from post_core.edit import ops
from post_core.edit.ranges import TranscriptIndex, keep_ranges, time_of, timeline, word_at
from post_core.model import Rational, WordAnchor

ASPECT = Rational(num=16, den=9)
FPS_23976 = Rational(num=24000, den=1001)
FPS_2997 = Rational(num=30000, den=1001)


@pytest.mark.parametrize("fps", [FPS_23976, FPS_2997])
def test_timeline_durations_sum_exactly_and_are_contiguous(fps):
    t = make_transcript("sg1", n=20, gap=0.37, dur=0.3)
    cut = ops.cut_from_transcript(t, "cam-a", ASPECT)
    index = TranscriptIndex([t])
    cut, _ = ops.delete_words(cut, index, "sg1", t.words[5].id, t.words[7].id)

    segments = timeline(cut, index, fps)
    total_seconds = sum(seg.source_end - seg.source_start for seg in segments)
    expected_total_frames = round(total_seconds * fps.as_float())
    assert sum(seg.duration_frames for seg in segments) == expected_total_frames

    cursor = 0
    for seg in segments:
        assert seg.start_frame == cursor
        assert seg.duration_frames >= 0
        cursor += seg.duration_frames


def test_word_at_and_time_of_roundtrip():
    t = make_transcript("sg1", n=10)
    cut = ops.cut_from_transcript(t, "cam-a", ASPECT)
    index = TranscriptIndex([t])
    fps = Rational(num=30, den=1)

    anchor = WordAnchor(transcript_id=t.id, word_id=t.words[4].id)
    frame = time_of(cut, index, fps, anchor)
    assert frame is not None

    found = word_at(cut, index, fps, frame)
    assert found is not None
    assert found.word_id == t.words[4].id
    assert found.transcript_id == t.id


def test_time_of_returns_none_for_word_not_in_cut():
    t = make_transcript("sg1", n=10)
    cut = ops.cut_from_transcript(t, "cam-a", ASPECT)
    index = TranscriptIndex([t])
    cut, _ = ops.delete_words(cut, index, "sg1", t.words[3].id, t.words[3].id)

    fps = Rational(num=30, den=1)
    anchor = WordAnchor(transcript_id=t.id, word_id=t.words[3].id)
    assert time_of(cut, index, fps, anchor) is None


def test_timeline_defaults_to_cut_fps_when_fps_omitted():
    t = make_transcript("sg1", n=10, gap=0.4, dur=0.3)
    cut = ops.cut_from_transcript(t, "cam-a", ASPECT)
    cut = cut.model_copy(update={"fps": FPS_2997})
    index = TranscriptIndex([t])

    default_segments = timeline(cut, index)
    explicit_segments = timeline(cut, index, FPS_2997)
    assert default_segments == explicit_segments

    # An explicit fps still overrides the Cut's own.
    overridden = timeline(cut, index, FPS_23976)
    assert overridden != default_segments


def test_word_at_and_time_of_default_to_cut_fps():
    t = make_transcript("sg1", n=10)
    cut = ops.cut_from_transcript(t, "cam-a", ASPECT).model_copy(update={"fps": FPS_2997})
    index = TranscriptIndex([t])

    anchor = WordAnchor(transcript_id=t.id, word_id=t.words[4].id)
    frame = time_of(cut, index, anchor=anchor)
    assert frame == time_of(cut, index, FPS_2997, anchor)

    found = word_at(cut, index, timeline_frame=frame)
    assert found.word_id == t.words[4].id


def test_keep_ranges_merges_within_gap_and_splits_beyond_it():
    t = make_transcript("sg1", n=8, gap=0.5, dur=0.4)
    cut = ops.cut_from_transcript(t, "cam-a", ASPECT)
    index = TranscriptIndex([t])

    # A contiguous cut merges into a single keep range.
    ranges = keep_ranges(cut, index)
    assert len(ranges["sg1"]) == 1

    # Deleting a big enough gap splits it into two keep ranges.
    cut, _ = ops.delete_words(cut, index, "sg1", t.words[3].id, t.words[4].id)
    ranges = keep_ranges(cut, index, merge_gap=0.05)
    assert len(ranges["sg1"]) == 2
