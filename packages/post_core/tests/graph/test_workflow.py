"""Edge validation: type matches, required inputs wired, `many` respected, no cycles."""
from __future__ import annotations

from post_core.graph.workflow import Edge, GraphCycleError, Node, Workflow, topo_order, validate


def make_simple_workflow(**overrides) -> Workflow:
    nodes = [
        Node(id="prompt1", type_id="text.prompt", params={"text": "a cat"}),
        Node(id="gen1", type_id="fake.generate", params={"prompt": "a cat"}),
    ]
    edges = [
        Edge(id="e1", from_node="prompt1", from_output="text", to_node="gen1", to_input="prompt"),
    ]
    defaults = dict(recipe_id="r1", nodes=nodes, edges=edges)
    defaults.update(overrides)
    return Workflow(**defaults)


def test_valid_workflow_has_no_issues(registry):
    wf = make_simple_workflow()
    assert validate(wf, registry) == []


def test_unknown_node_type_reported(registry):
    wf = Workflow(recipe_id="r1", nodes=[Node(id="n1", type_id="nope.type")], edges=[])
    issues = validate(wf, registry)
    assert any("unknown node type" in i for i in issues)


def test_type_mismatch_reported(registry):
    # source.file outputs "video", but gen1's "prompt" input wants "prompt".
    nodes = [
        Node(id="file1", type_id="source.file", params={"path": "/x.mp4"}),
        Node(id="gen1", type_id="fake.generate", params={}),
    ]
    edges = [Edge(id="e1", from_node="file1", from_output="file", to_node="gen1", to_input="prompt")]
    wf = Workflow(recipe_id="r1", nodes=nodes, edges=edges)
    issues = validate(wf, registry)
    assert any("type mismatch" in i for i in issues)


def test_required_input_not_wired_reported(registry):
    wf = Workflow(
        recipe_id="r1",
        nodes=[Node(id="gen1", type_id="fake.generate", params={})],
        edges=[],
    )
    issues = validate(wf, registry)
    assert any("required input" in i for i in issues)


def test_many_false_rejects_multiple_edges(registry):
    nodes = [
        Node(id="p1", type_id="text.prompt", params={"text": "one"}),
        Node(id="p2", type_id="text.prompt", params={"text": "two"}),
        Node(id="gen1", type_id="fake.generate", params={}),
    ]
    edges = [
        Edge(id="e1", from_node="p1", from_output="text", to_node="gen1", to_input="prompt"),
        Edge(id="e2", from_node="p2", from_output="text", to_node="gen1", to_input="prompt"),
    ]
    wf = Workflow(recipe_id="r1", nodes=nodes, edges=edges)
    issues = validate(wf, registry)
    assert any("does not accept many" in i for i in issues)


def test_pick_many_true_allows_multiple_edges(registry):
    nodes = [
        Node(id="p1", type_id="text.prompt", params={"text": "one"}),
        Node(id="p2", type_id="text.prompt", params={"text": "two"}),
        Node(id="pick1", type_id="human.pick", params={}),
    ]
    edges = [
        Edge(id="e1", from_node="p1", from_output="text", to_node="pick1", to_input="options"),
        Edge(id="e2", from_node="p2", from_output="text", to_node="pick1", to_input="options"),
    ]
    wf = Workflow(recipe_id="r1", nodes=nodes, edges=edges)
    assert validate(wf, registry) == []


def test_cycle_detected(registry):
    nodes = [
        Node(id="a", type_id="fake.transform", params={}),
        Node(id="b", type_id="fake.transform", params={}),
    ]
    edges = [
        Edge(id="e1", from_node="a", from_output="video", to_node="b", to_input="video"),
        Edge(id="e2", from_node="b", from_output="video", to_node="a", to_input="video"),
    ]
    wf = Workflow(recipe_id="r1", nodes=nodes, edges=edges)
    issues = validate(wf, registry)
    assert any("cycle" in i for i in issues)
    try:
        topo_order(wf)
        assert False, "expected GraphCycleError"
    except GraphCycleError:
        pass


def test_pick_selected_must_be_incoming_edge(registry):
    nodes = [
        Node(id="p1", type_id="text.prompt", params={"text": "one"}),
        Node(id="pick1", type_id="human.pick", params={}, selected="not-an-edge"),
    ]
    edges = [Edge(id="e1", from_node="p1", from_output="text", to_node="pick1", to_input="options")]
    wf = Workflow(recipe_id="r1", nodes=nodes, edges=edges)
    issues = validate(wf, registry)
    assert any("not an incoming edge" in i for i in issues)


def test_duplicate_node_id_rejected_at_construction():
    import pytest

    with pytest.raises(ValueError):
        Workflow(
            recipe_id="r1",
            nodes=[Node(id="a", type_id="x"), Node(id="a", type_id="y")],
            edges=[],
        )
