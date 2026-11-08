"""Swap-take candidates: other word ranges across every transcript whose text fuzzy-matches
a selected range, for the "Swap take" toolbar action. Read-only -- nothing here mutates a Cut;
a caller turns a candidate into an edit via `ops.replace_range_with`.
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from ..model.transcript import Transcript
from .ranges import TranscriptIndex

DEFAULT_MIN_SCORE = 0.6
DEFAULT_MAX_RESULTS = 8
# how many extra words of slack (beyond the selection's own length) a candidate window may
# scan across, so a slightly longer/shorter retake of the same line can still match
_WINDOW_SLACK = 3


@dataclass(frozen=True)
class SwapCandidate:
    sync_group_id: str
    start_word_id: str
    end_word_id: str
    text: str
    score: float


def _normalized_text(transcript: Transcript, start_i: int, end_i: int) -> str:
    return " ".join(w.text.strip().lower() for w in transcript.words[start_i : end_i + 1])


def find_swap_candidates(
    transcripts: list[Transcript],
    sync_group_id: str,
    start_word_id: str,
    end_word_id: str,
    min_score: float = DEFAULT_MIN_SCORE,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> list[SwapCandidate]:
    """Slide a window of similar length over every OTHER word range in every transcript
    (including other passages of the same sync group, e.g. a repeated take of the same line)
    and score it against the selected range's text with `difflib.SequenceMatcher`. Returns
    the best-scoring, non-overlapping windows per transcript, highest score first.
    """
    index = TranscriptIndex(transcripts)
    sel_start_i = index.index_of(sync_group_id, start_word_id)
    sel_end_i = index.index_of(sync_group_id, end_word_id)
    sel_len = sel_end_i - sel_start_i + 1
    sel_text = _normalized_text(index.transcript_for(sync_group_id), sel_start_i, sel_end_i)

    results: list[SwapCandidate] = []
    for transcript in transcripts:
        words = transcript.words
        n = len(words)
        is_same_group = transcript.sync_group_id == sync_group_id
        best_by_start: dict[int, SwapCandidate] = {}
        for win_len in range(max(1, sel_len - _WINDOW_SLACK), sel_len + _WINDOW_SLACK + 1):
            if win_len < 1:
                continue
            for w_start in range(0, max(0, n - win_len + 1)):
                w_end = w_start + win_len - 1
                if is_same_group and not (w_end < sel_start_i or w_start > sel_end_i):
                    continue  # skip the selection itself and any overlap with it
                text = _normalized_text(transcript, w_start, w_end)
                score = SequenceMatcher(None, sel_text, text).ratio()
                if score < min_score:
                    continue
                prev = best_by_start.get(w_start)
                if prev is None or score > prev.score:
                    best_by_start[w_start] = SwapCandidate(
                        sync_group_id=transcript.sync_group_id,
                        start_word_id=words[w_start].id,
                        end_word_id=words[w_end].id,
                        text=text,
                        score=score,
                    )
        results.extend(best_by_start.values())

    results.sort(key=lambda c: c.score, reverse=True)
    return results[:max_results]


__all__ = ["SwapCandidate", "find_swap_candidates", "DEFAULT_MIN_SCORE", "DEFAULT_MAX_RESULTS"]
