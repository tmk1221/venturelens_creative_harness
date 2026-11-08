"""`/api/projects/{pid}/workflows`: new, show, plan, states, run. Mirrors `post workflow
...` and `post run` -- persistence goes through `post_core.cli.context.save_workflow` /
`load_workflow` (T10 task note: "workflow" isn't wired into `store.store.KIND_MODELS` yet;
another in-flight task owns that, so this module calls `cli/context.py` as-is, unedited,
exactly like the CLI does, rather than duplicating its on-disk layout)."""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

import json as _json

from post_core.cli.context import load_workflow, save_workflow
from post_core.graph.hashing import compute_hashes
from post_core.graph.plan import plan as plan_fn
from post_core.graph.state import NodeState, artifact_dir, compute_states
from post_core.graph.workflow import Edge, Node, Workflow, WorkflowError, assert_valid
from post_core.queue.enqueue import Authorization, enqueue as enqueue_fn
from post_core.store.errors import NotFound, RevisionConflict

from ..deps import get_project_root
from ..graph_support import combined_cmd_for, combined_registry as build_registry
from ..models import EdgeOpOut, NodeUpdateOut, PlanOut, RunOut, StatesOut, WorkflowRef

router = APIRouter(prefix="/api/projects/{pid}/workflows", tags=["workflows"])


class GraphIn(BaseModel):
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []


class WorkflowNewRequest(BaseModel):
    recipe: str
    graph: GraphIn = GraphIn()


@router.post("", response_model=WorkflowRef)
def workflow_new(body: WorkflowNewRequest, root: Path = Depends(get_project_root)) -> WorkflowRef:
    registry = build_registry()
    nodes = [Node.model_validate(n) for n in body.graph.nodes]
    edges = [Edge.model_validate(e) for e in body.graph.edges]
    workflow = Workflow(recipe_id=body.recipe, nodes=nodes, edges=edges)
    try:
        assert_valid(workflow, registry)
    except WorkflowError as exc:
        raise HTTPException(status_code=400, detail=f"invalid workflow: {'; '.join(exc.issues)}") from exc
    save_workflow(root, workflow, expected_rev=0)
    return WorkflowRef(workflow_id=workflow.id)


def _load(root: Path, workflow_id: str) -> tuple[Workflow, int]:
    try:
        return load_workflow(root, workflow_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{workflow_id}")
def workflow_show(workflow_id: str, root: Path = Depends(get_project_root)) -> dict:
    workflow, revision = _load(root, workflow_id)
    return {"revision": revision, "workflow": workflow.model_dump(mode="json")}


@router.get("/{workflow_id}/plan", response_model=PlanOut)
def workflow_plan(
    workflow_id: str, targets: Optional[str] = Query(None), from_node: Optional[str] = Query(None, alias="from"),
    root: Path = Depends(get_project_root),
) -> PlanOut:
    import json

    workflow, _rev = _load(root, workflow_id)
    registry = build_registry()
    target_ids = json.loads(targets) if targets else None
    hashes = compute_hashes(workflow, registry)
    states = compute_states(workflow, registry, root, hashes=hashes)
    plan = plan_fn(workflow, registry, states, targets=target_ids, from_node=from_node)
    return PlanOut(workflow_id=workflow.id, plan=plan.model_dump(mode="json"))


@router.get("/{workflow_id}/states", response_model=StatesOut)
def workflow_states(workflow_id: str, root: Path = Depends(get_project_root)) -> StatesOut:
    workflow, _rev = _load(root, workflow_id)
    registry = build_registry()
    hashes = compute_hashes(workflow, registry)
    states = compute_states(workflow, registry, root, hashes=hashes)
    return StatesOut(workflow_id=workflow.id, states={nid: s.value for nid, s in states.items()})


@router.get("/{workflow_id}/nodes")
def workflow_nodes(workflow_id: str, root: Path = Depends(get_project_root)) -> dict:
    """State + input_hash + (if built) manifest outputs for every node -- one call the card
    and graph views poll instead of re-deriving hashes/artifact paths client-side. `outputs`
    entries carry whatever `sha256` the worker declared, which the client resolves through
    `GET /api/projects/{pid}/assets/{sha256}` (`routes/media.py`) to render a thumbnail or
    clip."""
    workflow, _rev = _load(root, workflow_id)
    registry = build_registry()
    hashes = compute_hashes(workflow, registry)
    states = compute_states(workflow, registry, root, hashes=hashes)
    out = []
    for node in workflow.nodes:
        h = hashes.get(node.id)
        state = states.get(node.id, NodeState.UNRESOLVED)
        outputs: list[dict] = []
        fail_cause: Optional[str] = None
        if h is not None and state in (NodeState.DONE, NodeState.STALE, NodeState.NEEDS_APPROVAL):
            manifest_path = artifact_dir(root, node.type_id, h) / "manifest.json"
            if manifest_path.is_file():
                try:
                    outputs = _json.loads(manifest_path.read_text(encoding="utf-8")).get("outputs", [])
                except ValueError:
                    outputs = []
        elif h is not None and state == NodeState.FAILED:
            # T29: the graph view shows a failed node red with its one-sentence cause
            # (`queue.artifacts.mark_failed`'s `failed.json`, written alongside the
            # would-be manifest) instead of just a bare "failed" pill.
            failed_path = artifact_dir(root, node.type_id, h) / "failed.json"
            if failed_path.is_file():
                try:
                    fail_cause = _json.loads(failed_path.read_text(encoding="utf-8")).get("summary")
                except ValueError:
                    fail_cause = None
        out.append({
            "id": node.id, "type_id": node.type_id, "state": state.value, "input_hash": h,
            "selected": node.selected, "outputs": outputs, "fail_cause": fail_cause,
        })
    return {"workflow_id": workflow.id, "nodes": out}


class NodeAddRequest(BaseModel):
    id: Optional[str] = None
    type_id: str
    params: dict[str, Any] = {}


@router.post("/{workflow_id}/nodes", response_model=NodeUpdateOut)
def workflow_add_node(
    workflow_id: str, body: NodeAddRequest, root: Path = Depends(get_project_root),
) -> NodeUpdateOut:
    """Append one new, unwired node (e.g. the graph view's "+ reference image" palette
    button, which adds a `source.file` node the user then connects to a `still.generate`
    node's `continuity` input via `POST .../edges`) -- id auto-generated if omitted,
    params validated against the type's own schema, whole graph re-validated before save."""
    import uuid

    workflow, revision = _load(root, workflow_id)
    registry = build_registry()
    node_type = registry.get(body.type_id)  # UnknownNodeType (KeyError) -> 400
    try:
        validated = node_type.params_schema.model_validate(body.params)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"bad params for {body.type_id!r}: {exc}") from exc
    node_id = body.id or f"{body.type_id.replace('.', '-')}-{uuid.uuid4().hex[:8]}"
    new_node = Node(id=node_id, type_id=body.type_id, params=validated.model_dump(mode="json"))
    new_workflow = workflow.model_copy(update={"nodes": [*workflow.nodes, new_node]})
    try:
        assert_valid(new_workflow, registry)
    except WorkflowError as exc:
        raise HTTPException(status_code=400, detail=f"invalid workflow: {'; '.join(exc.issues)}") from exc
    new_rev = save_workflow(root, new_workflow, expected_rev=revision)
    return NodeUpdateOut(workflow_id=workflow_id, node_id=node_id, revision=new_rev)


class NodeUpdateRequest(BaseModel):
    params: dict[str, Any] = {}
    # For `pick` nodes: the id of the chosen incoming edge on "options" (the variant grid's
    # Pick button). None/omitted leaves an existing pick alone -- a params-only PATCH (e.g.
    # editing a still's prompt) must never accidentally clear a pick already made.
    selected: Optional[str] = None


@router.patch("/{workflow_id}/nodes/{node_id}", response_model=NodeUpdateOut)
def workflow_update_node(
    workflow_id: str, node_id: str, body: NodeUpdateRequest, root: Path = Depends(get_project_root),
) -> NodeUpdateOut:
    """Merge new param values into one node, re-validate its params against its NodeType's
    schema and the whole workflow's wiring, and save. Stale propagation needs no extra work
    here: it is derived (`graph.state.compute_states`), never stored -- changing a node's
    params changes its `input_hash` the next time anything reads state/plan, which is what
    marks it (and everything downstream) stale."""
    workflow, revision = _load(root, workflow_id)
    registry = build_registry()
    node = workflow.node(node_id)  # KeyError -> 400 via the app's global handler
    node_type = registry.get(node.type_id)  # UnknownNodeType (a KeyError) -> 400
    merged = {**node.params, **body.params}
    try:
        validated = node_type.params_schema.model_validate(merged)
    except Exception as exc:  # pydantic ValidationError
        raise HTTPException(status_code=400, detail=f"bad params for {node_id!r}: {exc}") from exc
    update: dict[str, Any] = {"params": validated.model_dump(mode="json")}
    if body.selected is not None:
        update["selected"] = body.selected
    new_node = node.model_copy(update=update)
    new_nodes = [new_node if n.id == node_id else n for n in workflow.nodes]
    new_workflow = workflow.model_copy(update={"nodes": new_nodes})
    try:
        assert_valid(new_workflow, registry)
    except WorkflowError as exc:
        raise HTTPException(status_code=400, detail=f"invalid workflow: {'; '.join(exc.issues)}") from exc
    new_rev = save_workflow(root, new_workflow, expected_rev=revision)
    return NodeUpdateOut(workflow_id=workflow_id, node_id=node_id, revision=new_rev)


@router.delete("/{workflow_id}/nodes/{node_id}", response_model=NodeUpdateOut)
def workflow_delete_node(
    workflow_id: str, node_id: str, root: Path = Depends(get_project_root),
) -> NodeUpdateOut:
    """T29 graph palette: delete a node and every edge touching it. A `pick` node whose
    `selected` edge was just removed loses that selection too, so it never dangles on an
    edge id that no longer exists (the same invariant `graph.workflow.validate` enforces)."""
    workflow, revision = _load(root, workflow_id)
    registry = build_registry()
    if not any(n.id == node_id for n in workflow.nodes):
        raise HTTPException(status_code=404, detail=f"no node {node_id!r} in workflow")
    remaining_edges = [e for e in workflow.edges if e.from_node != node_id and e.to_node != node_id]
    remaining_edge_ids = {e.id for e in remaining_edges}
    remaining_nodes = []
    for n in workflow.nodes:
        if n.id == node_id:
            continue
        if n.selected is not None and n.selected not in remaining_edge_ids:
            n = n.model_copy(update={"selected": None})
        remaining_nodes.append(n)
    new_workflow = workflow.model_copy(update={"nodes": remaining_nodes, "edges": remaining_edges})
    try:
        assert_valid(new_workflow, registry)
    except WorkflowError as exc:
        raise HTTPException(status_code=400, detail=f"invalid workflow: {'; '.join(exc.issues)}") from exc
    new_rev = save_workflow(root, new_workflow, expected_rev=revision)
    return NodeUpdateOut(workflow_id=workflow_id, node_id=node_id, revision=new_rev)


class EdgeAdd(BaseModel):
    id: Optional[str] = None
    from_node: str
    from_output: str
    to_node: str
    to_input: str


class EdgesRequest(BaseModel):
    add: list[EdgeAdd] = []
    remove: list[str] = []


@router.post("/{workflow_id}/edges", response_model=EdgeOpOut)
def workflow_edges(
    workflow_id: str, body: EdgesRequest, root: Path = Depends(get_project_root),
) -> EdgeOpOut:
    """Add and/or remove edges in one call, type-checked (`graph.workflow.assert_valid`)
    against the node registry's handle types before anything is persisted."""
    import uuid

    workflow, revision = _load(root, workflow_id)
    registry = build_registry()
    remaining = [e for e in workflow.edges if e.id not in set(body.remove)]
    added = [
        Edge(
            id=a.id or f"e-{uuid.uuid4().hex[:8]}", from_node=a.from_node, from_output=a.from_output,
            to_node=a.to_node, to_input=a.to_input,
        )
        for a in body.add
    ]
    new_workflow = workflow.model_copy(update={"edges": [*remaining, *added]})
    try:
        assert_valid(new_workflow, registry)
    except WorkflowError as exc:
        raise HTTPException(status_code=400, detail=f"invalid workflow: {'; '.join(exc.issues)}") from exc
    new_rev = save_workflow(root, new_workflow, expected_rev=revision)
    return EdgeOpOut(
        workflow_id=workflow_id, revision=new_rev, edges=[e.model_dump(mode="json") for e in new_workflow.edges],
    )


class LayoutRequest(BaseModel):
    positions: dict[str, dict[str, float]]  # node_id -> {x, y}


@router.patch("/{workflow_id}/layout")
def workflow_update_layout(
    workflow_id: str, body: LayoutRequest, root: Path = Depends(get_project_root),
) -> dict:
    """T27 item 5 follow-up to T26: persist the graph view's drag positions into `Workflow.
    layout` (UI-only, never read by hashing.py/state.py) so re-opening the graph doesn't
    always re-run dagre auto-layout from scratch. Layout writes are last-write-wins and don't
    need the caller's revision -- retries once on a save race against another writer."""
    for _ in range(2):
        workflow, revision = _load(root, workflow_id)
        merged_layout = {**workflow.layout, **body.positions}
        new_workflow = workflow.model_copy(update={"layout": merged_layout})
        try:
            new_rev = save_workflow(root, new_workflow, expected_rev=revision)
            return {"workflow_id": workflow_id, "revision": new_rev, "layout": merged_layout}
        except RevisionConflict:
            continue
    raise HTTPException(status_code=409, detail="layout save conflict")


class RunRequest(BaseModel):
    """T31: no `cap`/`unit` -- a budget is created only by `PUT .../budgets/{id}`, never as a
    side effect of running. `budget` must already exist (else 409); `node_ids` limits the
    authorisation to exactly the spending nodes the person was shown."""

    model_config = ConfigDict(extra="forbid")

    targets: Optional[list[str]] = None
    from_node: Optional[str] = None
    budget: Optional[str] = None
    by: Optional[str] = None
    node_ids: Optional[list[str]] = None
    covers_downstream: bool = False


@router.post("/{workflow_id}/run", response_model=RunOut)
def run_workflow(workflow_id: str, body: RunRequest, root: Path = Depends(get_project_root)) -> RunOut:
    """Refusals come from `enqueue()` (the core enforces them, not this route) and map to
    JSON in `errors.py`: no authorisation / estimate past headroom / unit mismatch -> 402,
    a budget that was never created -> 409. A refused run persists nothing."""
    workflow, _rev = _load(root, workflow_id)
    registry = build_registry()
    hashes = compute_hashes(workflow, registry)
    states = compute_states(workflow, registry, root, hashes=hashes)
    plan = plan_fn(workflow, registry, states, targets=body.targets, from_node=body.from_node)

    authorization = None
    if body.budget:
        authorization = Authorization(
            budget_id=body.budget, by=body.by or "api",
            node_ids=frozenset(body.node_ids) if body.node_ids is not None else None,
            workflow_id=workflow.id, covers_downstream=body.covers_downstream,
        )

    job_ids = enqueue_fn(
        root, workflow, registry, hashes, plan,
        cmd_for=combined_cmd_for(workflow, registry, root), authorization=authorization,
    )
    return RunOut(workflow_id=workflow.id, job_ids=job_ids, plan=plan.model_dump(mode="json"))


__all__ = ["router"]
