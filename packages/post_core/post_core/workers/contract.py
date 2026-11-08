"""The worker contract: what a subprocess prints, and what its exit code means.

A worker is any subprocess the core drives to do real work (transcribe a clip, render a
still, place footage in Resolve). Two things make a worker's outcome legible to the runner
without guessing at its prose, unlike the old app's classifier (`~/cc/post/backend/app/
runner.py:66-102`), which matched glyphs and regexes against narration and was wrong in
several documented ways (the `NOTHING_HAPPENED` regex false-positives on ordinary prose;
`failure_hint` is two hardcoded regexes tied to one skill's wording):

1. **Structured events.** A worker prints ``##POST {json}`` lines. Each object has a
   ``kind`` plus kind-specific fields (see ``EVENT_KINDS`` below). Anything else on stdout
   is free-form narration for a human and is not interpreted.
2. **A uniform exit code**, which the event stream must agree with: 0 only means "the
   process returned cleanly", not "the work happened" — the runner (`runner.py` in this
   package) additionally requires a ``result`` event and verifies every declared artifact.

This module only defines the contract and its (de)serialisation; it has no opinion about
subprocesses, timeouts or process groups (that is ``runner.py``).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PREFIX = "##POST "

# Event kinds a worker may emit, and the fields each one carries. Extra fields beyond these
# are allowed and passed through untouched (e.g. `result` may carry a `retry_at` alongside
# `ok`/`detail` when the worker exits 3) — this module does not reject unknown fields.
EVENT_KINDS = {
    "step": ("label",),
    "say": ("text",),
    "warn": ("text",),
    "err": ("text",),
    "progress": ("i", "n", "label"),
    "prompt": ("text", "model"),
    "cost": ("amount", "unit", "provider"),
    "artifact": ("path", "role", "sha256"),
    "result": ("ok", "detail"),
}

# Exit codes every worker must use. The runner treats these as authoritative alongside the
# event stream; neither alone is trusted (see runner.py's module docstring).
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_RETRY_LATER = 3          # provider limit / rate limit; a `retry_at` field is optional
EXIT_NEEDS_HUMAN = 4

EXIT_CODES = {
    EXIT_OK: "ok",
    EXIT_FAILED: "failed",
    EXIT_USAGE: "usage",
    EXIT_RETRY_LATER: "retry-later",
    EXIT_NEEDS_HUMAN: "needs-human",
}


def format_line(kind: str, **data: Any) -> str:
    """Render one event as the exact line a worker should print (no trailing newline)."""
    payload = {"kind": kind, **data}
    return PREFIX + json.dumps(payload, sort_keys=True, default=str)


def emit(kind: str, **data: Any) -> None:
    """Print one ``##POST`` event to stdout for a Python worker. Flushes immediately.

    Workers are read line by line while they run (see runner.py); an unflushed event sits
    in a libc buffer and is indistinguishable from a stalled process until the process
    exits or the buffer fills. Every call flushes so progress is visible as it happens.
    """
    print(format_line(kind, **data), flush=True)


def parse_line(raw: str) -> dict | None:
    """Parse one line of a worker's stdout into an event dict, or None if it is not one.

    Never raises: malformed JSON after the prefix, or a JSON value that isn't an object
    with a ``kind``, is treated as ordinary narration rather than a crash in the runner.
    """
    stripped = raw.strip()
    if not stripped.startswith(PREFIX):
        return None
    try:
        data = json.loads(stripped[len(PREFIX):])
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or "kind" not in data:
        return None
    return data


# A ~10-line bash function shell workers can source or paste, so a worker that is a bash
# script (not Python) can speak the same contract without reimplementing JSON escaping.
# It shells out to the system python3 to build the JSON payload correctly (quoting,
# unicode) rather than hand-rolling string escaping in bash, which is a well-known way to
# emit broken JSON the moment a value contains a quote or newline. Kept as an actual file
# (`post_emit.sh`, sourceable as-is) so it is copy-pasteable and testable on its own; this
# constant is that same file's text, read once at import time so the two never drift.
POST_EMIT_SH_PATH = Path(__file__).with_name("post_emit.sh")
POST_EMIT_SH = POST_EMIT_SH_PATH.read_text()
