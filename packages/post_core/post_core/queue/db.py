"""The queue's SQLite database: `<root>/.post3/queue.db`, versioned migrations.

SQLite holds the queue only (ARCHITECTURE.md §1) -- disk JSON/artifact dirs stay the source
of truth. `connect()`/`open_db()` open one connection per call site and the caller (or the
`open_db` contextmanager) closes it explicitly; the old app leaked file descriptors by
holding one connection open for the whole process (`~/cc/post/backend/app/jobs.py`).

Tables:
  job    one row per (attempt at a) node build. `cmd_json` is the full worker command,
         recorded at enqueue time so a restart never has to reconstruct it.
  event  the `##POST` event stream for a job, in order (`seq`).
  budget one row per explicitly created budget: cap, spent so far, and the one unit it
         counts (`budget.py` -- never created as a side effect of running anything).
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ..store.paths import store_root

# Job states (ARCHITECTURE.md §1 / T05 spec). Terminal: ok, failed, cancelled, interrupted
# (an interrupted job is not retried in place -- `Executor.recover_interrupted` requeues its
# node as a brand new job if the node is still ready, leaving the interrupted row as history).
JOB_STATES = (
    "queued", "running", "ok", "failed", "retry_later", "needs_human", "interrupted",
    "cancelled",
)
# "live" for enqueue()'s idempotency check: a job in one of these states still might run, or
# is waiting to, so re-enqueuing the same (node_id, input_hash) must not duplicate it.
LIVE_STATES = ("queued", "running", "retry_later", "needs_human")

_MIGRATIONS: dict[int, str] = {
    1: """
        CREATE TABLE job (
            id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            lane TEXT NOT NULL,
            state TEXT NOT NULL,
            cmd_json TEXT NOT NULL,
            authorised_by TEXT,
            budget_id TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            not_before REAL,
            created_at REAL NOT NULL,
            started_at REAL,
            finished_at REAL,
            summary TEXT
        );
        CREATE INDEX idx_job_node_hash ON job(node_id, input_hash);
        CREATE INDEX idx_job_lane_state ON job(lane, state);
        CREATE INDEX idx_job_budget ON job(budget_id, state);

        CREATE TABLE event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            seq INTEGER NOT NULL,
            kind TEXT NOT NULL,
            json TEXT NOT NULL,
            at REAL NOT NULL
        );
        CREATE INDEX idx_event_job_seq ON event(job_id, seq);

        CREATE TABLE budget (
            id TEXT PRIMARY KEY,
            cap REAL NOT NULL,
            spent REAL NOT NULL DEFAULT 0,
            unit TEXT NOT NULL DEFAULT 'usd'
        );
    """,
    # T06 carry-over #2: authorisations are data, not process state. `scope` is a JSON blob
    # ({"node_ids": [...]} or {"workflow_id": "..."} or {} for "the whole plan"); every job
    # a given authorisation ever allowed names it, so a restarted process (with no in-memory
    # Authorization object at all) can still see exactly what authorised each job.
    2: """
        CREATE TABLE authorisation (
            id TEXT PRIMARY KEY,
            budget_id TEXT NOT NULL,
            scope TEXT NOT NULL,
            covers_downstream INTEGER NOT NULL DEFAULT 0,
            by TEXT NOT NULL,
            at REAL NOT NULL
        );
        ALTER TABLE job ADD COLUMN authorisation_id TEXT;
        CREATE INDEX idx_job_authorisation ON job(authorisation_id);
    """,
    # T31: a spending job's pre-run estimate, in its budget's unit. Live jobs' estimates are
    # *reserved* against the budget (`budget.reserved`), so headroom is cap - spent -
    # reserved and two enqueues can't each spend the same headroom.
    3: """
        ALTER TABLE job ADD COLUMN estimate REAL;
    """,
}

SCHEMA_VERSION = max(_MIGRATIONS)


def db_path(project_root: str | Path) -> Path:
    return store_root(project_root) / "queue.db"


def migrate(con: sqlite3.Connection) -> None:
    current = con.execute("PRAGMA user_version").fetchone()[0]
    for version in sorted(v for v in _MIGRATIONS if v > current):
        con.executescript(_MIGRATIONS[version])
        con.execute(f"PRAGMA user_version = {version}")
    con.commit()


def connect(project_root: str | Path) -> sqlite3.Connection:
    path = db_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=30.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=30000")
    migrate(con)
    return con


@contextmanager
def open_db(project_root: str | Path) -> Iterator[sqlite3.Connection]:
    """`with open_db(project_root) as con:` -- always closes, even if the body raises."""
    con = connect(project_root)
    try:
        yield con
    finally:
        con.close()
