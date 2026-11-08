"""`/api/projects/{pid}/queue`, `/approvals`, `/budgets`. Mirrors `post queue ...`,
`post approve|revoke`, `post budget ...` -- straight reads/writes against the queue's
SQLite db and the graph's approval ledger, same as the CLI."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from post_core.graph import approvals as approvals_mod
from post_core.queue import budget as budget_mod, db as db_mod, executor as executor_mod
from post_core.recipes import consent as consent_mod

from ..deps import get_project_root
from ..errors import PathTraversal
from ..models import ApprovalOut, BudgetOut, CancelOut, QueueListOut, QueueShowOut, RevokeOut

router = APIRouter(prefix="/api/projects/{pid}", tags=["queue"])


def _hex_id(value: str, field: str = "id") -> str:
    """Every id used as a lookup key here (job id, budget id, content hash) is a plain
    token, never a path -- reject anything that looks like it's trying to escape into a
    filesystem path (T10 acceptance: "path traversal attempts rejected")."""
    if not value or "/" in value or "\\" in value or ".." in value:
        raise PathTraversal(f"{field} must not contain path separators: {value!r}")
    return value


@router.get("/queue", response_model=QueueListOut)
def queue_list(
    workflow: Optional[str] = Query(None), state: Optional[str] = Query(None),
    root: Path = Depends(get_project_root),
) -> QueueListOut:
    query = "SELECT * FROM job WHERE 1=1"
    params: list = []
    if workflow:
        query += " AND workflow_id=?"
        params.append(workflow)
    if state:
        query += " AND state=?"
        params.append(state)
    query += " ORDER BY created_at"
    with db_mod.open_db(root) as con:
        rows = [dict(r) for r in con.execute(query, params).fetchall()]
    return QueueListOut(jobs=rows)


def _event_rows(root: Path, job_id: str) -> list[dict]:
    import json

    with db_mod.open_db(root) as con:
        rows = con.execute(
            "SELECT seq, kind, json, at FROM event WHERE job_id=? ORDER BY seq", (job_id,)
        ).fetchall()
    return [{"seq": r["seq"], "kind": r["kind"], "event": json.loads(r["json"]), "at": r["at"]} for r in rows]


@router.get("/queue/{job_id}", response_model=QueueShowOut)
def queue_show(job_id: str, root: Path = Depends(get_project_root)) -> QueueShowOut:
    _hex_id(job_id, "job_id")
    with db_mod.open_db(root) as con:
        row = con.execute("SELECT * FROM job WHERE id=?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no job {job_id!r}")
    return QueueShowOut(job=dict(row), events=_event_rows(root, job_id))


@router.post("/queue/{job_id}/cancel", response_model=CancelOut)
def queue_cancel(job_id: str, root: Path = Depends(get_project_root)) -> CancelOut:
    _hex_id(job_id, "job_id")
    cancelled = executor_mod.cancel_job(root, job_id)
    if not cancelled:
        raise HTTPException(status_code=400, detail=f"job {job_id!r} cannot be cancelled")
    return CancelOut(job_id=job_id, cancelled=True)


class ApproveRequest(BaseModel):
    content_hash: str
    by: str = "api"


@router.post("/approvals", response_model=ApprovalOut)
def approve(body: ApproveRequest, root: Path = Depends(get_project_root)) -> ApprovalOut:
    _hex_id(body.content_hash, "content_hash")
    approval = approvals_mod.approve(root, body.content_hash, body.by)
    return ApprovalOut(content_hash=approval.content_hash, by=approval.by, at=approval.at)


@router.delete("/approvals/{content_hash}", response_model=RevokeOut)
def revoke(content_hash: str, root: Path = Depends(get_project_root)) -> RevokeOut:
    _hex_id(content_hash, "content_hash")
    approvals_mod.revoke(root, content_hash)
    return RevokeOut(content_hash=content_hash, revoked=True)


class BudgetSetRequest(BaseModel):
    """T31: the only way a budget comes to exist. `unit` is the provider's own (`credits`
    for Higgsfield, `usd` for Deepgram) -- required, never defaulted."""

    model_config = ConfigDict(extra="forbid")

    cap: float
    unit: str


@router.put("/budgets/{budget_id}", response_model=BudgetOut)
def budget_set(budget_id: str, body: BudgetSetRequest, root: Path = Depends(get_project_root)) -> BudgetOut:
    _hex_id(budget_id, "budget_id")
    return BudgetOut(budget=budget_mod.set_budget(root, budget_id, body.cap, body.unit))


@router.get("/budgets/{budget_id}", response_model=BudgetOut)
def budget_show(budget_id: str, root: Path = Depends(get_project_root)) -> BudgetOut:
    _hex_id(budget_id, "budget_id")
    row = budget_mod.get_budget(root, budget_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no budget {budget_id!r}")
    return BudgetOut(budget=row)


class ConsentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    presenter: str
    release_path: str
    date: str


class ConsentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    presenter: Optional[str] = None
    release_path: Optional[str] = None
    date: Optional[str] = None
    recorded: bool


@router.get("/consent", response_model=ConsentOut)
def consent_show(root: Path = Depends(get_project_root)) -> ConsentOut:
    """T30e: the `aroll.regenerate` recipe's `consent.gate` reads `has_consent`/`read_consent`
    directly (`recipes.instantiate_extra.maybe_preapprove_consent`) -- this is the human-facing
    read: no record yet is not an error, just `recorded: false` with the other fields unset."""
    record = consent_mod.read_consent(root)
    if record is None:
        return ConsentOut(recorded=False)
    return ConsentOut(presenter=record.presenter, release_path=record.release_path, date=record.date, recorded=True)


@router.post("/consent", response_model=ConsentOut)
def consent_record(body: ConsentIn, root: Path = Depends(get_project_root)) -> ConsentOut:
    record = consent_mod.record_consent(root, presenter=body.presenter, release_path=body.release_path, date=body.date)
    return ConsentOut(presenter=record.presenter, release_path=record.release_path, date=record.date, recorded=True)


__all__ = ["router"]
