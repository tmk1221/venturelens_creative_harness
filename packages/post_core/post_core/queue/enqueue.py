"""`enqueue(plan, authorization)`: turn a `graph.plan.Plan`'s runnable nodes into durable
job rows.

Refuses a `spends` node with no authorisation covering it, and (T31, `budget.check_spend`) any
spend its budget refuses: an unknown budget, an estimate in another unit, no estimate at all,
or estimates summing past the budget's headroom. Checks, the authorisation row and the job
rows all happen in one write transaction, so a refused run leaves nothing behind.
Idempotent on `(node_id, input_hash)`: while a job for that pair is still live (queued,
running, retry_later, needs_human, interrupted), enqueuing it again returns the existing
job's id instead of inserting a duplicate -- no double spend from a re-plan/re-enqueue race.

Only `compute`-kind nodes get a job here: `source`/`pick`/`approve` nodes are satisfied by
ingest, a human pick, or an approval record, never by running a worker command.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ..graph.plan import Plan, node_estimate
from ..graph.registry import NodeRegistry
from ..graph.types import Cost
from ..graph.workflow import Workflow
from ..model.base import new_id
from . import authorisation as authorisation_mod, budget as budget_mod, db as db_mod
from .budget import (  # re-exported: callers have always imported these from here
    BudgetUnitMismatch, NoEstimate, OverBudget, SpendNotAuthorized, UnknownBudget,
)

CmdFor = Callable[[str], list]


@dataclass(frozen=True)
class Authorization:
    """One human/batch decision to let spending nodes run against a named budget.

    `node_ids=None` covers every spends node the caller enqueues with it; a non-None set
    restricts it to those node ids only (e.g. a targeted re-run should not silently also
    authorise an unrelated spend elsewhere in the same workflow).

    `id` is None for an authorisation that hasn't been persisted yet -- `enqueue()` persists
    it (T06 carry-over #2: authorisations are data, not process state) the first time it is
    used and returns/records the persisted id from then on. `covers_downstream=True` means
    the authorisation also covers nodes newly made ready downstream of the ones it named
    (the executor's own auto-continuation, T05 carry-over #1), not just its original scope.
    """

    budget_id: str
    by: str
    node_ids: Optional[frozenset[str]] = None
    id: Optional[str] = None
    workflow_id: Optional[str] = None
    covers_downstream: bool = False

    def covers(self, node_id: str) -> bool:
        return self.node_ids is None or node_id in self.node_ids


def _existing_live_job(con, node_id: str, input_hash: str) -> Optional[str]:
    placeholders = ",".join("?" for _ in db_mod.LIVE_STATES)
    row = con.execute(
        f"SELECT id FROM job WHERE node_id = ? AND input_hash = ? AND state IN ({placeholders})",
        (node_id, input_hash, *db_mod.LIVE_STATES),
    ).fetchone()
    return row["id"] if row else None


def enqueue(
    project_root: str | Path,
    workflow: Workflow,
    registry: NodeRegistry,
    hashes: dict[str, Optional[str]],
    plan: Plan,
    cmd_for: CmdFor,
    authorization: Optional[Authorization] = None,
) -> list[str]:
    """Enqueue every `compute`-kind node in `plan.runnable`. Returns one job id per such
    node, in `plan.runnable` order (an existing live job's id if one already covers that
    node's current `(node_id, input_hash)`).

    With an authorisation, every job it allows carries its id -- free ones too, so the
    executor's auto-continuation can follow a chain through a free step (e.g. `motion.
    from_frame`) to the next authorised spend. Only spending jobs name the budget."""
    compute = [
        nid for nid in plan.runnable
        if registry.get(workflow.node(nid).type_id).kind == "compute"
    ]
    for node_id in compute:
        if hashes.get(node_id) is None:
            raise ValueError(f"node {node_id!r} has no resolved input hash")

    job_ids: list[str] = []
    with db_mod.open_db(project_root) as con:
        con.execute("BEGIN IMMEDIATE")  # check + insert under one write lock
        new_spend: dict[str, Optional[Cost]] = {}
        for node_id in compute:
            if not registry.get(workflow.node(node_id).type_id).spends:
                continue
            if authorization is None or not authorization.covers(node_id):
                raise SpendNotAuthorized(
                    f"{node_id}: this node spends and has no authorisation covering it"
                )
            if _existing_live_job(con, node_id, hashes[node_id]) is None:
                new_spend[node_id] = node_estimate(workflow, registry, node_id)
        if authorization is not None:
            budget_mod.check_spend(con, authorization.budget_id, new_spend)
            if authorization.id is None:
                # T06 carry-over #2: authorisations are data, not process state.
                authorization = authorisation_mod.insert(
                    con, authorization.budget_id, authorization.by,
                    node_ids=authorization.node_ids, workflow_id=authorization.workflow_id,
                    covers_downstream=authorization.covers_downstream,
                )

        for node_id in compute:
            node_type = registry.get(workflow.node(node_id).type_id)
            input_hash = hashes[node_id]
            existing = _existing_live_job(con, node_id, input_hash)
            if existing is not None:
                if authorization is not None:
                    # A free step already queued without one joins this authorised chain.
                    con.execute(
                        "UPDATE job SET authorisation_id=? WHERE id=? AND authorisation_id IS NULL",
                        (authorization.id, existing),
                    )
                job_ids.append(existing)
                continue
            spends = node_type.spends
            estimate = new_spend.get(node_id)
            job_id = new_id()
            con.execute(
                """INSERT INTO job (id, workflow_id, node_id, input_hash, lane, state,
                                    cmd_json, authorised_by, budget_id, authorisation_id,
                                    attempts, not_before, created_at, started_at,
                                    finished_at, summary, estimate)
                   VALUES (?,?,?,?,?,'queued',?,?,?,?,0,NULL,?,NULL,NULL,NULL,?)""",
                (
                    job_id, workflow.id, node_id, input_hash, node_type.lane,
                    json.dumps(cmd_for(node_id)),
                    authorization.by if spends else None,
                    authorization.budget_id if spends else None,
                    authorization.id if authorization is not None else None,
                    time.time(),
                    estimate.amount if (spends and estimate is not None) else None,
                ),
            )
            job_ids.append(job_id)
        con.commit()
    return job_ids


__all__ = [
    "Authorization", "SpendNotAuthorized", "UnknownBudget", "BudgetUnitMismatch", "OverBudget",
    "NoEstimate", "enqueue", "CmdFor",
]
