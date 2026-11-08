"""Shared fixtures/builders for edit-op tests: cheap synthetic transcripts."""
from __future__ import annotations

from post_core.model import Transcript, Word


def make_words(n: int, start: float = 0.0, gap: float = 0.5, dur: float = 0.4) -> list[Word]:
    words = []
    t = start
    for i in range(n):
        words.append(Word(id=f"w{i}", text=f"word{i}", start=t, end=t + dur))
        t += gap
    return words


def make_transcript(sync_group_id: str, n: int = 10, **kw) -> Transcript:
    words = kw.pop("words", None)
    if words is None:
        words = make_words(n, gap=kw.pop("gap", 0.5), dur=kw.pop("dur", 0.4))
    defaults = dict(sync_group_id=sync_group_id, provider="fake", words=words, fingerprint="fp")
    defaults.update(kw)
    return Transcript(**defaults)
