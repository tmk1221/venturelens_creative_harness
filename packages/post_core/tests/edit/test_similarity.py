"""Swap-take candidate matching: fuzzy-matches a word range against every other range in
every transcript (including retakes in the same sync group), never mutates anything."""
from __future__ import annotations

from post_core.edit.similarity import find_swap_candidates
from post_core.model import Transcript, Word


def _words(texts: list[str], step: float = 0.3) -> list[Word]:
    out = []
    t = 0.0
    for i, text in enumerate(texts):
        out.append(Word(id=f"w{i}", text=text, start=t, end=t + step * 0.8))
        t += step
    return out


def test_finds_near_duplicate_take_in_same_sync_group():
    words = _words(["I", "think", "this", "works", "well", "I", "think", "this", "works", "great"])
    transcript = Transcript(sync_group_id="sg1", provider="fake", fingerprint="fp", words=words)

    candidates = find_swap_candidates([transcript], "sg1", "w0", "w4")
    assert candidates, "expected at least one candidate"
    best = candidates[0]
    assert best.sync_group_id == "sg1"
    assert best.start_word_id == "w5"
    assert best.score > 0.6


def test_selection_itself_is_excluded():
    words = _words(["hello", "there", "world"])
    transcript = Transcript(sync_group_id="sg1", provider="fake", fingerprint="fp", words=words)
    candidates = find_swap_candidates([transcript], "sg1", "w0", "w2")
    for c in candidates:
        assert not (c.start_word_id == "w0" and c.end_word_id == "w2")


def test_matches_across_transcripts():
    a = Transcript(
        sync_group_id="sg1", provider="fake", fingerprint="fp",
        words=_words(["this", "is", "a", "test", "sentence"]),
    )
    b = Transcript(
        sync_group_id="sg2", provider="fake", fingerprint="fp",
        words=_words(["this", "is", "a", "test", "sentence", "too"]),
    )
    candidates = find_swap_candidates([a, b], "sg1", "w0", "w4")
    assert any(c.sync_group_id == "sg2" for c in candidates)


def test_no_match_below_min_score_returns_empty():
    a = Transcript(
        sync_group_id="sg1", provider="fake", fingerprint="fp",
        words=_words(["completely", "different", "content"]),
    )
    b = Transcript(
        sync_group_id="sg2", provider="fake", fingerprint="fp",
        words=_words(["zebra", "quartz", "jynx"]),
    )
    candidates = find_swap_candidates([a, b], "sg1", "w0", "w2", min_score=0.95)
    assert candidates == []
