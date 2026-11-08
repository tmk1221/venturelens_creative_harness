"""Tests the Deepgram response mapper only. `DeepgramProvider.transcribe` (the network
call) is never invoked here — see deepgram.py's module docstring and AGENTS.md."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from post_core.ingest.transcribe.deepgram import map_response
from post_core.ingest.transcribe.importer import words_to_transcript

FIXTURE = Path(__file__).parent / "fixtures" / "deepgram_response.json"


def test_map_response_fixture():
    data = json.loads(FIXTURE.read_text())
    words = map_response(data)
    assert [w["text"] for w in words] == ["Hello", "world,", "This", "is", "a", "test."]
    assert words[0]["speaker"] == "SPEAKER_00"
    assert words[2]["speaker"] == "SPEAKER_01"
    assert words[0]["start"] == 0.08
    assert words[0]["confidence"] == 0.99


def test_map_response_builds_valid_transcript():
    data = json.loads(FIXTURE.read_text())
    words = map_response(data)
    transcript = words_to_transcript(words, sync_group_id="sg1", provider="deepgram",
                                      fingerprint="fp1")
    assert len(transcript.words) == 6
    assert transcript.provider == "deepgram"


def test_map_response_rejects_bad_shape():
    with pytest.raises(ValueError):
        map_response({"nope": True})


def test_map_response_skips_empty_words():
    data = {"results": {"channels": [{"alternatives": [{"words": [
        {"word": "", "punctuated_word": "", "start": 0.0, "end": 0.1},
        {"word": "ok", "start": 0.1, "end": 0.2},
    ]}]}]}}
    words = map_response(data)
    assert len(words) == 1
    assert words[0]["text"] == "ok"
