"""Executor: picking, running, and recording the outcome of real (subprocess) fake workers."""
from __future__ import annotations

import json
import time

from post_core.graph.hashing import compute_hashes
from post_core.graph.state import NodeState, compute_states, read_manifest
from post_core.graph.state import artifact_dir as artifact_dir_fn
from post_core.graph.plan import plan as plan_fn
from post_core.graph.workflow import Edge, Node, Workflow
from post_core.queue import db as db_mod
from post_core.queue.budget import set_budget
from post_core.queue.enqueue import Authorization
from post_core.queue.executor import Executor

from worker_scripts import (
    write_failing_worker,
    write_manifest,
    write_ok_worker,
    write_retry_then_succeed_worker,
)


def chain_workflow() -> Workflow:
    """src (source, not a job) -> a (fake.free, lane single) -> b (fake.free, lane single)."""
    nodes = [
        Node(id="src", type_id="source.file", params={"path": "/x.mp4"}),
        Node(id="a", type_id="fake.free", params={"text": "a"}),
        Node(id="b", type_id="fake.free", params={"text": "b"}),
    ]
    edges = [
        Edge(id="e1", from_node="src", from_output="file", to_node="a", to_input="video"),
        Edge(id="e2", from_node="a", from_output="video", to_node="b", to_input="video"),
    ]
    return Workflow(recipe_id="r1", nodes=nodes, edges=edges)


def _seed_ready(wf, registry, tmp_path):
    hashes = compute_hashes(wf, registry)
    write_manifest(tmp_path, "source.file", hashes["src"])
    return compute_hashes(wf, registry)


def _bootstrap(wf, registry, tmp_path, cmd_map):
    """enqueue() every currently-runnable compute node using cmd_map[node_id]."""
    hashes = _seed_ready(wf, registry, tmp_path)
    states = compute_states(wf, registry, tmp_path, hashes=hashes)
    plan1 = plan_fn(wf, registry, states)
    from post_core.queue.enqueue import enqueue

    return enqueue(tmp_path, wf, registry, hashes, plan1, cmd_for=lambda nid: cmd_map[nid])


def test_dependency_order_and_events_persisted_in_order(tmp_path, registry):
    wf = chain_workflow()
    cmd_map = {
        "a": write_ok_worker(tmp_path, "worker_a", out_name="a.bin"),
        "b": write_ok_worker(tmp_path, "worker_b", out_name="b.bin"),
    }
    job_ids = _bootstrap(wf, registry, tmp_path, cmd_map)
    assert len(job_ids) == 1  # "b" isn't runnable yet: "a" isn't done

    ex = Executor(project_root=tmp_path, workflow=wf, registry=registry, cmd_for=lambda nid: cmd_map[nid])
    ran1 = ex.run_once()
    assert ran1 == job_ids

    with db_mod.open_db(tmp_path) as con:
        job_a = con.execute("SELECT * FROM job WHERE id=?", (job_ids[0],)).fetchone()
        assert job_a["state"] == "ok"
        events = con.execute(
            "SELECT kind FROM event WHERE job_id=? ORDER BY seq", (job_ids[0],)
        ).fetchall()
    assert [e["kind"] for e in events] == ["cost", "artifact", "result"]

    # "a"'s manifest exists and "b" was auto-enqueued now that "a" is done.
    hashes = compute_hashes(wf, registry)
    a_dir = artifact_dir_fn(tmp_path, "fake.free", hashes["a"])
    assert read_manifest(a_dir) is not None

    with db_mod.open_db(tmp_path) as con:
        pending_b = con.execute("SELECT * FROM job WHERE node_id='b'").fetchone()
    assert pending_b is not None
    assert pending_b["state"] == "queued"

    ran2 = ex.run_once()
    assert ran2 == [pending_b["id"]]
    with db_mod.open_db(tmp_path) as con:
        job_b = con.execute("SELECT state FROM job WHERE id=?", (pending_b["id"],)).fetchone()
    assert job_b["state"] == "ok"


def test_lane_limit_honoured(tmp_path, registry):
    """fake.free is lane "single" (concurrency 1): two independent, already-ready jobs must
    not both be picked by one run_once() call."""
    nodes = [
        Node(id="src", type_id="source.file", params={"path": "/x.mp4"}),
        Node(id="a", type_id="fake.free", params={"text": "a"}),
        Node(id="c", type_id="fake.free", params={"text": "c"}),
    ]
    edges = [
        Edge(id="e1", from_node="src", from_output="file", to_node="a", to_input="video"),
        Edge(id="e2", from_node="src", from_output="file", to_node="c", to_input="video"),
    ]
    wf = Workflow(recipe_id="r1", nodes=nodes, edges=edges)
    cmd_map = {
        "a": write_ok_worker(tmp_path, "worker_a2", out_name="a2.bin"),
        "c": write_ok_worker(tmp_path, "worker_c2", out_name="c2.bin"),
    }
    job_ids = _bootstrap(wf, registry, tmp_path, cmd_map)
    assert len(job_ids) == 2  # both ready: "a" and "c" both only depend on "src"

    ex = Executor(project_root=tmp_path, workflow=wf, registry=registry, cmd_for=lambda nid: cmd_map[nid])
    ran1 = ex.run_once()
    assert len(ran1) == 1  # lane "single" only ever admits 1 per call

    with db_mod.open_db(tmp_path) as con:
        states = {
            r["node_id"]: r["state"]
            for r in con.execute("SELECT node_id, state FROM job").fetchall()
        }
    assert list(states.values()).count("ok") == 1
    assert list(states.values()).count("queued") == 1

    ran2 = ex.run_once()
    assert len(ran2) == 1
    with db_mod.open_db(tmp_path) as con:
        oks = con.execute("SELECT COUNT(*) c FROM job WHERE state='ok'").fetchone()["c"]
    assert oks == 2


def test_restart_mid_run_recovers_and_requeues_if_still_ready(tmp_path, registry):
    wf = chain_workflow()
    cmd_map = {
        "a": write_ok_worker(tmp_path, "worker_a3", out_name="a3.bin"),
        "b": write_ok_worker(tmp_path, "worker_b3", out_name="b3.bin"),
    }
    hashes = _seed_ready(wf, registry, tmp_path)
    states = compute_states(wf, registry, tmp_path, hashes=hashes)
    plan1 = plan_fn(wf, registry, states)
    from post_core.queue.enqueue import enqueue

    job_ids = enqueue(tmp_path, wf, registry, hashes, plan1, cmd_for=lambda nid: cmd_map[nid])
    job_id = job_ids[0]

    # Simulate the process dying mid-run: state was set to "running" and never finished.
    with db_mod.open_db(tmp_path) as con:
        con.execute("UPDATE job SET state='running', started_at=? WHERE id=?", (time.time(), job_id))
        con.commit()

    ex = Executor(project_root=tmp_path, workflow=wf, registry=registry, cmd_for=lambda nid: cmd_map[nid])
    ex.recover_interrupted()

    with db_mod.open_db(tmp_path) as con:
        old = con.execute("SELECT state FROM job WHERE id=?", (job_id,)).fetchone()
        assert old["state"] == "interrupted"
        requeued = con.execute(
            "SELECT * FROM job WHERE node_id='a' AND state='queued'"
        ).fetchall()
    assert len(requeued) == 1  # node "a" was still ready, so it got a fresh job

    ran = ex.run_once()
    assert ran == [requeued[0]["id"]]
    with db_mod.open_db(tmp_path) as con:
        row = con.execute("SELECT state FROM job WHERE id=?", (requeued[0]["id"],)).fetchone()
    assert row["state"] == "ok"


def test_retry_later_holds_lane_then_resumes(tmp_path, registry):
    wf = chain_workflow()
    marker = tmp_path / "retry_marker"
    cmd_map = {
        "a": write_retry_then_succeed_worker(tmp_path, "worker_retry", marker, retry_at=""),
        "b": write_ok_worker(tmp_path, "worker_retry_b", out_name="rb.bin"),
    }
    job_ids = _bootstrap(wf, registry, tmp_path, cmd_map)
    job_id = job_ids[0]

    clock = {"t": 1_000_000.0}
    ex = Executor(
        project_root=tmp_path, workflow=wf, registry=registry, cmd_for=lambda nid: cmd_map[nid],
        now=lambda: clock["t"],
    )
    ran1 = ex.run_once()
    assert ran1 == [job_id]
    with db_mod.open_db(tmp_path) as con:
        row = con.execute("SELECT state, not_before FROM job WHERE id=?", (job_id,)).fetchone()
    assert row["state"] == "retry_later"
    assert row["not_before"] > clock["t"]

    # Before not_before: the lane holds, nothing runs.
    ran_early = ex.run_once()
    assert ran_early == []

    # Advance time past not_before: the lane resumes and the (now-succeeding) worker runs.
    clock["t"] = row["not_before"] + 1
    ran2 = ex.run_once()
    assert ran2 == [job_id]
    with db_mod.open_db(tmp_path) as con:
        row2 = con.execute("SELECT state FROM job WHERE id=?", (job_id,)).fetchone()
    assert row2["state"] == "ok"


def test_failed_job_leaves_node_failed_and_blocks_downstream(tmp_path, registry):
    wf = chain_workflow()
    cmd_map = {"a": write_failing_worker(tmp_path, "worker_fail")}
    job_ids = _bootstrap(wf, registry, tmp_path, cmd_map)

    ex = Executor(project_root=tmp_path, workflow=wf, registry=registry, cmd_for=lambda nid: cmd_map[nid])
    ex.run_once()

    with db_mod.open_db(tmp_path) as con:
        row = con.execute("SELECT state, summary FROM job WHERE id=?", (job_ids[0],)).fetchone()
    assert row["state"] == "failed"
    assert row["summary"]

    hashes = compute_hashes(wf, registry)
    states = compute_states(wf, registry, tmp_path, hashes=hashes)
    assert states["a"] == NodeState.FAILED
    assert states["b"] == NodeState.BLOCKED

    with db_mod.open_db(tmp_path) as con:
        b_jobs = con.execute("SELECT * FROM job WHERE node_id='b'").fetchall()
    assert b_jobs == []  # never auto-enqueued behind a failed upstream


def test_budget_cap_stops_further_spend(tmp_path, registry):
    """T31: enqueue now refuses estimates past the headroom up front, so this exercises the
    other guard: a job whose *actual* cost overruns its estimate (1.5 shown, 3.5 charged)
    pushes spent past the cap and holds the rest of the budget's queued jobs."""
    nodes = [
        Node(id="g1", type_id="fake.spend_single", params={"text": "1"}),
        Node(id="g2", type_id="fake.spend_single", params={"text": "2"}),
    ]
    wf = Workflow(recipe_id="r1", nodes=nodes, edges=[])
    cmd_map = {
        "g1": write_ok_worker(tmp_path, "worker_spend1", out_name="s1.bin", cost=3.5),
        "g2": write_ok_worker(tmp_path, "worker_spend2", out_name="s2.bin", cost=3.5),
    }
    set_budget(tmp_path, "b1", cap=3.0, unit="usd")
    auth = Authorization(budget_id="b1", by="travis")

    hashes = compute_hashes(wf, registry)
    states = compute_states(wf, registry, tmp_path, hashes=hashes)
    plan1 = plan_fn(wf, registry, states)
    assert sorted(plan1.runnable) == ["g1", "g2"]

    from post_core.queue.enqueue import enqueue

    job_ids = enqueue(tmp_path, wf, registry, hashes, plan1, cmd_for=lambda nid: cmd_map[nid], authorization=auth)
    assert len(job_ids) == 2

    ex = Executor(
        project_root=tmp_path, workflow=wf, registry=registry, cmd_for=lambda nid: cmd_map[nid],
        authorization=auth,
    )
    ex.run_once()  # lane "single": only the first (created_at order) runs

    with db_mod.open_db(tmp_path) as con:
        rows = {r["node_id"]: dict(r) for r in con.execute("SELECT * FROM job").fetchall()}
        budget = con.execute("SELECT cap, spent FROM budget WHERE id='b1'").fetchone()

    assert budget["spent"] >= budget["cap"]  # the one job's 3.5 cost pushed it over the 3.0 cap
    ran_node = [nid for nid, r in rows.items() if r["state"] == "ok"][0]
    other_node = "g2" if ran_node == "g1" else "g1"
    assert rows[other_node]["state"] == "needs_human"

    # And it stays put: another run_once() does not pick it up.
    ran_again = ex.run_once()
    assert ran_again == []


def test_jobs_are_scoped_to_their_own_workflow_when_sharing_a_project(tmp_path, registry):
    """T30d regression: `post_api/runtime.py`'s background drain loop builds one fresh
    `Executor` per workflow_id currently on disk, all against the same project root -- so
    the same `queue.db` (and therefore its `job` table) is shared by every workflow in a
    project, not just one at a time (e.g. a project with two beats both mid-plan). Before
    this fix, `_pick_jobs`'s SELECT had no `workflow_id` filter at all: an `Executor` built
    for workflow A could claim a `queued` job that actually belongs to workflow B, and
    `self.workflow.node(job["node_id"])` (`_node_resources`/`_finish_job`) then raised a bare
    `KeyError` -- an uncaught exception that kills the whole background thread for the rest
    of that project's session (`post_api/runtime.py::_loop` has no try/except around
    `_drain`)."""
    wf_a = Workflow(recipe_id="r1", nodes=[Node(id="a", type_id="fake.free", params={"text": "a"})], edges=[])
    wf_b = Workflow(recipe_id="r1", nodes=[Node(id="b", type_id="fake.free", params={"text": "b"})], edges=[])
    cmd_map = {
        "a": write_ok_worker(tmp_path, "worker_a", out_name="a.bin"),
        "b": write_ok_worker(tmp_path, "worker_b", out_name="b.bin"),
    }
    from post_core.queue.enqueue import enqueue

    hashes_a = compute_hashes(wf_a, registry)
    states_a = compute_states(wf_a, registry, tmp_path, hashes=hashes_a)
    plan_a = plan_fn(wf_a, registry, states_a)
    job_ids_a = enqueue(tmp_path, wf_a, registry, hashes_a, plan_a, cmd_for=lambda nid: cmd_map[nid])

    hashes_b = compute_hashes(wf_b, registry)
    states_b = compute_states(wf_b, registry, tmp_path, hashes=hashes_b)
    plan_b = plan_fn(wf_b, registry, states_b)
    job_ids_b = enqueue(tmp_path, wf_b, registry, hashes_b, plan_b, cmd_for=lambda nid: cmd_map[nid])
    assert len(job_ids_a) == 1 and len(job_ids_b) == 1

    # Same project_root (tmp_path) -> same queue.db -- exactly the shared-queue shape
    # `runtime.py` builds, one Executor per workflow.
    ex_a = Executor(project_root=tmp_path, workflow=wf_a, registry=registry, cmd_for=lambda nid: cmd_map[nid])
    ex_b = Executor(project_root=tmp_path, workflow=wf_b, registry=registry, cmd_for=lambda nid: cmd_map[nid])

    # Drain B *first*: "a" was enqueued before "b" (earlier `created_at`), so the buggy,
    # unscoped `_pick_jobs` query (`ORDER BY created_at LIMIT ?`, no `workflow_id` filter)
    # would hand B's Executor "a"'s job regardless of which Executor asks first -- draining A
    # first would "accidentally" pick the right job even with the bug, since A's own job
    # happens to be the earliest-created one. Draining B first is the one order that actually
    # exercises the bug.
    ran_b = ex_b.run_once()
    assert ran_b == job_ids_b
    ran_a = ex_a.run_once()
    assert ran_a == job_ids_a

    with db_mod.open_db(tmp_path) as con:
        job_a = con.execute("SELECT state FROM job WHERE id=?", (job_ids_a[0],)).fetchone()
        job_b = con.execute("SELECT state FROM job WHERE id=?", (job_ids_b[0],)).fetchone()
    assert job_a["state"] == "ok"
    assert job_b["state"] == "ok"


def test_default_lane_is_scheduled_two_at_a_time(tmp_path, registry):
    """T18 item 4: a node type left at `NodeType.lane`'s default ("default") used to sit
    `queued` forever (no executor lane). It now runs, at most 2 per `run_once()`."""
    from dataclasses import replace

    registry.register(replace(registry.get("fake.free"), id="fake.default_lane", lane="default"))
    ids = ("a", "c", "d")
    nodes = [Node(id="src", type_id="source.file", params={"path": "/x.mp4"})]
    nodes += [Node(id=i, type_id="fake.default_lane", params={"text": i}) for i in ids]
    edges = [Edge(id=f"e{i}", from_node="src", from_output="file", to_node=i, to_input="video") for i in ids]
    wf = Workflow(recipe_id="r1", nodes=nodes, edges=edges)
    cmd_map = {i: write_ok_worker(tmp_path, f"worker_dl_{i}", out_name=f"dl_{i}.bin") for i in ids}
    assert len(_bootstrap(wf, registry, tmp_path, cmd_map)) == 3

    ex = Executor(project_root=tmp_path, workflow=wf, registry=registry, cmd_for=lambda nid: cmd_map[nid])
    assert len(ex.run_once()) == 2
    assert len(ex.run_once()) == 1
    with db_mod.open_db(tmp_path) as con:
        assert con.execute("SELECT COUNT(*) c FROM job WHERE state='ok'").fetchone()["c"] == 3
