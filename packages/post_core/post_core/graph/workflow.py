"""Workflow: a validated DAG of node instances + edges. See ARCHITECTURE.md §1.

`Workflow.layout` holds UI-only node positions; it is never read by hashing.py or state.py,
so moving nodes around a canvas never invalidates anything.
"""
from __future__ import annotations

from typing import Optional

from pydantic import Field, model_validator

from ..model.base import Entity, Value
from .registry import NodeRegistry
from .types import NodeType, types_compatible


class Node(Value):
    """One instance of a NodeType inside a Workflow."""

    id: str
    type_id: str
    params: dict = Field(default_factory=dict)
    # For `pick` nodes only: the id of the chosen incoming edge on the "options" input.
    # None means the pick has not been made yet.
    selected: Optional[str] = None


class Edge(Value):
    id: str
    from_node: str
    from_output: str
    to_node: str
    to_input: str


class Workflow(Entity):
    recipe_id: str
    brand_kit_hash: Optional[str] = None
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    layout: dict = Field(default_factory=dict)  # UI positions only; never affects hashes

    @model_validator(mode="after")
    def _unique_ids(self) -> "Workflow":
        node_ids = [n.id for n in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("duplicate node id in workflow")
        edge_ids = [e.id for e in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("duplicate edge id in workflow")
        return self

    def node(self, node_id: str) -> Node:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(f"no node {node_id!r} in workflow")

    def edges_into(self, node_id: str, input_name: Optional[str] = None) -> list[Edge]:
        return [
            e for e in self.edges
            if e.to_node == node_id and (input_name is None or e.to_input == input_name)
        ]

    def edges_from(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.from_node == node_id]


class GraphCycleError(ValueError):
    """The workflow's edges do not form a DAG."""


class WorkflowError(ValueError):
    """Raised by `assert_valid`, naming every problem found, not just the first."""

    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))


def topo_order(workflow: Workflow) -> list[str]:
    """A deterministic (lexicographically-tie-broken) topological order of node ids.

    Raises GraphCycleError, naming the nodes left over, if the edges do not form a DAG.
    """
    indeg = {n.id: 0 for n in workflow.nodes}
    adj: dict[str, list[str]] = {n.id: [] for n in workflow.nodes}
    for e in workflow.edges:
        if e.from_node in adj and e.to_node in indeg:
            adj[e.from_node].append(e.to_node)
            indeg[e.to_node] += 1

    ready = sorted(nid for nid, d in indeg.items() if d == 0)
    order: list[str] = []
    while ready:
        ready.sort()
        nid = ready.pop(0)
        order.append(nid)
        for nxt in adj[nid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                ready.append(nxt)

    if len(order) != len(indeg):
        remaining = sorted(set(indeg) - set(order))
        raise GraphCycleError(f"cycle detected among nodes: {remaining}")
    return order


def validate(workflow: Workflow, registry: NodeRegistry) -> list[str]:
    """Return a list of validation issues (empty = valid). Never raises on a bad graph."""
    issues: list[str] = []
    node_ids = {n.id for n in workflow.nodes}

    node_types: dict[str, NodeType] = {}
    for n in workflow.nodes:
        try:
            node_types[n.id] = registry.get(n.type_id)
        except Exception:
            issues.append(f"node {n.id!r}: unknown node type {n.type_id!r}")

    for e in workflow.edges:
        if e.from_node not in node_ids:
            issues.append(f"edge {e.id!r}: unknown from_node {e.from_node!r}")
        if e.to_node not in node_ids:
            issues.append(f"edge {e.id!r}: unknown to_node {e.to_node!r}")
    if issues:
        return issues  # can't check types/wiring against nodes we couldn't resolve

    nodes_by_id: dict[str, Node] = {n.id: n for n in workflow.nodes}

    incoming: dict[tuple[str, str], list[Edge]] = {}
    for e in workflow.edges:
        from_type = node_types.get(e.from_node)
        to_type = node_types.get(e.to_node)
        if from_type is None or to_type is None:
            continue
        try:
            out_spec = from_type.output(e.from_output)
        except KeyError:
            issues.append(f"edge {e.id!r}: {e.from_node!r} has no output {e.from_output!r}")
            continue
        try:
            in_spec = to_type.input(e.to_input)
        except KeyError:
            issues.append(f"edge {e.id!r}: {e.to_node!r} has no input {e.to_input!r}")
            continue
        # `source.file` is a single node type standing in for any handle type (image,
        # video, audio, ...): its instance-level `handle_type` param is the real output
        # type, not the static declaration on NodeType (which only exists to give it a
        # default so an un-parameterised source.file still type-checks as "video" against
        # older callers/tests). Every other node type's output type is static.
        out_type = out_spec.type
        if from_type.id == "source.file":
            from_node = nodes_by_id.get(e.from_node)
            if from_node is not None:
                out_type = from_node.params.get("handle_type", out_spec.type)
        if not types_compatible(out_type, in_spec.type):
            issues.append(f"edge {e.id!r}: type mismatch {out_type!r} -> {in_spec.type!r}")
        incoming.setdefault((e.to_node, e.to_input), []).append(e)

    for n in workflow.nodes:
        node_type = node_types.get(n.id)
        if node_type is None:
            continue
        for spec in node_type.inputs:
            wired = incoming.get((n.id, spec.name), [])
            if spec.required and not wired:
                issues.append(f"node {n.id!r}: required input {spec.name!r} is not wired")
            if not spec.many and len(wired) > 1:
                issues.append(
                    f"node {n.id!r}: input {spec.name!r} does not accept many, got {len(wired)}"
                )

    for n in workflow.nodes:
        node_type = node_types.get(n.id)
        if node_type is None or node_type.kind != "pick":
            continue
        if n.selected is not None:
            options = {e.id for e in incoming.get((n.id, "options"), [])}
            if n.selected not in options:
                issues.append(f"node {n.id!r}: selected {n.selected!r} is not an incoming edge")

    try:
        topo_order(workflow)
    except GraphCycleError as exc:
        issues.append(str(exc))

    return issues


def assert_valid(workflow: Workflow, registry: NodeRegistry) -> None:
    issues = validate(workflow, registry)
    if issues:
        raise WorkflowError(issues)
