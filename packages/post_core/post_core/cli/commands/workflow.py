"""`post workflow new --recipe|show|plan|states`.

Recipes (T12) that compile a graph from a brand kit + shot list don't exist yet. Until
then, `workflow new` takes the graph directly as JSON (`--graph nodes.json`, `{"nodes":
[...], "edges": [...]}`, the same shape `graph.workflow.Node`/`Edge` validate) -- a real
recipe module will build that same `Workflow` object and write it the same way.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ...graph.hashing import compute_hashes
from ...graph.plan import plan as plan_fn
from ...graph.state import compute_states
from ...graph.workflow import Edge, Node, Workflow, WorkflowError, assert_valid
from ...store.errors import NotFound
from ..context import build_registry, load_workflow, resolve_project_root, save_workflow
from ..output import CLIError


def _load_graph(path: str | None) -> tuple[list[Node], list[Edge]]:
    if not path:
        return [], []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    nodes = [Node.model_validate(n) for n in data.get("nodes", [])]
    edges = [Edge.model_validate(e) for e in data.get("edges", [])]
    return nodes, edges


def workflow_new(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    registry = build_registry()
    nodes, edges = _load_graph(args.graph)
    workflow = Workflow(recipe_id=args.recipe, nodes=nodes, edges=edges)
    try:
        assert_valid(workflow, registry)
    except WorkflowError as exc:
        raise CLIError(f"invalid workflow: {'; '.join(exc.issues)}") from exc
    save_workflow(root, workflow, expected_rev=0)
    return {"workflow_id": workflow.id}


def _load_workflow(root: Path, workflow_id: str) -> tuple[Workflow, int]:
    try:
        return load_workflow(root, workflow_id)
    except NotFound as exc:
        raise CLIError(str(exc)) from exc


def workflow_show(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    workflow, revision = _load_workflow(root, args.workflow)
    return {"revision": revision, "workflow": workflow}


def workflow_plan(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    workflow, _rev = _load_workflow(root, args.workflow)
    registry = build_registry()
    targets = json.loads(args.targets) if args.targets else None
    hashes = compute_hashes(workflow, registry)
    states = compute_states(workflow, registry, root, hashes=hashes)
    plan = plan_fn(workflow, registry, states, targets=targets, from_node=args.from_node)
    return {"workflow_id": workflow.id, "plan": plan}


def workflow_states(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    workflow, _rev = _load_workflow(root, args.workflow)
    registry = build_registry()
    hashes = compute_hashes(workflow, registry)
    states = compute_states(workflow, registry, root, hashes=hashes)
    return {"workflow_id": workflow.id, "states": {nid: s.value for nid, s in states.items()}}


__all__ = ["workflow_new", "workflow_show", "workflow_plan", "workflow_states"]
