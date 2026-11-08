"""Budgets: the only thing a spend authorisation can name, and the only place spend is counted
(T31 -- AGENTS.md: "Nothing spends money without an explicit authorisation recorded in the
request. Enforce in the core.").

Rules this module enforces, so no caller (CLI, API, executor) can forget one:
  - A budget exists only after an explicit `set_budget` call (`post budget set`,
    `PUT .../budgets/{id}`). Running a workflow never creates one; naming a budget that was
    never set is refused (`UnknownBudget`).
  - A budget counts one unit, the provider's own (`credits` for Higgsfield, `usd` for
    Deepgram). A spending node whose estimate is in another unit is refused up front
    (`BudgetUnitMismatch`), and a finished job's cost in another unit is never added.
  - Headroom is `cap - spent - reserved`, where `reserved` is the pre-run estimate of every
    still-live job on that budget -- so two enqueues against one budget can't each see the
    full cap, and a chain can never spend past the estimate the person was shown.
  - A spending node with no estimate is refused (`NoEstimate`): nothing spends blind.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Mapping, Optional

from ..graph.types import Cost
from . import db as db_mod

# Float slack for "estimate exactly equals the cap" (the web sets cap = the shown estimate).
EPSILON = 1e-9


class SpendNotAuthorized(ValueError):
    """A `spends` node may not run: no authorisation covers it, or its budget refuses it."""

    reason = "spend_not_authorized"


class UnknownBudget(SpendNotAuthorized):
    reason = "unknown_budget"


class BudgetUnitMismatch(SpendNotAuthorized):
    reason = "unit_mismatch"


class OverBudget(SpendNotAuthorized):
    reason = "over_headroom"


class NoEstimate(SpendNotAuthorized):
    reason = "no_estimate"


def set_budget(project_root: str | Path, budget_id: str, cap: float, unit: str) -> dict:
    """Create a budget, or change an existing one's cap. The only way a budget comes to
    exist. A budget's unit is fixed once anything has been spent or reserved against it --
    re-labelling spent credits as dollars would silently corrupt the count."""
    if cap < 0:
        raise ValueError(f"budget {budget_id!r}: cap must be >= 0, got {cap}")
    if not unit or not unit.strip():
        raise ValueError(f"budget {budget_id!r}: unit is required (e.g. 'credits' or 'usd')")
    with db_mod.open_db(project_root) as con:
        row = con.execute("SELECT * FROM budget WHERE id=?", (budget_id,)).fetchone()
        if row is None:
            con.execute("INSERT INTO budget (id, cap, spent, unit) VALUES (?,?,0,?)", (budget_id, cap, unit))
        else:
            if unit != row["unit"] and (row["spent"] > 0 or reserved(con, budget_id) > 0):
                raise ValueError(
                    f"budget {budget_id!r} already counts {row['unit']}; it cannot switch to {unit}"
                )
            con.execute("UPDATE budget SET cap=?, unit=? WHERE id=?", (cap, unit, budget_id))
        con.commit()
        return dict(con.execute("SELECT * FROM budget WHERE id=?", (budget_id,)).fetchone())


def get_budget(project_root: str | Path, budget_id: str) -> Optional[dict]:
    with db_mod.open_db(project_root) as con:
        row = con.execute("SELECT * FROM budget WHERE id=?", (budget_id,)).fetchone()
    return dict(row) if row is not None else None


def reserved(con: sqlite3.Connection, budget_id: str) -> float:
    """The summed pre-run estimate of every live job (queued/running/held) on this budget."""
    placeholders = ",".join("?" for _ in db_mod.LIVE_STATES)
    row = con.execute(
        f"SELECT COALESCE(SUM(estimate), 0) AS r FROM job WHERE budget_id=? AND state IN ({placeholders})",
        (budget_id, *db_mod.LIVE_STATES),
    ).fetchone()
    return float(row["r"] or 0.0)


def check_spend(con: sqlite3.Connection, budget_id: str, estimates: Mapping[str, Optional[Cost]]) -> None:
    """Raise unless `budget_id` exists and can cover every node in `estimates` (node id ->
    its pre-run estimate; None means no estimate could be made). Read-only."""
    row = con.execute("SELECT * FROM budget WHERE id=?", (budget_id,)).fetchone()
    if row is None:
        raise UnknownBudget(f"unknown budget {budget_id!r}: create it first with an explicit budget call")
    unit = row["unit"]
    total = 0.0
    for node_id, cost in estimates.items():
        if cost is None:
            raise NoEstimate(f"{node_id}: no cost estimate is available, so it will not spend blind")
        if cost.unit != unit:
            raise BudgetUnitMismatch(
                f"{node_id}: estimated in {cost.unit} but budget {budget_id!r} counts {unit}"
            )
        total += cost.amount
    if not estimates:
        return
    headroom = row["cap"] - row["spent"] - reserved(con, budget_id)
    if headroom <= EPSILON or total > headroom + EPSILON:
        raise OverBudget(
            f"estimate {total:g} {unit} exceeds budget {budget_id!r} headroom of {max(headroom, 0):g} {unit}"
        )


def record_cost(
    project_root: str | Path, job: dict, cost_total: Mapping[str, float], *, charge_estimate: bool = True,
) -> Optional[str]:
    """Add a finished spending job's cost to its budget. Only amounts in the budget's own
    unit are added. A successful job that reports nothing countable is charged its reserved
    estimate instead (`charge_estimate`) -- a real call is never recorded as free. Returns a
    one-sentence failure summary when the job reported cost in another unit (that amount
    is NOT added), else None.

    Spent reaching the cap holds every still-queued job on the budget at `needs_human`."""
    budget_id = job.get("budget_id")
    if not budget_id:
        return None
    with db_mod.open_db(project_root) as con:
        row = con.execute("SELECT unit FROM budget WHERE id=?", (budget_id,)).fetchone()
        if row is None:
            return f"its budget {budget_id!r} no longer exists (cause: budget-unknown)"
        unit = row["unit"]
        charged = float(cost_total.get(unit, 0.0) or 0.0)
        if charged <= 0 and charge_estimate and job.get("estimate"):
            charged = float(job["estimate"])
        con.execute("UPDATE budget SET spent = spent + ? WHERE id=?", (charged, budget_id))
        over = con.execute("SELECT cap, spent FROM budget WHERE id=?", (budget_id,)).fetchone()
        if over["spent"] >= over["cap"]:
            con.execute(
                "UPDATE job SET state='needs_human', summary='budget cap reached (cause: budget-cap)' "
                "WHERE budget_id=? AND state='queued'",
                (budget_id,),
            )
        con.commit()
    mismatched = sorted(u for u, amount in cost_total.items() if u != unit and amount)
    if mismatched:
        return (
            f"the worker reported cost in {', '.join(mismatched)} but budget {budget_id!r} counts "
            f"{unit}, so it was not added (cause: budget-unit)"
        )
    return None


__all__ = [
    "SpendNotAuthorized", "UnknownBudget", "BudgetUnitMismatch", "OverBudget", "NoEstimate",
    "set_budget", "get_budget", "reserved", "check_spend", "record_cost", "EPSILON",
]
