"""Deepgram nova-3 transcript provider.

`map_response` is pure: the JSON shape Deepgram's `/v1/listen` returns (see `~/.claude/skills/
footage-ingest/scripts/transcribe.py` and `~/cc/color_grade/skills/transcribe/scripts/
deepgram_transcribe.py` for the reference request/response shape this ports) -> flat word dicts.

`post_audio` is the only place that touches the network (T35). It streams the file from disk
with an explicit Content-Length -- http.client reads the body block by block, so a 43-minute
episode is never held in memory -- and reports bytes sent through `on_progress`. Tests point
`$DEEPGRAM_API_URL` at a local fake server; a real run leaves it unset. Nothing here ever logs
or returns the API key; error messages carry only Deepgram's status and reply.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, BinaryIO, Callable, Optional

from post_core.model.transcript import Transcript, Word

from . import base

API_URL = "https://api.deepgram.com/v1/listen"
QUERY = "model=nova-3&smart_format=true&punctuate=true&diarize=true&utterances=true"
API_URL_ENV = "DEEPGRAM_API_URL"
KEY_ENV = "DEEPGRAM_API_KEY"
CHUNK = 64 * 1024
CONTENT_TYPES = {".m4a": "audio/mp4", ".mp4": "audio/mp4", ".wav": "audio/wav", ".flac": "audio/flac",
                 ".mp3": "audio/mpeg"}

ProgressFn = Callable[[int, int], None]


class DeepgramError(RuntimeError):
    """Deepgram request failed, or no API key was available. `status` is Deepgram's HTTP
    status when it answered at all (429 = its rate limit: try again later)."""

    def __init__(self, message: str, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.status = status


def map_response(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Deepgram's raw JSON response -> a flat list of word dicts matching T02's Word
    fields (text/start/end/speaker/confidence). Raises ValueError on an unexpected shape
    rather than a bare KeyError, so a fixture drift is easy to diagnose."""
    try:
        alt = data["results"]["channels"][0]["alternatives"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("unexpected Deepgram response shape: no results.channels[0]."
                          "alternatives[0]") from exc

    words: list[dict[str, Any]] = []
    for w in alt.get("words", []):
        spk = w.get("speaker")
        speaker = f"SPEAKER_{spk:02d}" if isinstance(spk, int) else ""
        text = w.get("punctuated_word") or w.get("word")
        if not text:
            continue
        words.append({
            "text": text,
            "start": float(w["start"]),
            "end": float(w["end"]),
            "speaker": speaker,
            "confidence": float(w.get("confidence", 1.0)),
        })
    return words


class StreamedBody:
    """A file-like request body: every `read` returns at most `CHUNK` bytes straight from
    disk and reports the running total, so the upload is never one in-memory blob."""

    def __init__(self, f: BinaryIO, total: int, on_progress: Optional[ProgressFn] = None) -> None:
        self._f = f
        self.total = total
        self.sent = 0
        self._on_progress = on_progress

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0 or size > CHUNK:
            size = CHUNK
        data = self._f.read(size)
        if data:
            self.sent += len(data)
            if self._on_progress is not None:
                self._on_progress(self.sent, self.total)
        return data


def endpoint() -> str:
    return f"{os.environ.get(API_URL_ENV) or API_URL}?{QUERY}"


def content_type_for(path: str | Path) -> str:
    return CONTENT_TYPES.get(Path(path).suffix.lower(), "application/octet-stream")


def post_audio(
    audio_path: str | Path, api_key: str, *, content_type: Optional[str] = None,
    on_progress: Optional[ProgressFn] = None, timeout: float = 600.0,
) -> dict[str, Any]:
    """Upload one audio file to Deepgram and return its parsed JSON reply. Paid: callers
    must have an authorised spend before calling this (the queue enforces it)."""
    path = Path(audio_path)
    total = path.stat().st_size
    with path.open("rb") as f:
        req = urllib.request.Request(
            endpoint(), data=StreamedBody(f, total, on_progress), method="POST",
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": content_type or content_type_for(path),
                "Content-Length": str(total),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            reply = exc.read().decode(errors="replace").strip()[:300]
            raise DeepgramError(f"Deepgram answered HTTP {exc.code}: {reply or exc.reason}", exc.code) from None
        except urllib.error.URLError as exc:
            raise DeepgramError(f"Couldn't reach Deepgram: {exc.reason}") from None
        except TimeoutError:
            raise DeepgramError(f"Deepgram didn't answer within {timeout:g} s") from None


def api_key_from(opts: dict[str, Any]) -> str:
    api_key = opts.get("api_key") or os.environ.get(KEY_ENV)
    if not api_key:
        raise DeepgramError(f"{KEY_ENV} isn't set (put it in the repo's .env); nothing was sent")
    return api_key


class DeepgramProvider:
    name = "deepgram"

    def transcribe(self, audio_path: str, opts: dict[str, Any]) -> Transcript:
        """opts: sync_group_id, fingerprint (required); api_key (else env DEEPGRAM_API_KEY),
        content_type, on_progress, timeout (optional). Spends money -- tests only ever call
        it against a local fake server (`$DEEPGRAM_API_URL`)."""
        sync_group_id = opts.get("sync_group_id")
        fingerprint = opts.get("fingerprint")
        if not sync_group_id or not fingerprint:
            raise ValueError("opts must include 'sync_group_id' and 'fingerprint'")
        data = post_audio(audio_path, api_key_from(opts), content_type=opts.get("content_type"),
                          on_progress=opts.get("on_progress"), timeout=opts.get("timeout", 600.0))
        return Transcript(
            sync_group_id=sync_group_id,
            provider=self.name,
            words=[Word(**w) for w in map_response(data)],
            fingerprint=fingerprint,
        )


base.register("deepgram", DeepgramProvider())
