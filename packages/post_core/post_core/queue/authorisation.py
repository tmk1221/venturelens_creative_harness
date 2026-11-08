"""Authorisations are data, not process state (T06 carry-over #2).

`enqueue.Authorization` used to live only in memory: a caller built one and handed it to
`enqueue()`/`Executor` for that one call. That made an authorisation invisible to a process
that restarts mid-run and to anyone asking "what allowed this job to spend?" after the
fact. This module makes every authorisation a durable row (`authorisation` table,
`db.py` migration 2) with an id; `enqueue.enqueue()` persists one the first time it is used
and stamps that id onto every job row it allows, so the authorisation naming a job survives
a restart even with no authorisation object passed to the new process at all.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

from ..model.base import new_id
from . import db as db_mod


def insert(
    con: sqlite3.Connection,
    budget_id: str,
    by: str,
    *,
    node_ids: Optional[frozenset[str]] = None,
    workflow_id: Optional[str] = None,
    covers_downstream: bool = False,
    at: Optional[float] = None,
) -> "Authorization":
    """Insert a new authorisation row on an already-open connection (no commit) -- lets
    `enqueue()` persist the authorisation in the same transaction as its budget check and
    the jobs it allows (T31), so a refused run leaves no authorisation row behind."""
    from .enqueue import Authorization  # local import: enqueue.py imports this module too

    auth_id = new_id()
    at = at if at is not None else time.time()
    scope = {
        "node_ids": sorted(node_ids) if node_ids is not None else None,
        "workflow_id": workflow_id,
    }
    con.execute(
        "INSERT INTO authorisation (id, budget_id, scope, covers_downstream, by, at) "
        "VALUES (?,?,?,?,?,?)",
        (auth_id, budget_id, json.dumps(scope), int(covers_downstream), by, at),
    )
    return Authorization(
        budget_id=budget_id, by=by, node_ids=node_ids, id=auth_id,
        workflow_id=workflow_id, covers_downstream=covers_downstream,
    )


def record(
    project_root: str | Path,
    budget_id: str,
    by: str,
    *,
    node_ids: Optional[frozenset[str]] = None,
    workflow_id: Optional[str] = None,
    covers_downstream: bool = False,
    at: Optional[float] = None,
) -> "Authorization":
    """Insert a new authorisation row and return it (with its id set)."""
    with db_mod.open_db(project_root) as con:
        auth = insert(
            con, budget_id, by, node_ids=node_ids, workflow_id=workflow_id,
            covers_downstream=covers_downstream, at=at,
        )
        con.commit()
    return auth


def load(project_root: str | Path, authorisation_id: str) -> Optional["Authorization"]:
    """Reconstruct a persisted `Authorization` by id, or None if it isn't there."""
    from .enqueue import Authorization

    with db_mod.open_db(project_root) as con:
        row = con.execute(
            "SELECT * FROM authorisation WHERE id=?", (authorisation_id,)
        ).fetchone()
    if row is None:
        return None
    scope = json.loads(row["scope"])
    node_ids = frozenset(scope["node_ids"]) if scope.get("node_ids") is not None else None
    return Authorization(
        budget_id=row["budget_id"], by=row["by"], node_ids=node_ids, id=row["id"],
        workflow_id=scope.get("workflow_id"), covers_downstream=bool(row["covers_downstream"]),
    )


def load_for_job(project_root: str | Path, job_id: str) -> Optional["Authorization"]:
    """The persisted authorisation that named `job_id`, if any."""
    with db_mod.open_db(project_root) as con:
        row = con.execute(
            "SELECT authorisation_id FROM job WHERE id=?", (job_id,)
        ).fetchone()
    if row is None or not row["authorisation_id"]:
        return None
    return load(project_root, row["authorisation_id"])


__all__ = ["insert", "record", "load", "load_for_job"]
