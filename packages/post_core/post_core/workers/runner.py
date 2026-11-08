"""Run a worker subprocess and decide, from disk and the event stream, what happened.

Ports the parts of the old runner (`~/cc/post/backend/app/runner.py`) worth keeping — line
streaming, a new process group so a timeout/cancel kills everything the worker spawned,
`PYTHONUTF8`-safe decoding, and a finalizer that always runs — and fixes the weaknesses the
v3 audit (`~/cc/vl/brain/projects/post-v3-audit-current-app.md` §3.1) called out in it:

- No more guessing at success from narration (`NOTHING_HAPPENED` regex, glyph classifier,
  two hardcoded `failure_hint` regexes). A worker's own `##POST` events are authoritative:
  outcome is `ok` only when the exit code is 0 *and* the worker emitted `result{ok: true}`
  *and* every artifact it declared exists on disk with a matching sha256. Anything else is
  a specific, non-guessed failure kind (`failed` / `retry_later` / `needs_human` /
  `interrupted`).
- A heartbeat: silence past `heartbeat` seconds emits a synthetic `stalled` event through
  `on_event` (the caller decides whether that means anything) rather than killing a worker
  that is just slow. The old runner had no watchdog at all.
"""
from __future__ import annotations

import hashlib
import os
import queue
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Sequence

from . import contract

OK = "ok"
FAILED = "failed"
RETRY_LATER = "retry_later"
NEEDS_HUMAN = "needs_human"
INTERRUPTED = "interrupted"

_TAIL_LINES = 40
_POLL_INTERVAL = 0.05
_KILL_GRACE = 3.0


@dataclass
class RunResult:
    exit_code: int | None
    outcome: str
    events: list[dict]
    artifacts: list[dict]
    cost_total: dict[str, float]
    tail: str
    cmd: list[str] = field(default_factory=list)
    retry_at: str | None = None

    @property
    def ok(self) -> bool:
        return self.outcome == OK


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_artifacts(events: list[dict], base: Path) -> tuple[list[dict], bool]:
    """Every `artifact` event must name a file that exists and (if declared) matches its
    sha256. Missing declared fields (no path) count as a failed check, not a skip."""
    artifacts = [e for e in events if e.get("kind") == "artifact"]
    all_ok = True
    for a in artifacts:
        raw_path = a.get("path")
        if not raw_path:
            all_ok = False
            continue
        p = Path(raw_path)
        if not p.is_absolute():
            p = base / p
        if not p.is_file():
            all_ok = False
            continue
        declared = a.get("sha256")
        if declared and _sha256(p) != declared:
            all_ok = False
    return artifacts, all_ok


def _cost_total(events: list[dict]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for e in events:
        if e.get("kind") != "cost":
            continue
        unit = str(e.get("unit") or "")
        try:
            amount = float(e.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        totals[unit] = totals.get(unit, 0.0) + amount
    return totals


def _kill_group(proc: subprocess.Popen) -> None:
    """SIGTERM the whole process group; escalate to SIGKILL if it ignores that."""
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        try:
            proc.terminate()
        except Exception:
            pass
        return
    try:
        proc.wait(timeout=_KILL_GRACE)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def run(
    cmd: Sequence[str | os.PathLike],
    cwd: str | os.PathLike | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
    on_event: Callable[[dict], None] | None = None,
    finalizer: Callable[[], None] | None = None,
    cancel: threading.Event | None = None,
    heartbeat: float | None = None,
) -> RunResult:
    """Run one worker to completion. Blocks the calling thread; run it in a thread/executor
    to cancel it concurrently by setting `cancel`.

    `finalizer`, if given, always runs exactly once (success, failure, timeout, cancel, or
    a launch error) and cannot change or mask the returned outcome — an exception it raises
    is appended to `tail` and otherwise ignored, the same discipline the old runner used
    (`runner.py:314-319`: "cleanup cannot erase the job's real result").
    """
    cmd_list = [str(c) for c in cmd]
    cwd_path = Path(cwd) if cwd is not None else Path.cwd()
    run_env = {**os.environ, **(env or {})}

    events: list[dict] = []
    tail: list[str] = []
    interrupted = False
    proc: subprocess.Popen | None = None
    exit_code: int | None = None

    try:
        try:
            proc = subprocess.Popen(
                cmd_list, cwd=str(cwd_path), env=run_env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                bufsize=1, start_new_session=True,
            )
        except OSError as exc:
            # No process ever started: a clean failure result, not a raised exception, so
            # callers have one error path instead of two.
            return RunResult(exit_code=None, outcome=FAILED, events=[], artifacts=[],
                              cost_total={}, tail=f"launch failed: {exc}", cmd=cmd_list)

        line_q: "queue.Queue[str | None]" = queue.Queue()

        def _reader() -> None:
            assert proc is not None and proc.stdout is not None
            try:
                for raw in proc.stdout:
                    line_q.put(raw)
            finally:
                line_q.put(None)  # EOF sentinel

        reader = threading.Thread(target=_reader, daemon=True)
        reader.start()

        start = time.monotonic()
        last_output = start
        stalled_emitted = False

        while True:
            if cancel is not None and cancel.is_set():
                interrupted = True
                _kill_group(proc)
                break
            now = time.monotonic()
            if timeout is not None and (now - start) >= timeout:
                interrupted = True
                _kill_group(proc)
                break

            try:
                item = line_q.get(timeout=_POLL_INTERVAL)
            except queue.Empty:
                if (heartbeat is not None and (now - last_output) >= heartbeat
                        and not stalled_emitted):
                    stalled_emitted = True
                    if on_event:
                        on_event({"kind": "stalled", "since": last_output})
                continue

            if item is None:
                break  # worker's stdout closed: it has exited or is exiting

            last_output = time.monotonic()
            stalled_emitted = False
            tail.append(item.rstrip("\n"))
            if len(tail) > _TAIL_LINES:
                del tail[: len(tail) - _TAIL_LINES]
            ev = contract.parse_line(item)
            if ev is not None:
                events.append(ev)
                if on_event:
                    on_event(ev)

        reader.join(timeout=_KILL_GRACE + 1)
        try:
            exit_code = proc.wait(timeout=_KILL_GRACE + 1)
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            exit_code = proc.wait(timeout=_KILL_GRACE + 1)
    finally:
        if finalizer:
            try:
                finalizer()
            except Exception as exc:  # finalizer cannot mask the real result
                tail.append(f"[runner] finalizer failed: {exc}")

    tail_text = "\n".join(tail)

    if interrupted:
        artifacts = [e for e in events if e.get("kind") == "artifact"]
        return RunResult(exit_code=exit_code, outcome=INTERRUPTED, events=events,
                          artifacts=artifacts, cost_total=_cost_total(events),
                          tail=tail_text, cmd=cmd_list)

    result_events = [e for e in events if e.get("kind") == "result"]
    result_event = result_events[-1] if result_events else None
    artifacts, artifacts_ok = _verify_artifacts(events, cwd_path)
    retry_at = None

    if exit_code == contract.EXIT_OK and result_event is not None \
            and result_event.get("ok") is True and artifacts_ok:
        outcome = OK
    elif exit_code == contract.EXIT_RETRY_LATER:
        outcome = RETRY_LATER
        if result_event is not None:
            retry_at = result_event.get("retry_at")
    elif exit_code == contract.EXIT_NEEDS_HUMAN:
        outcome = NEEDS_HUMAN
    else:
        outcome = FAILED

    return RunResult(exit_code=exit_code, outcome=outcome, events=events,
                      artifacts=artifacts, cost_total=_cost_total(events), tail=tail_text,
                      cmd=cmd_list, retry_at=retry_at)
