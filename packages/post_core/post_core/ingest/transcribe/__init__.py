"""Pluggable transcription: a `TranscriptProvider` protocol + a name registry.

`deepgram` and `local` register themselves on import of this package so
`post_core.ingest.transcribe.base.get("deepgram")` works right after `import
post_core.ingest.transcribe`. `importer` (JSON/SRT/VTT) is a separate utility, not a
network provider, and is used directly rather than through the registry.

T35: `job` makes a paid transcription a queued, authorised spend (worker: `job_worker`);
`link` is the one way a transcript lands in the store; `speakers` names the speakers.
"""
from __future__ import annotations

from . import base, deepgram  # noqa: F401  (import registers the built-in providers)

__all__ = ["base", "deepgram"]
