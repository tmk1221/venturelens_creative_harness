"""T34: a job that runs in-process (a thread in post_api) rather than as a workflow node the
`Executor` picks -- e.g. the new-project ingest. It is still a row in `job` with its events
in `event`, so it streams over the same SSE endpoint and shows up in `queue list`, but it
lives in its own lane, which no `Executor` manages (`Executor.recover_interrupted` and
`_pick_jobs` only touch their own lanes), so a workflow's executor never claims or recovers
it. A process that dies mid-run leaves the row `running`; `recover_inline_jobs` marks those
`interrupted` the next time the project is opened.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Callable, Iterable, Optional

from ..model.base import new_id
from . import db as db_mod

INLINE_LANE = "inline"


class InlineJob:
    """One running in-process job: `emit(event)` appends to its event stream, `finish()`
    records the outcome (plus a final `result` event, like a worker's)."""

    def __init__(self, project_root: str | Path, job_id: str, now: Callable[[], float] = time.time) -> None:
        self.project_root = project_root
        self.id = job_id
        self._now = now
        self._seq = 0
        self._lock = threading.Lock()

    @classmethod
    def start(cls, project_root: str | Path, *, workflow_id: str, node_id: str, params: dict,
              now: Callable[[], float] = time.time) -> "InlineJob":
        params_json = json.dumps(params, sort_keys=True, default=str)
        job_id = new_id()
        at = now()
        with db_mod.open_db(project_root) as con:
            con.execute(
                "INSERT INTO job (id, workflow_id, node_id, input_hash, lane, state, cmd_json, attempts, "
                "created_at, started_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (job_id, workflow_id, node_id, hashlib.sha256(params_json.encode()).hexdigest(), INLINE_LANE,
                 "running", params_json, 1, at, at),
            )
            con.commit()
        return cls(project_root, job_id, now)

    def emit(self, event: dict) -> None:
        with self._lock:
            seq = self._seq
            self._seq += 1
        with db_mod.open_db(self.project_root) as con:
            con.execute(
                "INSERT INTO event (job_id, seq, kind, json, at) VALUES (?,?,?,?,?)",
                (self.id, seq, event.get("kind", ""), json.dumps(event, default=str), self._now()),
            )
            con.commit()

    def finish(self, ok: bool, summary: str) -> None:
        self.emit({"kind": "result", "ok": ok, "detail": summary})
        with db_mod.open_db(self.project_root) as con:
            con.execute("UPDATE job SET state=?, finished_at=?, summary=? WHERE id=?",
                        ("ok" if ok else "failed", self._now(), summary, self.id))
            con.commit()


def recover_inline_jobs(project_root: str | Path, workflow_id: str, live_ids: Iterable[str] = (),
                        now: Callable[[], float] = time.time) -> list[str]:
    """Mark this workflow's `running` inline jobs that no live thread owns as `interrupted`."""
    live = set(live_ids)
    with db_mod.open_db(project_root) as con:
        rows = con.execute("SELECT id FROM job WHERE workflow_id=? AND lane=? AND state='running'",
                           (workflow_id, INLINE_LANE)).fetchall()
        stale = [r["id"] for r in rows if r["id"] not in live]
        for job_id in stale:
            con.execute("UPDATE job SET state='interrupted', finished_at=?, "
                        "summary='the server stopped while this was running; run it again to pick up where it left off' "
                        "WHERE id=?", (now(), job_id))
        con.commit()
    return stale


def latest_inline_job(project_root: str | Path, workflow_id: str) -> Optional[dict]:
    with db_mod.open_db(project_root) as con:
        row = con.execute("SELECT * FROM job WHERE workflow_id=? AND lane=? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                          (workflow_id, INLINE_LANE)).fetchone()
    return dict(row) if row is not None else None


__all__ = ["INLINE_LANE", "InlineJob", "latest_inline_job", "recover_inline_jobs"]
