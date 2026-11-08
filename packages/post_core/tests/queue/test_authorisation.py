"""T06 carry-over #2: authorisations are data, not process state."""
from __future__ import annotations

from post_core.graph.hashing import compute_hashes
from post_core.graph.plan import plan as plan_fn
from post_core.graph.state import compute_states
from post_core.graph.workflow import Node, Workflow
from post_core.queue import authorisation, db as db_mod
from post_core.queue.budget import set_budget
from post_core.queue.enqueue import Authorization, enqueue
from post_core.queue.executor import Executor

from worker_scripts import write_ok_worker


def test_authorisation_is_recorded_and_named_on_its_job(tmp_path, registry):
    wf = Workflow(recipe_id="r1", nodes=[Node(id="g", type_id="fake.spend", params={"text": "x"})], edges=[])
    hashes = compute_hashes(wf, registry)
    states = compute_states(wf, registry, tmp_path, hashes=hashes)
    plan1 = plan_fn(wf, registry, states)
    set_budget(tmp_path, "b1", cap=10.0, unit="usd")
    auth = Authorization(budget_id="b1", by="travis")

    job_ids = enqueue(tmp_path, wf, registry, hashes, plan1,
                       cmd_for=lambda nid: write_ok_worker(tmp_path, "spend_worker", "s.bin"),
                       authorization=auth)
    assert len(job_ids) == 1

    with db_mod.open_db(tmp_path) as con:
        row = con.execute("SELECT authorisation_id FROM job WHERE id=?", (job_ids[0],)).fetchone()
    auth_id = row["authorisation_id"]
    assert auth_id  # persisted, not left null

    reloaded = authorisation.load(tmp_path, auth_id)
    assert reloaded is not None
    assert reloaded.budget_id == "b1"
    assert reloaded.by == "travis"

    same_job = authorisation.load_for_job(tmp_path, job_ids[0])
    assert same_job is not None
    assert same_job.id == auth_id


def test_covers_downstream_authorisation_survives_a_restart(tmp_path, registry):
    """A brand new Executor, built with no in-memory Authorization object at all, must still
    auto-continue node "b" (a spends node made ready only once "a" finishes) because "a"'s
    own job names a persisted, `covers_downstream=True` authorisation -- the authorisation
    naming the finished upstream job is durable, not something the new process needs to be
    handed again (T06 carry-over #2)."""
    from post_core.graph.workflow import Edge

    nodes = [Node(id="a", type_id="fake.spend", params={"text": "a"}),
             Node(id="b", type_id="fake.spend", params={"text": "b"})]
    edges = [Edge(id="e1", from_node="a", from_output="video", to_node="b", to_input="text")]
    wf = Workflow(recipe_id="r1", nodes=nodes, edges=edges)
    set_budget(tmp_path, "b1", cap=100.0, unit="usd")
    persisted = authorisation.record(tmp_path, "b1", "travis", covers_downstream=True)

    hashes = compute_hashes(wf, registry)
    states = compute_states(wf, registry, tmp_path, hashes=hashes)
    plan1 = plan_fn(wf, registry, states)
    assert plan1.runnable == ["a"]  # "b" isn't ready yet: "a" hasn't run
    cmd_map = {
        "a": write_ok_worker(tmp_path, "auth_a", "a.bin"),
        "b": write_ok_worker(tmp_path, "auth_b", "b.bin"),
    }
    job_ids = enqueue(tmp_path, wf, registry, hashes, plan1,
                       cmd_for=lambda nid: cmd_map[nid], authorization=persisted)
    assert job_ids  # "a" enqueued, named by the persisted authorisation

    # A fresh Executor, as if this were a brand new process: no `authorization=` passed.
    ex = Executor(project_root=tmp_path, workflow=wf, registry=registry, cmd_for=lambda nid: cmd_map[nid])
    ex.run_once()  # runs "a", which should auto-continue "b" via the persisted authorisation

    with db_mod.open_db(tmp_path) as con:
        states_by_node = {r["node_id"]: r["state"] for r in con.execute("SELECT node_id, state FROM job")}
    assert states_by_node.get("a") == "ok"
    assert "b" in states_by_node  # auto-enqueued, not left waiting on a fresh authorisation

    ex.run_once()
    with db_mod.open_db(tmp_path) as con:
        states_by_node = {r["node_id"]: r["state"] for r in con.execute("SELECT node_id, state FROM job")}
    assert states_by_node["b"] == "ok"
