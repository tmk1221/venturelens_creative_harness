"""The transcript editor's brain: pure functions over a Cut, plus a persisted session wrapper.

See `ops.py` (edit operations), `ranges.py` (keep ranges + timeline derivation),
`heuristics.py` (filler/silence suggestions), and `session.py` (apply + undo/redo).
"""
from .heuristics import (
    DEFAULT_FILLERS,
    DEFAULT_SILENCE_THRESHOLD,
    WordRangeSuggestion,
    find_filler_words,
    find_long_silences,
)
from .ops import (
    EditReport,
    cut_from_transcript,
    delete_words,
    derive_cut,
    insert_range,
    merge_adjacent,
    move_passage,
    move_words,
    replace_range_with,
    restore_words,
    set_angle,
    set_trim,
)
from .ranges import TimelineSegment, TranscriptIndex, keep_ranges, passage_source_range, time_of, timeline, word_at
from .session import EditSession
from .similarity import SwapCandidate, find_swap_candidates

__all__ = [
    "EditReport",
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
    "merge_adjacent",
    "TranscriptIndex",
    "TimelineSegment",
    "keep_ranges",
    "passage_source_range",
    "timeline",
    "word_at",
    "time_of",
    "find_filler_words",
    "find_long_silences",
    "WordRangeSuggestion",
    "DEFAULT_FILLERS",
    "DEFAULT_SILENCE_THRESHOLD",
    "EditSession",
    "SwapCandidate",
    "find_swap_candidates",
]
