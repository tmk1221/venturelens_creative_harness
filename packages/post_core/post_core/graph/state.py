"""Per-node state, derived from disk artifacts (ARCHITECTURE.md §1).

Artifact dir: `<root>/.post3/artifacts/<node_type>/<input_hash>/manifest.json`. Content
addressing means the same (type, params, upstream) always resolves to the same dir, but it
can't by itself tell two different *node ids* apart if they happen to hash the same, nor
can it tell you a node id's hash used to be something else. So each node id also gets a
tiny append-only hash history at `<root>/.post3/artifacts/_history/<node_id>.json`,
recorded here as hashes are computed, purely so a later param/pick change can be recognised
as "stale" (an old, still-listed output exists) rather than merely "not built yet".
"""
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Optional

from ..store.atomic import locked, read_envelope, write_envelope
from ..store.paths import store_root
from . import approvals as approvals_mod
from .hashing import compute_hashes
from .registry import NodeRegistry
from .workflow import Workflow, topo_order


class NodeState(str, Enum):
    UNRESOLVED = "unresolved"
    BLOCKED = "blocked"
    READY = "ready"
    DONE = "done"
    STALE = "stale"
    NEEDS_PICK = "needs_pick"
    NEEDS_APPROVAL = "needs_approval"
    FAILED = "failed"


def artifact_dir(project_root: str | Path, node_type_id: str, input_hash: str) -> Path:
    return store_root(project_root) / "artifacts" / node_type_id / input_hash


def _history_path(project_root: str | Path, node_id: str) -> Path:
    return store_root(project_root) / "artifacts" / "_history" / f"{node_id}.json"


def read_history(project_root: str | Path, node_id: str) -> list[str]:
    path = _history_path(project_root, node_id)
    with locked(path):
        _, data = read_envelope(path)
    return list((data or {}).get("hashes", []))


def record_history_entry(project_root: str | Path, node_id: str, input_hash: str) -> None:
    """Append `input_hash` to `node_id`'s hash history if not already present.

    Called by the executor (queue/artifacts.py) exactly when it writes a manifest, so that
    reading state (`compute_states`) never has to write to be correct (T05 carry-over #1).
    """
    path = _history_path(project_root, node_id)
    with locked(path):
        rev, data = read_envelope(path)
        hashes = list((data or {}).get("hashes", []))
        if input_hash not in hashes:
            hashes.append(input_hash)
            write_envelope(path, rev + 1, {"hashes": hashes})


def read_manifest(directory: Path) -> Optional[dict]:
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError:
        return None


def _has_failed_marker(directory: Path) -> bool:
    return (directory / "failed.json").is_file()


def _is_done(project_root: str | Path, node_type, input_hash: str) -> bool:
    directory = artifact_dir(project_root, node_type.id, input_hash)
    return read_manifest(directory) is not None and node_type.check(directory)


def compute_states(
    workflow: Workflow,
    registry: NodeRegistry,
    project_root: str | Path,
    hashes: Optional[dict[str, Optional[str]]] = None,
    record_history: bool = False,
) -> dict[str, NodeState]:
    """Derive every node's state. Pure by default (T05 carry-over #1): reading state never
    writes the per-node hash history. The executor calls `record_history_entry` itself, at
    the moment it writes a manifest, instead of relying on this function's side effect.

    `hashes` may be passed in (from `hashing.compute_hashes`) to avoid recomputing it; if
    omitted it is computed here. Passing `record_history=True` restores the old read-writes
    behaviour, for callers (and existing tests) that still want it in one step.
    """
    if hashes is None:
        hashes = compute_hashes(workflow, registry)

    order = topo_order(workflow)
    states: dict[str, NodeState] = {}

    for node_id in order:
        node = workflow.node(node_id)
        node_type = registry.get(node.type_id)

        if node_type.kind == "pick":
            if node.selected is None:
                states[node_id] = NodeState.NEEDS_PICK
                continue
            chosen = next(
                (e for e in workflow.edges_into(node_id, "options") if e.id == node.selected), None
            )
            upstream_state = states.get(chosen.from_node) if chosen else None
            states[node_id] = upstream_state if upstream_state is not None else NodeState.BLOCKED
            continue

        input_hash = hashes.get(node_id)
        if input_hash is None:
            states[node_id] = NodeState.UNRESOLVED
            continue

        if record_history:
            record_history_entry(project_root, node_id, input_hash)

        if node_type.kind == "approve":
            states[node_id] = (
                NodeState.DONE
                if approvals_mod.is_approved(project_root, input_hash)
                else NodeState.NEEDS_APPROVAL
            )
            continue

        if _is_done(project_root, node_type, input_hash):
            states[node_id] = NodeState.DONE
            continue

        directory = artifact_dir(project_root, node_type.id, input_hash)
        if _has_failed_marker(directory):
            states[node_id] = NodeState.FAILED
            continue

        history = read_history(project_root, node_id)
        has_older_done = any(
            old_hash != input_hash and _is_done(project_root, node_type, old_hash)
            for old_hash in history
        )
        if has_older_done:
            states[node_id] = NodeState.STALE
            continue

        upstream_ids = [e.from_node for e in workflow.edges_into(node_id)]
        all_upstream_done = all(states.get(u) == NodeState.DONE for u in upstream_ids)
        states[node_id] = NodeState.READY if all_upstream_done else NodeState.BLOCKED

    return states
