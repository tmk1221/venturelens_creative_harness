"""Hash stability, param/pick/brand change propagation."""
from __future__ import annotations

from post_core.graph.hashing import compute_hashes, node_input_hash
from post_core.graph.workflow import Edge, Node, Workflow


def chain_workflow(prompt_text="a cat", brand_kit_hash=None) -> Workflow:
    nodes = [
        Node(id="prompt1", type_id="text.prompt", params={"text": prompt_text}),
        Node(id="gen1", type_id="fake.generate", params={"prompt": prompt_text}),
        Node(id="xform1", type_id="fake.transform", params={}),
    ]
    edges = [
        Edge(id="e1", from_node="prompt1", from_output="text", to_node="gen1", to_input="prompt"),
        Edge(id="e2", from_node="gen1", from_output="video", to_node="xform1", to_input="video"),
    ]
    return Workflow(recipe_id="r1", nodes=nodes, edges=edges, brand_kit_hash=brand_kit_hash)


def test_hash_stable_across_key_order_and_layout(registry):
    wf1 = chain_workflow()
    wf2 = chain_workflow()
    wf2 = wf2.model_copy(update={"layout": {"gen1": {"x": 100, "y": 200}}})
    h1 = compute_hashes(wf1, registry)
    h2 = compute_hashes(wf2, registry)
    assert h1 == h2
    assert all(v is not None for v in h1.values())

    # params dict key order shouldn't matter either.
    nih_a = node_input_hash("t", 1, {"a": 1, "b": 2}, [], None)
    nih_b = node_input_hash("t", 1, {"b": 2, "a": 1}, [], None)
    assert nih_a == nih_b


def test_param_change_makes_that_node_and_downstream_stale_siblings_untouched(registry):
    nodes = [
        Node(id="prompt1", type_id="text.prompt", params={"text": "a cat"}),
        Node(id="gen1", type_id="fake.generate", params={"prompt": "a cat"}),
        Node(id="xform1", type_id="fake.transform", params={}),
        Node(id="sibling", type_id="fake.transform", params={}),  # no edges: independent
    ]
    edges = [
        Edge(id="e1", from_node="prompt1", from_output="text", to_node="gen1", to_input="prompt"),
        Edge(id="e2", from_node="gen1", from_output="video", to_node="xform1", to_input="video"),
    ]
    wf_before = Workflow(recipe_id="r1", nodes=nodes, edges=edges)
    before = compute_hashes(wf_before, registry)

    nodes_after = [n.model_copy() for n in nodes]
    nodes_after[1] = nodes_after[1].model_copy(update={"params": {"prompt": "a dog"}})
    wf_after = Workflow(recipe_id="r1", nodes=nodes_after, edges=edges)
    after = compute_hashes(wf_after, registry)

    assert before["prompt1"] == after["prompt1"]  # untouched upstream
    assert before["gen1"] != after["gen1"]  # the changed node
    assert before["xform1"] != after["xform1"]  # downstream of it
    assert before["sibling"] == after["sibling"]  # unrelated sibling untouched


def test_pick_change_rehashes_downstream(registry):
    nodes = [
        Node(id="p1", type_id="text.prompt", params={"text": "one"}),
        Node(id="p2", type_id="text.prompt", params={"text": "two"}),
        Node(id="pick1", type_id="human.pick", params={}, selected="e1"),
        Node(id="xform1", type_id="fake.transform", params={}),
    ]
    edges = [
        Edge(id="e1", from_node="p1", from_output="text", to_node="pick1", to_input="options"),
        Edge(id="e2", from_node="p2", from_output="text", to_node="pick1", to_input="options"),
        Edge(id="e3", from_node="pick1", from_output="chosen", to_node="xform1", to_input="video"),
    ]
    wf_e1 = Workflow(recipe_id="r1", nodes=nodes, edges=edges)
    hashes_e1 = compute_hashes(wf_e1, registry)

    nodes_e2 = [n.model_copy() for n in nodes]
    nodes_e2[2] = nodes_e2[2].model_copy(update={"selected": "e2"})
    wf_e2 = Workflow(recipe_id="r1", nodes=nodes_e2, edges=edges)
    hashes_e2 = compute_hashes(wf_e2, registry)

    assert hashes_e1["pick1"] != hashes_e2["pick1"]
    assert hashes_e1["xform1"] != hashes_e2["xform1"]


def test_unmade_pick_is_unresolved(registry):
    nodes = [
        Node(id="p1", type_id="text.prompt", params={"text": "one"}),
        Node(id="pick1", type_id="human.pick", params={}),  # not selected
        Node(id="xform1", type_id="fake.transform", params={}),
    ]
    edges = [
        Edge(id="e1", from_node="p1", from_output="text", to_node="pick1", to_input="options"),
        Edge(id="e2", from_node="pick1", from_output="chosen", to_node="xform1", to_input="video"),
    ]
    wf = Workflow(recipe_id="r1", nodes=nodes, edges=edges)
    hashes = compute_hashes(wf, registry)
    assert hashes["pick1"] is None
    assert hashes["xform1"] is None
    assert hashes["p1"] is not None


def test_brand_hash_only_affects_brand_consumers(registry):
    nodes = [
        Node(id="prompt1", type_id="text.prompt", params={"text": "a cat"}),
        Node(id="gen1", type_id="fake.generate", params={"prompt": "a cat"}),
        Node(id="branded1", type_id="fake.brand_consumer", params={}),
    ]
    edges = [
        Edge(id="e1", from_node="prompt1", from_output="text", to_node="gen1", to_input="prompt"),
        Edge(id="e2", from_node="gen1", from_output="video", to_node="branded1", to_input="video"),
    ]
    wf_a = Workflow(recipe_id="r1", nodes=nodes, edges=edges, brand_kit_hash="brand-a")
    wf_b = Workflow(recipe_id="r1", nodes=nodes, edges=edges, brand_kit_hash="brand-b")
    hashes_a = compute_hashes(wf_a, registry)
    hashes_b = compute_hashes(wf_b, registry)

    assert hashes_a["prompt1"] == hashes_b["prompt1"]
    assert hashes_a["gen1"] == hashes_b["gen1"]
    assert hashes_a["branded1"] != hashes_b["branded1"]
