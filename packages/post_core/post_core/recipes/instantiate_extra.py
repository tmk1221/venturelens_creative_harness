"""T30b overflow from `instantiate.py` (kept under the ~400-line budget): the
`aroll_regenerate` recipe builder, its consent pre-approval, and the "+3 more" growth helper.
Nothing here is imported at module load time by `instantiate.py` except lazily, right where
each is used, to avoid a circular import (`instantiate.py` imports this module; this module
imports back from `instantiate.py` for its shared private helpers)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from brandkit.look import Look
from brandkit.schema import BrandKit

from .. import aspect as aspect_mod
from ..graph.hashing import compute_hashes
from ..graph.registry import NodeRegistry
from ..graph.workflow import Edge, Node, Workflow
from . import consent as consent_mod
from . import models
from . import node_types as nt
from .prompts import build_still_prompt


@dataclass(frozen=True)
class BeatAspects:
    still: str
    video: str
    crop_to: Optional[str]


def beat_aspects(target: str, video_model: Optional[str] = None, still_model: Optional[str] = None) -> BeatAspects:
    """T37: what a live_action beat for a `target`-aspect cut generates at. The video model
    decides, since its clip is what lands on the timeline: the cut's aspect when it offers
    it, else the nearest offered aspect that covers the frame plus `crop_to` (the video
    worker centre-crops; the card says "generated 9:16, cropped to 4:5"). Stills are that
    video's start/end frames, so they generate at the video's aspect (or the still model's
    nearest covering one) and are never cropped themselves. Models default to the node
    types' own defaults -- the ones `instantiate` builds with."""
    video_model = video_model or nt.VideoGenerateParams.model_fields["model"].default
    still_model = still_model or nt.StillGenerateParams.model_fields["model"].default
    video_at, crop_to = aspect_mod.choose_generation_aspect(target, models.offered_aspects(video_model))
    still_at, _ = aspect_mod.choose_generation_aspect(video_at, models.offered_aspects(still_model))
    return BeatAspects(still=still_at, video=video_at, crop_to=crop_to)


def build_aroll_regenerate(span, kit: BrandKit, look: Optional[Look]) -> tuple[list[Node], list[Edge]]:
    """T15 stub (T30b spec line): request -> consent gate. No presenter regeneration
    happens yet; see `recipes/workers/aroll_regenerate.py` and `recipes/consent.py`."""
    from .instantiate import _edge, _params

    bid = span.id
    request_id = f"{bid}-request"
    nodes = [Node(id=request_id, type_id="aroll.regenerate", params=_params(
        nt.ArollRegenerateParams, mode=span.regen_mode, instruction=span.instruction,
    ))]
    gate_id = f"{bid}-consent"
    nodes.append(Node(id=gate_id, type_id="consent.gate"))
    edges = [_edge(f"{bid}-e-consent", request_id, "request", gate_id, "subject")]
    return nodes, edges


def maybe_preapprove_consent(workflow: Workflow, project_root: str | Path) -> None:
    """If this project already has a recorded consent (`recipes.consent.has_consent`),
    pre-approve the freshly-built `consent.gate` node's own hash so it comes up `done`
    immediately rather than making a human click an extra approve button for a decision the
    project already made. A project with no consent record leaves the node `needs_approval`
    (the T30b spec's "needs_human until the project has a consent record")."""
    if not consent_mod.has_consent(project_root):
        return
    from . import full_registry
    from ..graph import approvals as approvals_mod

    gate_id = next((n.id for n in workflow.nodes if n.type_id == "consent.gate"), None)
    if gate_id is None:
        return
    registry: NodeRegistry = full_registry()
    node_hash = compute_hashes(workflow, registry).get(gate_id)
    if node_hash is None:
        return
    approvals_mod.approve(project_root, node_hash, by="system:consent-record")


def add_more_stills(workflow: Workflow, span, kit: BrandKit, look: Optional[Look], count: int) -> Workflow:
    """T30b: the "+3 more" card action -- append `count` more `still.generate` nodes to an
    already-instantiated `live_action` workflow, wired into the SAME `human.pick` node the
    original batch feeds (spec: "a second still node group sharing the pick"). Pure: returns
    a new `Workflow`; callers persist it (`cli.context.save_workflow`) themselves, the same
    as every other workflow-graph mutation in this app."""
    from .instantiate import _add_still_variants, _edge

    bid = span.id
    pick_id = f"{bid}-pick"
    if not any(n.id == pick_id for n in workflow.nodes):
        raise ValueError(f"add_more_stills: workflow has no pick node {pick_id!r}")
    start_index = sum(1 for n in workflow.nodes if n.id.startswith(f"{bid}-still"))
    # T37: the new batch shares the pick, so it matches the first batch's aspect exactly.
    first = next((n for n in workflow.nodes if n.type_id == "still.generate"), None)
    aspect = str((first.params or {}).get("aspect", "16:9")) if first is not None else "16:9"
    still_result = build_still_prompt(
        {"shot_type": span.shot_type, "subject": span.subject, "action": span.action,
         "setting": span.setting, "negatives": span.negatives},
        kit, look,
    )
    new_nodes: list[Node] = []
    new_ids: list[str] = []
    _add_still_variants(new_nodes, bid, still_result, max(1, count), start_index, new_ids, aspect=aspect)
    new_edges = [
        _edge(f"{bid}-e-still{start_index + i}", sid, "image", pick_id, "options")
        for i, sid in enumerate(new_ids)
    ]
    return workflow.model_copy(update={
        "nodes": [*workflow.nodes, *new_nodes], "edges": [*workflow.edges, *new_edges],
    })


__all__ = ["BeatAspects", "beat_aspects", "build_aroll_regenerate", "maybe_preapprove_consent", "add_more_stills"]
