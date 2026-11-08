"""T30b: "Decisions" -- a project-wide list of outstanding decisions (picks, approvals,
failed steps with cause, waiting-on-<something>), each linking to the beat/node that needs
attention. Renamed from the old app's "Needs you" (spec, "Additions" section) -- these are
the SAME rows the graph/card states derive from, not a separate evidence scan: every row
here comes straight out of `graph.state.compute_states` for each span's own workflow, plus a
`waiting_on` pass over `Span.cast_refs` (a beat can be blocked on an unapproved cast anchor
before it ever gets a workflow at all -- `instantiate.CastNotReady`)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from ..cli.context import load_workflow
from ..graph.hashing import compute_hashes
from ..graph.state import NodeState, artifact_dir, compute_states
from ..model.cut import Cut
from ..store.errors import NotFound
from . import cast as cast_mod
from . import full_registry

DecisionKind = Literal["pick", "approve", "failed", "waiting_on"]


@dataclass(frozen=True)
class DecisionRow:
    kind: DecisionKind
    span_id: str
    node_id: Optional[str]
    cause: str
    link: str


def _fail_cause(project_root: str | Path, node_type_id: str, node_hash: Optional[str]) -> str:
    if node_hash is None:
        return "failed"
    failed_path = artifact_dir(project_root, node_type_id, node_hash) / "failed.json"
    if not failed_path.is_file():
        return "failed"
    try:
        return json.loads(failed_path.read_text(encoding="utf-8")).get("summary", "failed")
    except ValueError:
        return "failed"


def decisions_for_cut(project_root: str | Path, cut: Cut) -> list[DecisionRow]:
    rows: list[DecisionRow] = []
    registry = full_registry()

    for span in cut.spans:
        if span.orphaned:
            continue
        for name in span.cast_refs:
            if not cast_mod.anchor_ready(project_root, name):
                rows.append(DecisionRow(
                    kind="waiting_on", span_id=span.id, node_id=None,
                    cause=f"cast {name!r} has no approved anchor yet", link=f"span:{span.id}",
                ))
        if not span.workflow_id:
            continue
        try:
            workflow, _rev = load_workflow(project_root, span.workflow_id)
        except NotFound:
            continue
        hashes = compute_hashes(workflow, registry)
        states = compute_states(workflow, registry, project_root, hashes=hashes)
        for node in workflow.nodes:
            state = states.get(node.id)
            link = f"span:{span.id}/node:{node.id}"
            if state == NodeState.NEEDS_PICK:
                rows.append(DecisionRow(kind="pick", span_id=span.id, node_id=node.id, cause="pick a variant", link=link))
            elif state == NodeState.NEEDS_APPROVAL:
                cause = "needs consent" if node.type_id == "consent.gate" else "needs approval"
                rows.append(DecisionRow(kind="approve", span_id=span.id, node_id=node.id, cause=cause, link=link))
            elif state == NodeState.FAILED:
                cause = _fail_cause(project_root, node.type_id, hashes.get(node.id))
                rows.append(DecisionRow(kind="failed", span_id=span.id, node_id=node.id, cause=cause, link=link))
    return rows


def counts_by_kind(rows: list[DecisionRow]) -> dict[str, int]:
    counts: dict[str, int] = {"pick": 0, "approve": 0, "failed": 0, "waiting_on": 0}
    for row in rows:
        counts[row.kind] = counts.get(row.kind, 0) + 1
    return counts


__all__ = ["DecisionRow", "DecisionKind", "decisions_for_cut", "counts_by_kind"]
