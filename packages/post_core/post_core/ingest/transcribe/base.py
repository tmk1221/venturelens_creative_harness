"""The `TranscriptProvider` protocol and a name -> provider registry.

Any provider (Deepgram today, a local model later) implements `transcribe(audio_path,
opts) -> Transcript` and calls `register(name, instance)` once at import time. Callers
look providers up by name (`get("deepgram")`) so the worker CLI and the graph layer never
import a specific provider module directly.
"""
from __future__ import annotations

from typing import Any, Protocol

from post_core.model.transcript import Transcript


class TranscriptProvider(Protocol):
    name: str

    def transcribe(self, audio_path: str, opts: dict[str, Any]) -> Transcript: ...


_REGISTRY: dict[str, TranscriptProvider] = {}


def register(name: str, provider: TranscriptProvider) -> None:
    _REGISTRY[name] = provider


def get(name: str) -> TranscriptProvider:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"No transcript provider registered as {name!r}; known providers: "
            f"{sorted(_REGISTRY)}"
        ) from exc


def available() -> list[str]:
    return sorted(_REGISTRY)


# T35: the free path, named wherever transcription can't run (the `local` stub, a refusal).
LOCAL_UNAVAILABLE = (
    "The 'local' transcript provider isn't built yet. The free path is importing a finished "
    "transcript (JSON, SRT or VTT): `post ingest import-transcript --shoot <id> --sync-group <id> "
    "--path <file>`, or \"Import transcript…\" on the Ingest page."
)


class _LocalStub:
    """Placeholder for a future local (on-device) provider. Registered so `get("local")`
    resolves to something with a clear, actionable error rather than a KeyError."""

    name = "local"

    def transcribe(self, audio_path: str, opts: dict[str, Any]) -> Transcript:
        raise NotImplementedError(LOCAL_UNAVAILABLE)


register("local", _LocalStub())
