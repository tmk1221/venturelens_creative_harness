"""Filler-word and long-silence detection: suggestions, never auto-applied.

Callers turn a suggestion into an actual edit by feeding its word range into
`ops.delete_words` -- nothing here mutates a Cut.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..model.transcript import Transcript

DEFAULT_FILLERS = frozenset(
    {"um", "uh", "erm", "hm", "hmm", "like", "y'know", "yknow", "kinda", "basically", "literally"}
)
DEFAULT_SILENCE_THRESHOLD = 1.5  # seconds


@dataclass(frozen=True)
class WordRangeSuggestion:
    """A candidate `delete_words` argument, plus why it was suggested."""

    sync_group_id: str
    start_word_id: str
    end_word_id: str
    kind: str  # "filler" | "silence"
    reason: str


def find_filler_words(
    transcript: Transcript, fillers: frozenset[str] = DEFAULT_FILLERS
) -> list[WordRangeSuggestion]:
    """One suggestion per filler word (not merged across runs -- callers can merge adjacent
    ones with `ranges.keep_ranges`-style logic if they want)."""
    suggestions: list[WordRangeSuggestion] = []
    for word in transcript.words:
        cleaned = word.text.strip().lower().strip(".,!?")
        if cleaned in fillers:
            suggestions.append(
                WordRangeSuggestion(
                    sync_group_id=transcript.sync_group_id,
                    start_word_id=word.id,
                    end_word_id=word.id,
                    kind="filler",
                    reason=f"filler word {cleaned!r}",
                )
            )
    return suggestions


def find_long_silences(
    transcript: Transcript, threshold: float = DEFAULT_SILENCE_THRESHOLD
) -> list[WordRangeSuggestion]:
    """A suggestion per gap `>= threshold` seconds between consecutive words. `start_word_id`
    and `end_word_id` bracket the silent gap (the words just before/after it); trim their
    passages' tail/head, or delete the range, to close it."""
    suggestions: list[WordRangeSuggestion] = []
    words = transcript.words
    for prev_word, next_word in zip(words, words[1:]):
        gap = next_word.start - prev_word.end
        if gap >= threshold:
            suggestions.append(
                WordRangeSuggestion(
                    sync_group_id=transcript.sync_group_id,
                    start_word_id=prev_word.id,
                    end_word_id=next_word.id,
                    kind="silence",
                    reason=f"{gap:.2f}s silence",
                )
            )
    return suggestions
