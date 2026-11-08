"""Content-addressed hashing: `input_hash(node)` per ARCHITECTURE.md §1.

A node's input_hash is computed purely from the workflow's own definition: the hash of
(type id + version, params, sorted upstream input_hashes, brand hash if consumed). It never
looks at disk or at `Workflow.layout`, so it is stable across dict/JSON key order and
unaffected by moving nodes on a canvas. Because content addressing means "same inputs,
same address," a node's own input_hash doubles as the address other nodes hash against for
"upstream output content hash" -- there is no separate notion of an output hash here.
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from .registry import NodeRegistry
from .workflow import Workflow, topo_order


def canonical_json(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def node_input_hash(
    type_id: str,
    type_version: int,
    params: dict,
    upstream_hashes: list[str],
    brand_kit_hash: Optional[str],
) -> str:
    payload = {
        "type": type_id,
        "version": type_version,
        "params": params,
        "upstream": sorted(upstream_hashes),
        "brand": brand_kit_hash,
    }
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def compute_hashes(workflow: Workflow, registry: NodeRegistry) -> dict[str, Optional[str]]:
    """Return `{node_id: input_hash | None}` for every node.

    None means the node cannot yet be resolved to a content address -- either it is itself
    an unmade `pick`, or an upstream node is (transitively) an unmade pick. Requires an
    acyclic workflow; call `workflow.validate` first if the graph may not be one.
    """
    order = topo_order(workflow)
    hashes: dict[str, Optional[str]] = {}

    for node_id in order:
        node = workflow.node(node_id)
        node_type = registry.get(node.type_id)

        if node_type.kind == "pick":
            options = workflow.edges_into(node_id, "options")
            chosen = next((e for e in options if e.id == node.selected), None)
            if chosen is None:
                hashes[node_id] = None
                continue
            upstream = hashes.get(chosen.from_node)
            if upstream is None:
                hashes[node_id] = None
                continue
            upstream_hashes = [upstream]
        else:
            upstream_hashes = []
            blocked = False
            for e in workflow.edges_into(node_id):
                h = hashes.get(e.from_node)
                if h is None:
                    blocked = True
                    break
                upstream_hashes.append(h)
            if blocked:
                hashes[node_id] = None
                continue

        brand = workflow.brand_kit_hash if node_type.uses_brand_kit else None
        hashes[node_id] = node_input_hash(
            node_type.id, node_type.version, node.params, upstream_hashes, brand
        )

    return hashes
