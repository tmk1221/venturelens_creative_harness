"""enqueue(): spend authorisation gating and idempotency on (node_id, input_hash)."""
from __future__ import annotations

import json

from post_core.graph.hashing import compute_hashes
from post_core.graph.plan import plan as plan_fn
from post_core.graph.state import compute_states
from post_core.graph.workflow import Edge, Node, Workflow
from post_core.queue import db as db_mod
from post_core.queue.budget import set_budget
from post_core.queue.enqueue import Authorization, SpendNotAuthorized, enqueue


def free_workflow() -> Workflow:
    nodes = [
        Node(id="src", type_id="source.file", params={"path": "/x.mp4"}),
        Node(id="gen", type_id="fake.free", params={"text": "a"}),
    ]
    edges = [Edge(id="e1", from_node="src", from_output="file", to_node="gen", to_input="video")]
    return Workflow(recipe_id="r1", nodes=nodes, edges=edges)


def spend_workflow() -> Workflow:
    nodes = [Node(id="gen", type_id="fake.spend", params={"text": "a"})]
    return Workflow(recipe_id="r1", nodes=nodes, edges=[])


def _ready_plan(wf, registry, project_root):
    hashes = compute_hashes(wf, registry)
    states = compute_states(wf, registry, project_root, hashes=hashes)
    return hashes, plan_fn(wf, registry, states)


def _write_source_manifest(tmp_path, hashes):
    from post_core.graph.state import artifact_dir

    d = artifact_dir(tmp_path, "source.file", hashes["src"])
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps({"outputs": [], "finished_at": 0.0}))


def test_enqueue_creates_a_queued_job_for_a_compute_node(tmp_path, registry):
    wf = free_workflow()
    hashes, plan1 = _ready_plan(wf, registry, tmp_path)
    _write_source_manifest(tmp_path, hashes)
    hashes, plan1 = _ready_plan(wf, registry, tmp_path)
    assert plan1.runnable == ["gen"]

    job_ids = enqueue(tmp_path, wf, registry, hashes, plan1, cmd_for=lambda nid: ["echo", nid])
    assert len(job_ids) == 1

    with db_mod.open_db(tmp_path) as con:
        row = con.execute("SELECT * FROM job WHERE id=?", (job_ids[0],)).fetchone()
    assert row["node_id"] == "gen"
    assert row["state"] == "queued"
    assert row["lane"] == "single"
    assert json.loads(row["cmd_json"]) == ["echo", "gen"]


def test_enqueue_skips_source_nodes(tmp_path, registry):
    wf = free_workflow()
    hashes = compute_hashes(wf, registry)
    _write_source_manifest(tmp_path, hashes)
    hashes, plan1 = _ready_plan(wf, registry, tmp_path)
    # "src" is already DONE (manifest written), so it wouldn't be runnable anyway; force it
    # into the plan directly to prove enqueue() itself also skips non-compute kinds.
    from post_core.graph.plan import Plan

    forced = Plan(runnable=["src"], needs_authorization=[], blocked_on_human=[], estimated_cost=[])
    job_ids = enqueue(tmp_path, wf, registry, hashes, forced, cmd_for=lambda nid: ["echo"])
    assert job_ids == []


def test_enqueue_idempotent_while_job_is_live(tmp_path, registry):
    wf = free_workflow()
    hashes = compute_hashes(wf, registry)
    _write_source_manifest(tmp_path, hashes)
    hashes, plan1 = _ready_plan(wf, registry, tmp_path)

    ids1 = enqueue(tmp_path, wf, registry, hashes, plan1, cmd_for=lambda nid: ["echo", nid])
    ids2 = enqueue(tmp_path, wf, registry, hashes, plan1, cmd_for=lambda nid: ["echo", nid])
    assert ids1 == ids2

    with db_mod.open_db(tmp_path) as con:
        n = con.execute("SELECT COUNT(*) c FROM job WHERE node_id='gen'").fetchone()["c"]
    assert n == 1


def test_spend_refused_without_authorization(tmp_path, registry):
    wf = spend_workflow()
    hashes, plan1 = _ready_plan(wf, registry, tmp_path)
    assert plan1.runnable == ["gen"]
    try:
        enqueue(tmp_path, wf, registry, hashes, plan1, cmd_for=lambda nid: ["echo"])
        assert False, "expected SpendNotAuthorized"
    except SpendNotAuthorized:
        pass


def test_spend_refused_when_budget_has_no_headroom(tmp_path, registry):
    wf = spend_workflow()
    hashes, plan1 = _ready_plan(wf, registry, tmp_path)
    set_budget(tmp_path, "b1", cap=1.0, unit="usd")
    with db_mod.open_db(tmp_path) as con:
        con.execute("UPDATE budget SET spent=1.0 WHERE id='b1'")
        con.commit()
    auth = Authorization(budget_id="b1", by="travis")
    try:
        enqueue(tmp_path, wf, registry, hashes, plan1, cmd_for=lambda nid: ["echo"], authorization=auth)
        assert False, "expected SpendNotAuthorized"
    except SpendNotAuthorized:
        pass


def test_spend_allowed_with_authorization_and_headroom(tmp_path, registry):
    wf = spend_workflow()
    hashes, plan1 = _ready_plan(wf, registry, tmp_path)
    set_budget(tmp_path, "b1", cap=10.0, unit="usd")
    auth = Authorization(budget_id="b1", by="travis")
    job_ids = enqueue(tmp_path, wf, registry, hashes, plan1, cmd_for=lambda nid: ["echo"], authorization=auth)
    assert len(job_ids) == 1
    with db_mod.open_db(tmp_path) as con:
        row = con.execute("SELECT authorised_by, budget_id FROM job WHERE id=?", (job_ids[0],)).fetchone()
    assert row["authorised_by"] == "travis"
    assert row["budget_id"] == "b1"


def test_authorization_scoped_to_named_node_ids_does_not_cover_others(tmp_path, registry):
    auth = Authorization(budget_id="b1", by="travis", node_ids=frozenset({"other"}))
    assert auth.covers("other") is True
    assert auth.covers("gen") is False
