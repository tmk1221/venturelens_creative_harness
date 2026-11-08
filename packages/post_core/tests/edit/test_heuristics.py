"""Filler-word / long-silence suggestions: detection only, never auto-applied."""
from __future__ import annotations

from post_core.edit.heuristics import find_filler_words, find_long_silences
from post_core.model import Transcript, Word


def _transcript(words: list[Word]) -> Transcript:
    return Transcript(sync_group_id="sg1", provider="fake", fingerprint="fp", words=words)


def test_find_filler_words_matches_default_list_case_insensitively():
    words = [
        Word(id="w0", text="So", start=0.0, end=0.3),
        Word(id="w1", text="Um,", start=0.3, end=0.5),
        Word(id="w2", text="basically", start=0.5, end=0.9),
        Word(id="w3", text="fine.", start=0.9, end=1.1),
    ]
    suggestions = find_filler_words(_transcript(words))
    assert {s.start_word_id for s in suggestions} == {"w1", "w2"}
    assert all(s.kind == "filler" for s in suggestions)
    assert all(s.start_word_id == s.end_word_id for s in suggestions)


def test_find_long_silences_brackets_the_gap():
    words = [
        Word(id="w0", text="hi", start=0.0, end=0.3),
        Word(id="w1", text="there", start=2.5, end=2.8),
    ]
    suggestions = find_long_silences(_transcript(words), threshold=1.0)
    assert len(suggestions) == 1
    suggestion = suggestions[0]
    assert suggestion.start_word_id == "w0"
    assert suggestion.end_word_id == "w1"
    assert suggestion.kind == "silence"


def test_no_suggestion_for_gap_below_threshold():
    words = [
        Word(id="w0", text="hi", start=0.0, end=0.3),
        Word(id="w1", text="there", start=0.5, end=0.8),
    ]
    assert find_long_silences(_transcript(words), threshold=1.0) == []


def test_suggestions_never_mutate_the_transcript():
    words = [Word(id="w0", text="um", start=0.0, end=0.3)]
    transcript = _transcript(words)
    find_filler_words(transcript)
    find_long_silences(transcript)
    assert transcript.words[0].text == "um"
