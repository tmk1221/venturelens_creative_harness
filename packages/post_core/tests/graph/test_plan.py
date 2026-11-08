"""plan(): ordering, cost totals, spend flags, targets/from_node scoping."""
from __future__ import annotations

from post_core.graph.plan import plan
from post_core.graph.state import NodeState
from post_core.graph.workflow import Edge, Node, Workflow


def three_stage_workflow() -> Workflow:
    nodes = [
        Node(id="prompt1", type_id="text.prompt", params={"text": "a cat"}),
        Node(id="gen1", type_id="fake.generate", params={"prompt": "a cat"}),
        Node(id="xform1", type_id="fake.transform", params={}),
    ]
    edges = [
        Edge(id="e1", from_node="prompt1", from_output="text", to_node="gen1", to_input="prompt"),
        Edge(id="e2", from_node="gen1", from_output="video", to_node="xform1", to_input="video"),
    ]
    return Workflow(recipe_id="r1", nodes=nodes, edges=edges)


def test_runnable_ordering_and_spend_flags(registry):
    wf = three_stage_workflow()
    states = {"prompt1": NodeState.READY, "gen1": NodeState.BLOCKED, "xform1": NodeState.UNRESOLVED}
    result = plan(wf, registry, states)
    assert result.runnable == ["prompt1"]
    assert result.needs_authorization == []  # text.prompt doesn't spend

    states2 = {"prompt1": NodeState.DONE, "gen1": NodeState.READY, "xform1": NodeState.BLOCKED}
    result2 = plan(wf, registry, states2)
    assert result2.runnable == ["gen1"]
    assert result2.needs_authorization == ["gen1"]  # fake.generate spends
    assert len(result2.estimated_cost) == 1
    assert result2.estimated_cost[0].amount == 1.5
    assert result2.estimated_cost[0].unit == "usd"
    assert result2.estimated_cost[0].provider == "fake-provider"


def test_cost_totals_sum_across_multiple_runnable_spending_nodes(registry):
    nodes = [
        Node(id="prompt1", type_id="text.prompt", params={"text": "a"}),
        Node(id="prompt2", type_id="text.prompt", params={"text": "b"}),
        Node(id="gen1", type_id="fake.generate", params={"prompt": "a"}),
        Node(id="gen2", type_id="fake.generate", params={"prompt": "b"}),
    ]
    edges = [
        Edge(id="e1", from_node="prompt1", from_output="text", to_node="gen1", to_input="prompt"),
        Edge(id="e2", from_node="prompt2", from_output="text", to_node="gen2", to_input="prompt"),
    ]
    wf = Workflow(recipe_id="r1", nodes=nodes, edges=edges)
    states = {
        "prompt1": NodeState.DONE, "prompt2": NodeState.DONE,
        "gen1": NodeState.READY, "gen2": NodeState.READY,
    }
    result = plan(wf, registry, states)
    assert set(result.runnable) == {"gen1", "gen2"}
    assert len(result.estimated_cost) == 1
    assert result.estimated_cost[0].amount == 3.0


def test_blocked_on_human(registry):
    nodes = [
        Node(id="p1", type_id="text.prompt", params={"text": "one"}),
        Node(id="pick1", type_id="human.pick", params={}),
    ]
    edges = [Edge(id="e1", from_node="p1", from_output="text", to_node="pick1", to_input="options")]
    wf = Workflow(recipe_id="r1", nodes=nodes, edges=edges)
    states = {"p1": NodeState.DONE, "pick1": NodeState.NEEDS_PICK}
    result = plan(wf, registry, states)
    assert result.blocked_on_human == ["pick1"]


def test_targets_restrict_to_ancestors(registry):
    wf = three_stage_workflow()
    states = {"prompt1": NodeState.READY, "gen1": NodeState.BLOCKED, "xform1": NodeState.UNRESOLVED}
    # Targeting gen1 pulls in prompt1 (its ancestor) but not xform1 (a descendant, irrelevant).
    result = plan(wf, registry, states, targets=["gen1"])
    assert result.runnable == ["prompt1"]


def test_from_node_restricts_to_descendants(registry):
    wf = three_stage_workflow()
    states = {"prompt1": NodeState.READY, "gen1": NodeState.READY, "xform1": NodeState.READY}
    result = plan(wf, registry, states, from_node="gen1")
    assert result.runnable == ["gen1", "xform1"]
    assert "prompt1" not in result.runnable
