"""T31 spend safety in the core: budgets exist only when explicitly set, carry one unit, and
refuse any run whose estimate they can't cover; the executor counts only the budget's unit
and never records a spending job as free; a chain never spends past what was authorised."""
from __future__ import annotations

from typing import Optional

import pytest
from pydantic import BaseModel, ConfigDict

from post_core.graph.hashing import compute_hashes
from post_core.graph.plan import plan as plan_fn
from post_core.graph.registry import NodeRegistry, register_builtins
from post_core.graph.state import NodeState, compute_states
from post_core.graph.types import Cost, InputSpec, NodeType, OutputSpec
from post_core.graph.workflow import Edge, Node, Workflow
from post_core.queue import db as db_mod
from post_core.queue.budget import get_budget, set_budget
from post_core.queue.enqueue import (
    Authorization, BudgetUnitMismatch, NoEstimate, OverBudget, UnknownBudget, enqueue,
)
from post_core.queue.executor import Executor

from worker_scripts import write_ok_worker


class P(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = ""


def _credits(amount: float):
    def _estimate(params: P) -> Optional[Cost]:
        return Cost(amount=amount, unit="credits", provider="fake-higgsfield")
    return _estimate


SPEND_SRC = NodeType(
    id="t.spend_src", outputs=(OutputSpec(name="video", type="video"),), params_schema=P,
    spends=True, lane="single", estimate_cost=_credits(1.0),
)
FREE = NodeType(
    id="t.free", inputs=(InputSpec(name="video", type="video"),),
    outputs=(OutputSpec(name="video", type="video"),), params_schema=P, lane="single",
)
SPEND_NEXT = NodeType(
    id="t.spend_next", inputs=(InputSpec(name="video", type="video"),),
    outputs=(OutputSpec(name="video", type="video"),), params_schema=P,
    spends=True, lane="single", estimate_cost=_credits(2.0),
)
SPEND_NO_ESTIMATE = NodeType(
    id="t.spend_blind", outputs=(OutputSpec(name="video", type="video"),), params_schema=P,
    spends=True, lane="single",
)


@pytest.fixture
def reg() -> NodeRegistry:
    r = NodeRegistry()
    register_builtins(r)
    for nt in (SPEND_SRC, FREE, SPEND_NEXT, SPEND_NO_ESTIMATE):
        r.register(nt)
    return r


def _single(type_id: str, n: int = 1) -> Workflow:
    return Workflow(recipe_id="r", nodes=[Node(id=f"g{i}", type_id=type_id, params={"text": str(i)}) for i in range(n)], edges=[])


def _chain() -> Workflow:
    nodes = [
        Node(id="a", type_id="t.spend_src", params={"text": "a"}),
        Node(id="b", type_id="t.free", params={"text": "b"}),
        Node(id="c", type_id="t.spend_next", params={"text": "c"}),
    ]
    edges = [
        Edge(id="e1", from_node="a", from_output="video", to_node="b", to_input="video"),
        Edge(id="e2", from_node="b", from_output="video", to_node="c", to_input="video"),
    ]
    return Workflow(recipe_id="r", nodes=nodes, edges=edges)


def _plan(wf, reg, root):
    hashes = compute_hashes(wf, reg)
    return hashes, plan_fn(wf, reg, compute_states(wf, reg, root, hashes=hashes))


def _enqueue(root, wf, reg, auth):
    hashes, plan1 = _plan(wf, reg, root)
    return enqueue(root, wf, reg, hashes, plan1, cmd_for=lambda nid: ["echo", nid], authorization=auth)


def _counts(root) -> dict:
    with db_mod.open_db(root) as con:
        return {t: con.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in ("job", "authorisation", "budget")}


def test_run_naming_an_unknown_budget_is_refused_and_creates_nothing(tmp_path, reg):
    with pytest.raises(UnknownBudget, match="unknown budget 'nope'"):
        _enqueue(tmp_path, _single("t.spend_src"), reg, Authorization(budget_id="nope", by="t"))
    assert _counts(tmp_path) == {"job": 0, "authorisation": 0, "budget": 0}
    assert get_budget(tmp_path, "nope") is None


def test_spend_estimated_in_another_unit_is_refused(tmp_path, reg):
    set_budget(tmp_path, "b", cap=100.0, unit="usd")
    with pytest.raises(BudgetUnitMismatch, match="estimated in credits but budget 'b' counts usd"):
        _enqueue(tmp_path, _single("t.spend_src"), reg, Authorization(budget_id="b", by="t"))
    assert _counts(tmp_path)["job"] == 0


def test_estimate_over_headroom_is_refused_even_with_headroom_left(tmp_path, reg):
    set_budget(tmp_path, "b", cap=2.5, unit="credits")
    with pytest.raises(OverBudget, match="estimate 3 credits exceeds budget 'b' headroom of 2.5"):
        _enqueue(tmp_path, _single("t.spend_src", n=3), reg, Authorization(budget_id="b", by="t"))
    assert _counts(tmp_path) == {"job": 0, "authorisation": 0, "budget": 1}
    set_budget(tmp_path, "b", cap=3.0, unit="credits")  # exactly the estimate: allowed
    assert len(_enqueue(tmp_path, _single("t.spend_src", n=3), reg, Authorization(budget_id="b", by="t"))) == 3


def test_live_jobs_reserve_their_estimate(tmp_path, reg):
    set_budget(tmp_path, "b", cap=1.5, unit="credits")
    first = Workflow(recipe_id="r", nodes=[Node(id="x", type_id="t.spend_src", params={"text": "x"})], edges=[])
    second = Workflow(recipe_id="r", nodes=[Node(id="y", type_id="t.spend_src", params={"text": "y"})], edges=[])
    assert len(_enqueue(tmp_path, first, reg, Authorization(budget_id="b", by="t"))) == 1
    with pytest.raises(OverBudget):  # 1.0 of the 1.5 cap is already reserved by x's queued job
        _enqueue(tmp_path, second, reg, Authorization(budget_id="b", by="t"))


def test_spending_node_with_no_estimate_is_refused(tmp_path, reg):
    set_budget(tmp_path, "b", cap=100.0, unit="credits")
    with pytest.raises(NoEstimate, match="will not spend blind"):
        _enqueue(tmp_path, _single("t.spend_blind"), reg, Authorization(budget_id="b", by="t"))


def test_budget_unit_cannot_switch_after_spend(tmp_path):
    set_budget(tmp_path, "b", cap=5.0, unit="credits")
    with db_mod.open_db(tmp_path) as con:
        con.execute("UPDATE budget SET spent=1.0 WHERE id='b'")
        con.commit()
    with pytest.raises(ValueError, match="cannot switch to usd"):
        set_budget(tmp_path, "b", cap=5.0, unit="usd")
    assert set_budget(tmp_path, "b", cap=9.0, unit="credits")["cap"] == 9.0


def _run_single(tmp_path, reg, worker_cost: float, worker_unit: str):
    wf = _single("t.spend_src")
    set_budget(tmp_path, "b", cap=10.0, unit="credits")
    cmd = write_ok_worker(tmp_path, "w", out_name="w.bin", cost=worker_cost, unit=worker_unit)
    hashes, plan1 = _plan(wf, reg, tmp_path)
    enqueue(tmp_path, wf, reg, hashes, plan1, cmd_for=lambda nid: cmd, authorization=Authorization(budget_id="b", by="t"))
    Executor(project_root=tmp_path, workflow=wf, registry=reg, cmd_for=lambda nid: cmd).run_once()
    with db_mod.open_db(tmp_path) as con:
        job = dict(con.execute("SELECT * FROM job").fetchone())
    return job, get_budget(tmp_path, "b")


def test_cost_in_a_mismatched_unit_is_not_summed_and_fails_the_job(tmp_path, reg):
    job, budget = _run_single(tmp_path, reg, worker_cost=7.0, worker_unit="usd")
    assert job["state"] == "failed"
    assert "cause: budget-unit" in job["summary"] and "usd" in job["summary"]
    assert budget["spent"] == pytest.approx(1.0)  # the reserved credits estimate, never the 7 usd


def test_matching_cost_is_recorded_as_reported(tmp_path, reg):
    job, budget = _run_single(tmp_path, reg, worker_cost=1.25, worker_unit="credits")
    assert job["state"] == "ok"
    assert budget["spent"] == pytest.approx(1.25)


def test_spending_job_that_reports_no_cost_is_charged_its_estimate(tmp_path, reg):
    job, budget = _run_single(tmp_path, reg, worker_cost=0.0, worker_unit="credits")
    assert job["state"] == "ok"
    assert budget["spent"] == pytest.approx(1.0)  # never recorded as free


def test_plan_lists_the_downstream_spends_a_run_leads_to(tmp_path, reg):
    _hashes, plan1 = _plan(_chain(), reg, tmp_path)
    assert plan1.runnable == ["a"]
    assert [(s.node_id, s.amount, s.unit, s.runnable) for s in plan1.spends] == [
        ("a", 1.0, "credits", True), ("c", 2.0, "credits", False),
    ]


def _drive_chain(tmp_path, reg, cap: float, node_ids: frozenset[str]):
    wf = _chain()
    set_budget(tmp_path, "click", cap=cap, unit="credits")
    cmds = {
        "a": write_ok_worker(tmp_path, "wa", out_name="a.bin", cost=1.0, unit="credits"),
        "b": write_ok_worker(tmp_path, "wb", out_name="b.bin", cost=0.0, unit="credits"),
        "c": write_ok_worker(tmp_path, "wc", out_name="c.bin", cost=2.0, unit="credits"),
    }
    auth = Authorization(budget_id="click", by="web", node_ids=node_ids, workflow_id=wf.id, covers_downstream=True)
    hashes, plan1 = _plan(wf, reg, tmp_path)
    enqueue(tmp_path, wf, reg, hashes, plan1, cmd_for=lambda nid: cmds[nid], authorization=auth)
    # No in-memory authorisation: the API's background runtime only has the persisted one.
    ex = Executor(project_root=tmp_path, workflow=wf, registry=reg, cmd_for=lambda nid: cmds[nid])
    for _ in range(5):
        if not ex.run_once():
            break
    hashes = compute_hashes(wf, reg)
    return compute_states(wf, reg, tmp_path, hashes=hashes), get_budget(tmp_path, "click")


def test_chain_continues_through_a_free_step_to_the_next_authorised_spend(tmp_path, reg):
    states, budget = _drive_chain(tmp_path, reg, cap=3.0, node_ids=frozenset({"a", "c"}))
    assert states == {"a": NodeState.DONE, "b": NodeState.DONE, "c": NodeState.DONE}
    assert budget["spent"] == pytest.approx(3.0)


def test_chain_never_spends_past_the_cap_it_was_shown(tmp_path, reg):
    states, budget = _drive_chain(tmp_path, reg, cap=2.5, node_ids=frozenset({"a", "c"}))
    assert states["b"] == NodeState.DONE
    assert states["c"] == NodeState.READY  # refused (2.0 > 1.5 left), waiting on a fresh click
    assert budget["spent"] == pytest.approx(1.0)


def test_chain_only_spends_on_the_node_ids_it_named(tmp_path, reg):
    states, _budget = _drive_chain(tmp_path, reg, cap=10.0, node_ids=frozenset({"a"}))
    assert states["c"] == NodeState.READY


def test_free_step_queued_before_the_click_joins_its_authorised_chain(tmp_path, reg):
    """Race seen in the e2e: the card's free-step nudge queues `b` with no authorisation just
    before the confirmed click's run; the click must still be able to continue past `b`."""
    wf = _chain()
    hashes = compute_hashes(wf, reg)
    from worker_scripts import write_manifest

    write_manifest(tmp_path, "t.spend_src", hashes["a"])  # a already built: b is ready
    hashes, plan1 = _plan(wf, reg, tmp_path)
    (free_job,) = enqueue(tmp_path, wf, reg, hashes, plan1, cmd_for=lambda nid: ["echo"])
    set_budget(tmp_path, "click", cap=2.0, unit="credits")
    auth = Authorization(budget_id="click", by="web", node_ids=frozenset({"c"}), covers_downstream=True)
    assert enqueue(tmp_path, wf, reg, hashes, plan1, cmd_for=lambda nid: ["echo"], authorization=auth) == [free_job]
    with db_mod.open_db(tmp_path) as con:
        assert con.execute("SELECT authorisation_id FROM job WHERE id=?", (free_job,)).fetchone()[0] is not None


def test_free_step_already_running_when_the_click_lands_still_continues_its_chain(tmp_path, reg):
    """The same race one step later (the enrich e2e once T33 let `motion.from_frame` succeed):
    `b` was already claimed and running when the confirmed click attached its authorisation,
    so finishing `b` must read the job's authorisation from the queue, not its claim-time row."""
    from post_core.workers import runner as runner_mod
    from worker_scripts import write_manifest

    wf = _chain()
    write_manifest(tmp_path, "t.spend_src", compute_hashes(wf, reg)["a"])  # a built: b ready
    hashes, plan1 = _plan(wf, reg, tmp_path)
    cmds = {
        "b": write_ok_worker(tmp_path, "wb", out_name="b.bin", cost=0.0, unit="credits"),
        "c": write_ok_worker(tmp_path, "wc", out_name="c.bin", cost=2.0, unit="credits"),
    }
    enqueue(tmp_path, wf, reg, hashes, plan1, cmd_for=lambda nid: cmds[nid])  # the free-step nudge
    set_budget(tmp_path, "click", cap=2.0, unit="credits")
    auth = Authorization(budget_id="click", by="web", node_ids=frozenset({"c"}), workflow_id=wf.id, covers_downstream=True)
    clicked: list[str] = []

    def click_lands_mid_run(cmd, **kwargs):
        if not clicked:  # the confirmed click arrives while `b` runs
            clicked.extend(enqueue(tmp_path, wf, reg, hashes, plan1, cmd_for=lambda nid: cmds[nid], authorization=auth))
        return runner_mod.run(cmd, **kwargs)

    ex = Executor(project_root=tmp_path, workflow=wf, registry=reg, cmd_for=lambda nid: cmds[nid], run_fn=click_lands_mid_run)
    for _ in range(5):
        if not ex.run_once():
            break
    states = compute_states(wf, reg, tmp_path, hashes=compute_hashes(wf, reg))
    assert states == {"a": NodeState.DONE, "b": NodeState.DONE, "c": NodeState.DONE}
    assert get_budget(tmp_path, "click")["spent"] == pytest.approx(2.0)
