"""Word and Transcript: the spoken-word timeline a Cut is edited against."""
from __future__ import annotations

from typing import Optional

from pydantic import field_validator, model_validator

from .base import Entity


class Word(Entity):
    """One transcribed word, stable-id'd so edits and anchors survive re-transcription diffs."""

    text: str
    start: float  # seconds, relative to the sync group origin
    end: float
    speaker: str = ""
    confidence: float = 1.0

    @field_validator("text")
    @classmethod
    def _text_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Word.text must not be empty")
        return v

    @model_validator(mode="after")
    def _ordered_range(self) -> "Word":
        if self.start < 0 or self.end <= self.start:
            raise ValueError("Word.start must be >= 0 and Word.end must be > Word.start")
        return self


class Transcript(Entity):
    """A word-level transcript for one SyncGroup, from one provider."""

    sync_group_id: str
    provider: str
    words: list[Word] = []
    fingerprint: str
    # T35: a display name per diarization label (`SPEAKER_00` -> "a podcast host"). Names live
    # here, never in `Word.speaker`, so a rename is one write and the labels stay what the
    # provider said (`ingest.transcribe.speakers`).
    speakers: dict[str, str] = {}

    @model_validator(mode="after")
    def _words_ordered_unique(self) -> "Transcript":
        seen: set[str] = set()
        previous_start: Optional[float] = None
        for word in self.words:
            if word.id in seen:
                raise ValueError(f"Transcript has duplicate word id: {word.id}")
            seen.add(word.id)
            if previous_start is not None and word.start < previous_start:
                raise ValueError("Transcript.words must be ordered by start time")
            previous_start = word.start
        return self
