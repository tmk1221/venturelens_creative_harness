from __future__ import annotations

import json

import pytest

from post_core.ingest.transcribe import importer


def test_import_json_list_shape():
    text = json.dumps([
        {"text": "hello", "start": 0.0, "end": 0.4, "speaker": "SPEAKER_00", "confidence": 0.9},
        {"word": "world", "start": 0.4, "end": 0.8},
    ])
    words = importer.import_json(text)
    assert words[0] == {"text": "hello", "start": 0.0, "end": 0.4, "speaker": "SPEAKER_00", "confidence": 0.9}
    assert words[1]["text"] == "world"
    assert words[1]["speaker"] == ""
    assert words[1]["confidence"] == 1.0


def test_import_json_dict_shape():
    text = json.dumps({"words": [{"text": "hi", "start": 0.0, "end": 0.2}]})
    words = importer.import_json(text)
    assert len(words) == 1
    assert words[0]["text"] == "hi"


def test_import_json_rejects_missing_text():
    with pytest.raises(ValueError):
        importer.import_json(json.dumps([{"start": 0.0, "end": 0.1}]))


SRT_SAMPLE = """\
1
00:00:00,000 --> 00:00:01,000
Hello world

2
00:00:01,500 --> 00:00:02,500
Second line here
"""


def test_import_srt():
    words = importer.import_srt(SRT_SAMPLE)
    assert [w["text"] for w in words] == ["Hello", "world", "Second", "line", "here"]
    assert words[0]["start"] == 0.0
    assert words[-1]["end"] <= 2.5
    for a, b in zip(words, words[1:]):
        assert a["start"] <= b["start"]


VTT_SAMPLE = """\
WEBVTT

00:00:00.000 --> 00:00:01.000
Hello world

00:00:01.500 --> 00:00:02.500
Second line here
"""


def test_import_vtt():
    words = importer.import_vtt(VTT_SAMPLE)
    assert [w["text"] for w in words] == ["Hello", "world", "Second", "line", "here"]
    assert words[0]["start"] == 0.0


def test_guess_format():
    assert importer.guess_format("t.json") == "json"
    assert importer.guess_format("t.srt") == "srt"
    assert importer.guess_format("t.vtt") == "vtt"
    with pytest.raises(ValueError):
        importer.guess_format("t.txt")


def test_words_to_transcript_builds_valid_transcript():
    words = importer.import_srt(SRT_SAMPLE)
    transcript = importer.words_to_transcript(
        words, sync_group_id="sg1", provider="import:srt", fingerprint="fp1")
    assert transcript.sync_group_id == "sg1"
    assert transcript.provider == "import:srt"
    assert len(transcript.words) == len(words)
    assert transcript.words[0].text == "Hello"
