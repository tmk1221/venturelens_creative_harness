"""Import an existing transcript (JSON, SRT, or VTT) into T02 Word/Transcript.

Not a `TranscriptProvider` — these formats are already-finished transcripts someone
supplies, not something to fetch from a service, so they are plain functions the worker
CLI (or a caller) invokes directly.
"""
from __future__ import annotations

import json
import re
from typing import Any

from post_core.model.transcript import Transcript, Word


def import_json(text: str) -> list[dict[str, Any]]:
    """Accepts `[{text|word, start, end, speaker?, confidence?}, ...]` or
    `{"words": [...]}`  of the same shape."""
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("words", [])
    if not isinstance(data, list):
        raise ValueError("JSON transcript must be a list of words or {'words': [...]}")

    words: list[dict[str, Any]] = []
    for w in data:
        word_text = w.get("text", w.get("word"))
        if not word_text:
            raise ValueError(f"word entry missing 'text'/'word': {w!r}")
        words.append({
            "text": word_text,
            "start": float(w["start"]),
            "end": float(w["end"]),
            "speaker": str(w.get("speaker", "")),
            "confidence": float(w.get("confidence", 1.0)),
        })
    return words


_SRT_TIME = re.compile(r"(\d{1,2}):(\d\d):(\d\d)[,.](\d\d\d)")
_VTT_TIME = re.compile(r"(\d{1,2}):(\d\d):(\d\d)\.(\d\d\d)")


def _timecode_seconds(groups: tuple[str, str, str, str]) -> float:
    h, mnt, s, ms = (int(x) for x in groups)
    return h * 3600 + mnt * 60 + s + ms / 1000


def _parse_cues(text: str, time_re: re.Pattern[str]) -> list[tuple[float, float, str]]:
    blocks = re.split(r"\r?\n\r?\n+", text.strip())
    cues: list[tuple[float, float, str]] = []
    for block in blocks:
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        arrow_line = next((ln for ln in lines if "-->" in ln), None)
        if arrow_line is None:
            continue
        times = time_re.findall(arrow_line)
        if len(times) < 2:
            continue
        start = _timecode_seconds(times[0])
        end = _timecode_seconds(times[1])
        body = " ".join(lines[lines.index(arrow_line) + 1:]).strip()
        if body and end > start:
            cues.append((start, end, body))
    return cues


def _cues_to_words(cues: list[tuple[float, float, str]]) -> list[dict[str, Any]]:
    """Splits each cue's text evenly across its time span — subtitle formats don't carry
    per-word timing, so this is an approximation good enough for waveform/caption
    placement, not a claim of word-accurate timing."""
    words: list[dict[str, Any]] = []
    for start, end, cue_text in cues:
        tokens = cue_text.split()
        if not tokens:
            continue
        span = (end - start) / len(tokens)
        for i, tok in enumerate(tokens):
            w_start = start + i * span
            w_end = w_start + span if span > 0 else end
            if w_end <= w_start:
                w_end = w_start + 1e-3
            words.append({"text": tok, "start": w_start, "end": w_end,
                          "speaker": "", "confidence": 1.0})
    return words


def import_srt(text: str) -> list[dict[str, Any]]:
    return _cues_to_words(_parse_cues(text, _SRT_TIME))


def import_vtt(text: str) -> list[dict[str, Any]]:
    body = re.sub(r"^WEBVTT[^\n]*\n", "", text.strip(), count=1)
    return _cues_to_words(_parse_cues(body, _VTT_TIME))


_FORMATS = {"json": import_json, "srt": import_srt, "vtt": import_vtt}


def guess_format(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext not in _FORMATS:
        raise ValueError(f"cannot guess transcript format from path: {path!r}")
    return ext


def import_words(text: str, fmt: str) -> list[dict[str, Any]]:
    if fmt not in _FORMATS:
        raise ValueError(f"unknown transcript import format: {fmt!r} (known: {sorted(_FORMATS)})")
    return _FORMATS[fmt](text)


def words_to_transcript(
    words: list[dict[str, Any]], sync_group_id: str, provider: str, fingerprint: str,
) -> Transcript:
    return Transcript(
        sync_group_id=sync_group_id, provider=provider,
        words=[Word(**w) for w in words], fingerprint=fingerprint,
    )
