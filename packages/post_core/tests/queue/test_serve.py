"""T06 carry-over #1 (`Executor.serve()`: real per-lane concurrency, clean shutdown marks
running jobs interrupted) and carry-over #3 (`NodeType.resources` resource locking, not a
magic lane name)."""
from __future__ import annotations

import threading
import time

from post_core.graph.hashing import compute_hashes
from post_core.graph.plan import plan as plan_fn
from post_core.graph.state import compute_states
from post_core.graph.workflow import Node, Workflow
from post_core.queue import db as db_mod
from post_core.queue.enqueue import enqueue
from post_core.queue.executor import Executor

from worker_scripts import write_sleepy_worker


def _bootstrap(wf, registry, tmp_path, cmd_map):
    hashes = compute_hashes(wf, registry)
    states = compute_states(wf, registry, tmp_path, hashes=hashes)
    plan1 = plan_fn(wf, registry, states)
    return enqueue(tmp_path, wf, registry, hashes, plan1, cmd_for=lambda nid: cmd_map[nid])


def _run_serve_until_drained(ex: Executor, timeout: float = 10.0) -> None:
    stop = threading.Event()
    thread = threading.Thread(target=ex.serve, args=(stop,), kwargs={"poll_interval": 0.02})
    thread.start()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with db_mod.open_db(ex.project_root) as con:
            pending = con.execute(
                "SELECT COUNT(*) c FROM job WHERE state IN ('queued','running','retry_later')"
            ).fetchone()["c"]
        if pending == 0:
            break
        time.sleep(0.02)
    stop.set()
    thread.join(timeout=5)
    assert not thread.is_alive()


def test_serve_runs_lane_jobs_concurrently(tmp_path, registry):
    """Two independent jobs in a lane whose limit allows both at once must actually overlap
    -- `run_once()` runs its picked jobs one after another in the calling thread and could
    never finish two 0.3s jobs in under 0.3s*2; `serve()`'s per-lane thread pool can."""
    nodes = [Node(id="a", type_id="fake.free", params={"text": "a"}),
             Node(id="b", type_id="fake.free", params={"text": "b"})]
    wf = Workflow(recipe_id="r1", nodes=nodes, edges=[])
    marker_a, marker_b = tmp_path / "a.start", tmp_path / "b.start"
    cmd_map = {
        "a": write_sleepy_worker(tmp_path, "slow_a", seconds=0.4, lock_check=marker_a),
        "b": write_sleepy_worker(tmp_path, "slow_b", seconds=0.4, lock_check=marker_b),
    }

    _bootstrap(wf, registry, tmp_path, cmd_map)
    ex = Executor(
        project_root=tmp_path, workflow=wf, registry=registry, cmd_for=lambda nid: cmd_map[nid],
        lanes={"single": 2},
    )
    start = time.monotonic()
    _run_serve_until_drained(ex)
    elapsed = time.monotonic() - start

    with db_mod.open_db(tmp_path) as con:
        states = {r["node_id"]: r["state"] for r in con.execute("SELECT node_id, state FROM job")}
    assert states == {"a": "ok", "b": "ok"}
    # Run serially this would take >=0.8s; concurrently, comfortably under that.
    assert elapsed < 0.75


def test_serve_shutdown_marks_running_job_interrupted(tmp_path, registry):
    node = Node(id="a", type_id="fake.free", params={"text": "a"})
    wf = Workflow(recipe_id="r1", nodes=[node], edges=[])
    marker = tmp_path / "lock_check"
    cmd_map = {"a": write_sleepy_worker(tmp_path, "slow_shutdown", seconds=2.0, lock_check=marker)}
    _bootstrap(wf, registry, tmp_path, cmd_map)

    ex = Executor(project_root=tmp_path, workflow=wf, registry=registry, cmd_for=lambda nid: cmd_map[nid])
    stop = threading.Event()
    thread = threading.Thread(target=ex.serve, args=(stop,), kwargs={"poll_interval": 0.02})
    thread.start()
    # Give the job time to actually start running.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not marker.exists():
        time.sleep(0.02)
    assert marker.exists()

    stop.set()
    thread.join(timeout=10)
    assert not thread.is_alive()

    with db_mod.open_db(tmp_path) as con:
        row = con.execute("SELECT state FROM job WHERE node_id='a'").fetchone()
    assert row["state"] == "interrupted"


def test_serve_serialises_resource_lock_even_across_lane_concurrency(tmp_path, registry):
    """Two "fake.resolve" nodes (lane "render", resources=("resolve",)) run under a lane
    limit that allows both at once -- the resource lock must still keep them from
    overlapping. `write_sleepy_worker`'s script itself raises if it sees a live marker from
    the other run, so any overlap fails the job."""
    nodes = [Node(id="r1", type_id="fake.resolve", params={"text": "r1"}),
             Node(id="r2", type_id="fake.resolve", params={"text": "r2"})]
    wf = Workflow(recipe_id="r1", nodes=nodes, edges=[])
    lock_check = tmp_path / "resolve_marker"
    cmd_map = {
        "r1": write_sleepy_worker(tmp_path, "resolve_1", seconds=0.2, lock_check=lock_check),
        "r2": write_sleepy_worker(tmp_path, "resolve_2", seconds=0.2, lock_check=lock_check),
    }
    _bootstrap(wf, registry, tmp_path, cmd_map)
    ex = Executor(
        project_root=tmp_path, workflow=wf, registry=registry, cmd_for=lambda nid: cmd_map[nid],
        lanes={"render": 4},
    )
    _run_serve_until_drained(ex)

    with db_mod.open_db(tmp_path) as con:
        states = {r["node_id"]: r["state"] for r in con.execute("SELECT node_id, state FROM job")}
    assert states == {"r1": "ok", "r2": "ok"}
