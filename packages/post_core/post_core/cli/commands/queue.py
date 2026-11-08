"""`post run`, `post queue list|show <job>|cancel|serve`, `post approve|revoke`,
`post budget set|show`, `post doctor`."""
from __future__ import annotations

import argparse
import functools
import json
import signal
import threading
from pathlib import Path

from ...graph import approvals as approvals_mod
from ...graph.hashing import compute_hashes
from ...graph.plan import plan as plan_fn
from ...graph.state import compute_states
from ...queue import db as db_mod
from ...queue import executor as executor_mod
from ...queue import budget as budget_mod
from ...queue.enqueue import Authorization, SpendNotAuthorized, enqueue
from ...queue.executor import Executor
from .. import config as config_mod
from ..context import build_registry, cmd_for as cmd_for_fn, resolve_project_root
from ..output import CLIError
from .workflow import _load_workflow


def run(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    workflow, _rev = _load_workflow(root, args.workflow)
    registry = build_registry()
    targets = json.loads(args.targets) if args.targets else None
    hashes = compute_hashes(workflow, registry)
    states = compute_states(workflow, registry, root, hashes=hashes)
    plan = plan_fn(workflow, registry, states, targets=targets, from_node=args.from_node)

    # T31: `run` never creates a budget -- `post budget set` does, explicitly. `enqueue`
    # persists the authorisation only if the budget accepts the whole run.
    authorization = None
    if args.budget:
        node_ids = frozenset(json.loads(args.node_ids)) if args.node_ids else None
        authorization = Authorization(
            budget_id=args.budget, by=args.by or "cli", node_ids=node_ids,
            workflow_id=workflow.id, covers_downstream=args.covers_downstream,
        )

    try:
        job_ids = enqueue(
            root, workflow, registry, hashes, plan,
            cmd_for=functools.partial(cmd_for_fn, workflow), authorization=authorization,
        )
    except SpendNotAuthorized as exc:
        raise CLIError(str(exc)) from exc
    return {"workflow_id": workflow.id, "job_ids": job_ids, "plan": plan}


def _event_rows(root: Path, job_id: str) -> list[dict]:
    with db_mod.open_db(root) as con:
        rows = con.execute(
            "SELECT seq, kind, json, at FROM event WHERE job_id=? ORDER BY seq", (job_id,)
        ).fetchall()
    return [{"seq": r["seq"], "kind": r["kind"], "event": json.loads(r["json"]), "at": r["at"]} for r in rows]


def queue_list(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    query = "SELECT * FROM job WHERE 1=1"
    params: list = []
    if args.workflow:
        query += " AND workflow_id=?"
        params.append(args.workflow)
    if args.state:
        query += " AND state=?"
        params.append(args.state)
    query += " ORDER BY created_at"
    with db_mod.open_db(root) as con:
        rows = [dict(r) for r in con.execute(query, params).fetchall()]
    return {"jobs": rows}


def queue_show(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    with db_mod.open_db(root) as con:
        row = con.execute("SELECT * FROM job WHERE id=?", (args.job,)).fetchone()
    if row is None:
        raise CLIError(f"no job {args.job!r}")
    return {"job": dict(row), "events": _event_rows(root, args.job)}


def queue_cancel(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    cancelled = executor_mod.cancel_job(root, args.job)
    if not cancelled:
        raise CLIError(f"job {args.job!r} cannot be cancelled (not queued/retry_later/needs_human)")
    return {"job_id": args.job, "cancelled": True}


def queue_serve(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    workflow, _rev = _load_workflow(root, args.workflow)
    registry = build_registry()
    ex = Executor(project_root=root, workflow=workflow, registry=registry,
                  cmd_for=functools.partial(cmd_for_fn, workflow))

    if args.once:
        ex.recover_interrupted()
        ran: list[str] = []
        while True:
            batch = ex.run_once()
            if not batch:
                break
            ran.extend(batch)
        return {"workflow_id": workflow.id, "ran": ran}

    stop = threading.Event()

    def _stop(_signum, _frame) -> None:
        stop.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    ex.serve(stop)
    return {"workflow_id": workflow.id, "stopped": True}


def approve(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    approval = approvals_mod.approve(root, args.content_hash, args.by or "cli")
    return {"content_hash": approval.content_hash, "by": approval.by, "at": approval.at}


def revoke(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    approvals_mod.revoke(root, args.content_hash)
    return {"content_hash": args.content_hash, "revoked": True}


def budget_set(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    try:
        return {"budget": budget_mod.set_budget(root, args.id, args.cap, args.unit)}
    except ValueError as exc:
        raise CLIError(str(exc)) from exc


def budget_show(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    row = budget_mod.get_budget(root, args.id)
    if row is None:
        raise CLIError(f"no budget {args.id!r}")
    return {"budget": row}


def doctor(args: argparse.Namespace) -> dict:
    root = None
    if args.root:
        try:
            root = resolve_project_root(args.root)
        except CLIError:
            root = Path(args.root).resolve()  # report it even if not yet initialised
    return config_mod.doctor_report(root)


__all__ = [
    "run", "queue_list", "queue_show", "queue_cancel", "queue_serve",
    "approve", "revoke", "budget_set", "budget_show", "doctor",
]
