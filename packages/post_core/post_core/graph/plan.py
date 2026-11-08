"""plan(): pure derivation of what's runnable next.

Disk enters the picture only in `state.py`; `plan()` takes the already-computed `states`
dict as input and does no I/O of its own, so it stays a pure function (ARCHITECTURE.md §1,
T04's own requirement) that is trivial to unit test against fake states.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict

from .registry import NodeRegistry
from .state import NodeState
from .types import Cost
from .workflow import Workflow, topo_order


class NodeSpend(BaseModel):
    """One spending node a run will lead to, with its own pre-run estimate (None when no
    estimate could be made -- `queue.enqueue` refuses such a node rather than spend blind)."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    type_id: str
    amount: Optional[float] = None
    unit: Optional[str] = None
    provider: Optional[str] = None
    runnable: bool = True


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runnable: list[str] = []
    needs_authorization: list[str] = []
    blocked_on_human: list[str] = []
    estimated_cost: list[Cost] = []
    # T31: every spending node this run leads to with no further human decision -- the
    # runnable ones (`runnable=True`) plus ones downstream that become ready as in-plan work
    # finishes (`runnable=False`; what an authorisation's `covers_downstream` continues
    # into). What a confirm shows, and what one click's budget + authorisation must cover.
    spends: list[NodeSpend] = []


def node_estimate(workflow: Workflow, registry: NodeRegistry, node_id: str) -> Optional[Cost]:
    """A node's pre-run cost estimate, or None if it has none or estimating failed (a real
    provider's cost endpoint being down must read as "unknown", never as "free")."""
    node = workflow.node(node_id)
    node_type = registry.get(node.type_id)
    try:
        params = node_type.params_schema.model_validate(node.params)
        return node_type.estimate_cost(params)
    except Exception:  # noqa: BLE001 -- any failure to estimate is "no estimate"
        return None


def _ancestors(workflow: Workflow, node_ids: set[str]) -> set[str]:
    incoming: dict[str, list[str]] = {}
    for e in workflow.edges:
        incoming.setdefault(e.to_node, []).append(e.from_node)
    seen: set[str] = set()
    stack = list(node_ids)
    while stack:
        nid = stack.pop()
        for parent in incoming.get(nid, []):
            if parent not in seen:
                seen.add(parent)
                stack.append(parent)
    return seen


def _descendants(workflow: Workflow, node_id: str) -> set[str]:
    outgoing: dict[str, list[str]] = {}
    for e in workflow.edges:
        outgoing.setdefault(e.from_node, []).append(e.to_node)
    seen: set[str] = set()
    stack = [node_id]
    while stack:
        nid = stack.pop()
        for child in outgoing.get(nid, []):
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return seen


def _stale_node_is_actually_runnable(
    workflow: Workflow, registry: NodeRegistry, states: dict[str, NodeState], node_id: str,
) -> bool:
    """A STALE node's current hash has never been built, but unlike READY (`state.py` only
    grants that once every upstream node is truly `DONE`), STALE is granted purely from
    local history, with no such check -- a node several hops downstream of the one that
    actually changed can come back STALE while its own nearer upstream is itself still
    BLOCKED/STALE and hasn't produced the file this node's `cmd_for` would need to read yet
    (T26: rewiring a reference image into `still.generate` cascades staleness all the way to
    `asset.verify`, but only `still.generate` itself has anything ready to rebuild right
    now). A `kind="source"` producer (e.g. `source.file`) needs no build step at all -- its
    output is just its own params -- so it never blocks eligibility."""
    for edge in workflow.edges_into(node_id):
        producer_kind = registry.get(workflow.node(edge.from_node).type_id).kind
        if producer_kind == "source":
            continue
        if states.get(edge.from_node) != NodeState.DONE:
            return False
    return True


def _chain(
    workflow: Workflow, registry: NodeRegistry, states: dict[str, NodeState],
    order: list[str], relevant: set[str], runnable: list[str],
) -> list[str]:
    """Compute nodes in `relevant` that are not runnable yet but will be once the runnable
    ones (and earlier chain nodes) finish, with no pick/approval in between: every upstream
    is already DONE, runnable, in the chain, a source, or a pick whose chosen option is."""
    will_finish = set(runnable) | {nid for nid, st in states.items() if st == NodeState.DONE}
    chain: list[str] = []
    for nid in order:
        if nid not in relevant or nid in will_finish:
            continue
        node = workflow.node(nid)
        kind = registry.get(node.type_id).kind
        if kind == "pick":
            chosen = next((e for e in workflow.edges_into(nid, "options") if e.id == node.selected), None)
            if chosen is not None and chosen.from_node in will_finish:
                will_finish.add(nid)
            continue
        if kind != "compute" or states.get(nid) not in (NodeState.BLOCKED, NodeState.STALE):
            continue
        upstream_ok = all(
            e.from_node in will_finish or registry.get(workflow.node(e.from_node).type_id).kind == "source"
            for e in workflow.edges_into(nid)
        )
        if upstream_ok:
            chain.append(nid)
            will_finish.add(nid)
    return chain


def plan(
    workflow: Workflow,
    registry: NodeRegistry,
    states: dict[str, NodeState],
    targets: Optional[list[str]] = None,
    from_node: Optional[str] = None,
) -> Plan:
    """Order runnable nodes, flag which need spend authorisation, total estimated cost,
    and report what's blocked on a human.

    `targets`, if given, restricts the plan to those nodes plus everything they transitively
    depend on. `from_node`, if given, further restricts it to that node plus its downstream
    descendants (a partial re-run). Both may be combined.
    """
    relevant = {n.id for n in workflow.nodes}
    if targets:
        relevant = set(targets) | _ancestors(workflow, set(targets))
    if from_node is not None:
        relevant &= {from_node} | _descendants(workflow, from_node)

    order = topo_order(workflow)
    # STALE alongside READY: a stale node's *current* input_hash has never been built (only
    # an old, now-superseded one has) -- rebuilding it is exactly the same job as building a
    # READY node for the first time (T26: this is what lets the graph view's "run from here"
    # actually rebuild a node the user just marked stale by rewiring its inputs). Gated by
    # `_stale_node_is_actually_runnable` since, unlike READY, STALE alone doesn't guarantee
    # this node's own upstream files exist yet to build it from.
    runnable = [
        nid for nid in order
        if nid in relevant and (
            states.get(nid) == NodeState.READY
            or (states.get(nid) == NodeState.STALE and _stale_node_is_actually_runnable(workflow, registry, states, nid))
        )
    ]
    needs_authorization = [
        nid for nid in runnable if registry.get(workflow.node(nid).type_id).spends
    ]
    blocked_on_human = [
        nid
        for nid in order
        if nid in relevant and states.get(nid) in (NodeState.NEEDS_PICK, NodeState.NEEDS_APPROVAL)
    ]

    cost_by_key: dict[tuple[str, Optional[str]], float] = {}
    spends: list[NodeSpend] = []
    chain = _chain(workflow, registry, states, order, relevant, runnable)
    for nid in [*runnable, *chain]:
        node_type = registry.get(workflow.node(nid).type_id)
        if nid in chain and not node_type.spends:
            continue
        cost = node_estimate(workflow, registry, nid)
        if node_type.spends:
            spends.append(NodeSpend(
                node_id=nid, type_id=node_type.id, runnable=nid not in chain,
                amount=cost.amount if cost else None, unit=cost.unit if cost else None,
                provider=cost.provider if cost else None,
            ))
        if cost is not None and nid not in chain:
            key = (cost.unit, cost.provider)
            cost_by_key[key] = cost_by_key.get(key, 0.0) + cost.amount
    estimated_cost = [
        Cost(amount=amount, unit=unit, provider=provider)
        for (unit, provider), amount in sorted(cost_by_key.items(), key=lambda kv: (kv[0][0], kv[0][1] or ""))
    ]

    return Plan(
        runnable=runnable,
        needs_authorization=needs_authorization,
        blocked_on_human=blocked_on_human,
        estimated_cost=estimated_cost,
        spends=spends,
    )
