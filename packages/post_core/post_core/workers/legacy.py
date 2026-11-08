"""Adapter for scripts that do not speak the ##POST contract.

Most of the scripts this app drives today (the skills under `~/.claude/skills/*/scripts/`)
print narration for a human and exit 0 even when they produced nothing — AGENTS.md: "a
successful process exit alone is not proof of completion." This module does not try to
read that narration; the old runner's glyph/regex classifier for exactly this problem is
the weakness the v3 audit flags (`~/cc/vl/brain/projects/post-v3-audit-current-app.md`
§3.1: "the glyph classifier is admitted guesswork"). Instead it verifies success the one
way a legacy script actually supports: the caller states which files it expects, and this
adapter checks the exit code plus those files existing and being non-trivial (not a
zero-byte file left behind by a script that "succeeded" while writing nothing).

Runs through `runner.run` for the process-group/timeout/heartbeat/finalizer machinery, then
replaces `runner.run`'s contract-based outcome (which will read `failed` for any script
that never emits `##POST` events — expected here) with this simpler check.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable, Mapping, Sequence

from . import runner


def run_legacy(
    cmd: Sequence[str | os.PathLike],
    expected_artifacts: Sequence[str | os.PathLike],
    cwd: str | os.PathLike | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
    on_event: Callable[[dict], None] | None = None,
    finalizer: Callable[[], None] | None = None,
    cancel: threading.Event | None = None,
    heartbeat: float | None = None,
    min_size: int = 1,
) -> runner.RunResult:
    """Run `cmd`; outcome is `ok` only if it exits 0 and every path in
    `expected_artifacts` exists and is at least `min_size` bytes. A timeout/cancel still
    reports `interrupted`, same as `runner.run`.
    """
    base = Path(cwd) if cwd is not None else Path.cwd()
    result = runner.run(cmd, cwd=cwd, env=env, timeout=timeout, on_event=on_event,
                         finalizer=finalizer, cancel=cancel, heartbeat=heartbeat)

    if result.outcome == runner.INTERRUPTED:
        return result

    missing: list[str] = []
    trivial: list[str] = []
    artifacts: list[dict] = []
    for raw_path in expected_artifacts:
        p = Path(raw_path)
        if not p.is_absolute():
            p = base / p
        exists = p.is_file()
        size = p.stat().st_size if exists else 0
        artifacts.append({"kind": "artifact", "path": str(p), "exists": exists, "size": size})
        if not exists:
            missing.append(str(p))
        elif size < min_size:
            trivial.append(str(p))

    outcome = runner.OK if (result.exit_code == 0 and not missing and not trivial) else runner.FAILED

    tail = result.tail
    if missing:
        tail = (tail + "\n" if tail else "") + f"[legacy] missing artifacts: {missing}"
    if trivial:
        tail = (tail + "\n" if tail else "") + f"[legacy] trivial (empty) artifacts: {trivial}"

    return runner.RunResult(
        exit_code=result.exit_code, outcome=outcome, events=result.events,
        artifacts=artifacts, cost_total=result.cost_total, tail=tail,
        cmd=result.cmd, retry_at=result.retry_at,
    )
