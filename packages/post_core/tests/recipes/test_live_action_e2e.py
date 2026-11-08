"""Acceptance: live_action end to end -- stills -> blocked on pick -> pick -> motion ->
video >= span+1s -> verify -> approve; only fixture-priced spends, nothing paid runs."""
from __future__ import annotations

import math

from post_core.graph import approvals
from post_core.graph.hashing import compute_hashes
from post_core.graph.plan import plan as plan_fn
from post_core.graph.state import NodeState, compute_states
from post_core.recipes.instantiate import SpanSpec, instantiate

from conftest import enqueue_ready, run_to_completion


def test_live_action_end_to_end(project_root, registry, kit):
    span = SpanSpec(id="beat1", seconds=3.4, variants=3)
    workflow = instantiate("live_action", span, kit, None, project_root)

    executor = run_to_completion(project_root, workflow, registry)

    hashes = compute_hashes(workflow, registry)
    states = compute_states(workflow, registry, project_root, hashes=hashes)
    for v in range(3):
        assert states[f"beat1-still{v}"] == NodeState.DONE
    assert states["beat1-pick"] == NodeState.NEEDS_PICK

    plan = plan_fn(workflow, registry, states)
    assert "beat1-pick" in plan.blocked_on_human

    # Make the pick: choose the first still variant.
    pick_node = workflow.node("beat1-pick")
    chosen_edge = next(e for e in workflow.edges_into("beat1-pick", "options") if e.from_node == "beat1-still0")
    pick_node.selected = chosen_edge.id

    from post_core.recipes import cmd_for as cmd_for_mod

    cmd_for = cmd_for_mod.make_cmd_for(workflow, registry, project_root)
    enqueue_ready(project_root, workflow, registry, cmd_for, executor.authorization)
    for _ in range(25):
        if not executor.run_once():
            break

    hashes = compute_hashes(workflow, registry)
    states = compute_states(workflow, registry, project_root, hashes=hashes)
    assert states["beat1-motion"] == NodeState.DONE
    assert states["beat1-video"] == NodeState.DONE
    assert states["beat1-verify"] == NodeState.DONE
    assert states["beat1-approve"] == NodeState.NEEDS_APPROVAL

    plan = plan_fn(workflow, registry, states)
    assert "beat1-approve" in plan.blocked_on_human

    from post_core.export._context import asset_done_and_approved, find_asset_for_node

    approve_hash = hashes["beat1-approve"]
    asset = find_asset_for_node(project_root, "beat1-approve")
    assert asset is not None
    assert asset.content_hash == approve_hash
    assert asset.fps is not None
    min_seconds = math.ceil(span.seconds) + 1
    assert asset.duration_frames / asset.fps.as_float() >= min_seconds - 0.5
    assert not asset_done_and_approved(project_root, asset)  # not approved yet

    approvals.approve(project_root, approve_hash, by="test")
    asset = find_asset_for_node(project_root, "beat1-approve")
    assert asset_done_and_approved(project_root, asset)
