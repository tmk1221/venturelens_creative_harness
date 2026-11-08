"""State derivation from disk artifacts: ready/done/stale/blocked/needs_pick/needs_approval/failed."""
from __future__ import annotations

from pathlib import Path

from post_core.graph import approvals
from post_core.graph.hashing import compute_hashes
from post_core.graph.state import NodeState, artifact_dir, compute_states, read_history, record_history_entry
from post_core.graph.workflow import Edge, Node, Workflow


def two_node_workflow() -> Workflow:
    nodes = [
        Node(id="prompt1", type_id="text.prompt", params={"text": "a cat"}),
        Node(id="gen1", type_id="fake.generate", params={"prompt": "a cat"}),
    ]
    edges = [Edge(id="e1", from_node="prompt1", from_output="text", to_node="gen1", to_input="prompt")]
    return Workflow(recipe_id="r1", nodes=nodes, edges=edges)


def test_source_node_with_no_manifest_is_ready(tmp_path: Path, registry):
    wf = two_node_workflow()
    states = compute_states(wf, registry, tmp_path)
    assert states["prompt1"] == NodeState.READY
    assert states["gen1"] == NodeState.BLOCKED  # upstream (prompt1) not done yet


def test_done_upstream_unblocks_downstream(tmp_path: Path, registry, write_manifest):
    wf = two_node_workflow()
    hashes = compute_hashes(wf, registry)
    write_manifest(tmp_path, "text.prompt", hashes["prompt1"])
    states = compute_states(wf, registry, tmp_path)
    assert states["prompt1"] == NodeState.DONE
    assert states["gen1"] == NodeState.READY


def test_manifest_present_and_check_passes_is_done(tmp_path: Path, registry, write_manifest):
    wf = two_node_workflow()
    hashes = compute_hashes(wf, registry)
    write_manifest(tmp_path, "text.prompt", hashes["prompt1"])
    write_manifest(tmp_path, "fake.generate", hashes["gen1"])
    states = compute_states(wf, registry, tmp_path)
    assert states["gen1"] == NodeState.DONE


def test_param_change_makes_node_stale_and_old_output_still_listed(tmp_path: Path, registry, write_manifest):
    wf_before = two_node_workflow()
    hashes_before = compute_hashes(wf_before, registry)
    write_manifest(tmp_path, "text.prompt", hashes_before["prompt1"])
    write_manifest(tmp_path, "fake.generate", hashes_before["gen1"])
    # record_history=True here stands in for what the executor now does itself when it
    # writes a manifest (T05 carry-over #1) -- compute_states is pure by default.
    states_before = compute_states(wf_before, registry, tmp_path, record_history=True)
    assert states_before["gen1"] == NodeState.DONE

    nodes_after = [n.model_copy() for n in wf_before.nodes]
    nodes_after[1] = nodes_after[1].model_copy(update={"params": {"prompt": "a dog"}})
    wf_after = Workflow(recipe_id="r1", nodes=nodes_after, edges=wf_before.edges)
    hashes_after = compute_hashes(wf_after, registry)
    assert hashes_after["gen1"] != hashes_before["gen1"]

    states_after = compute_states(wf_after, registry, tmp_path)
    assert states_after["gen1"] == NodeState.STALE

    # the old output is still on disk, listed under the old hash.
    old_dir = artifact_dir(tmp_path, "fake.generate", hashes_before["gen1"])
    assert (old_dir / "manifest.json").is_file()


def test_failed_marker_reports_failed(tmp_path: Path, registry, write_manifest):
    wf = two_node_workflow()
    hashes = compute_hashes(wf, registry)
    write_manifest(tmp_path, "text.prompt", hashes["prompt1"])
    gen_dir = artifact_dir(tmp_path, "fake.generate", hashes["gen1"])
    gen_dir.mkdir(parents=True, exist_ok=True)
    (gen_dir / "failed.json").write_text("{}")
    states = compute_states(wf, registry, tmp_path)
    assert states["gen1"] == NodeState.FAILED


def test_compute_states_is_pure_by_default(tmp_path: Path, registry, write_manifest):
    """T05 carry-over #1: reading state never writes the per-node hash history."""
    wf = two_node_workflow()
    hashes = compute_hashes(wf, registry)
    write_manifest(tmp_path, "text.prompt", hashes["prompt1"])
    compute_states(wf, registry, tmp_path)  # default: record_history=False
    assert read_history(tmp_path, "prompt1") == []

    record_history_entry(tmp_path, "prompt1", hashes["prompt1"])
    assert read_history(tmp_path, "prompt1") == [hashes["prompt1"]]


def test_unmade_pick_needs_pick_downstream_unresolved(tmp_path: Path, registry):
    nodes = [
        Node(id="p1", type_id="text.prompt", params={"text": "one"}),
        Node(id="pick1", type_id="human.pick", params={}),
        Node(id="xform1", type_id="fake.transform", params={}),
    ]
    edges = [
        Edge(id="e1", from_node="p1", from_output="text", to_node="pick1", to_input="options"),
        Edge(id="e2", from_node="pick1", from_output="chosen", to_node="xform1", to_input="video"),
    ]
    wf = Workflow(recipe_id="r1", nodes=nodes, edges=edges)
    states = compute_states(wf, registry, tmp_path)
    assert states["pick1"] == NodeState.NEEDS_PICK
    assert states["xform1"] == NodeState.UNRESOLVED


def test_approve_node_needs_approval_then_done(tmp_path: Path, registry):
    nodes = [
        Node(id="p1", type_id="text.prompt", params={"text": "one"}),
        Node(id="approve1", type_id="human.approve", params={}),
    ]
    edges = [Edge(id="e1", from_node="p1", from_output="text", to_node="approve1", to_input="subject")]
    wf = Workflow(recipe_id="r1", nodes=nodes, edges=edges)
    hashes = compute_hashes(wf, registry)

    states = compute_states(wf, registry, tmp_path)
    assert states["approve1"] == NodeState.NEEDS_APPROVAL

    approvals.approve(tmp_path, hashes["approve1"], by="travis")
    states = compute_states(wf, registry, tmp_path)
    assert states["approve1"] == NodeState.DONE
