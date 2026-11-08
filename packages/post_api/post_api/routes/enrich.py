"""T26: the Visuals-rail node editor's own endpoints -- instantiate a span's recipe
workflow, and the node registry (types + handle types + fixture-priced model options) the
web card/graph views render from. `/workflows/...` (nodes/edges/plan/run/states) already
lives in `workflows.py`; this module only owns what's specific to *span -> workflow* and to
introspecting what can be built, using the same `graph_support.combined_registry` every
other route/the background runtime uses, so a span-instantiated workflow (real T12 recipe
node types) is always plannable/runnable through the generic `/workflows/{id}/...` routes.
"""
from __future__ import annotations

import json
import typing
from pathlib import Path

from brandkit.schema import BrandKitError
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from post_core import aspect as aspect_mod
from post_core import brand as brand_mod
from post_core.cli.context import load_workflow
from post_core.graph.hashing import compute_hashes
from post_core.graph.state import artifact_dir
from post_core.graph.types import HandleType
from post_core.model.cut import Cut
from post_core.recipes import model_list as model_list_mod
from post_core.recipes import models as models_mod
from post_core.recipes.instantiate import CastNotReady, SpanSpec, add_more_stills, instantiate
from post_core.recipes.prompts import brief_asks_for_hold, recommend_end_frame
from post_core.store import store as store_module

from post_core.recipes import cast as cast_mod

from ..deps import get_project_root
from ..graph_support import combined_registry
from ..models import (
    CastEntryOut, CastListOut, ModelOptionOut, MoreVariantsOut, NodeRegistryOut, NodeTypeOut,
    ProvidedCatalogueOut, ProvidedClipOut, SpanWorkflowOut,
)

router = APIRouter(prefix="/api/projects/{pid}", tags=["enrich"])

# Span.kind -> T12 recipe id. Two naming generations both land here: T24's VISUALS picker
# ids ("video"/"anim", still written by the enrich e2e fixture script and its own tests via
# a raw `add_span`) and T30a's PictureKind values ("live_action"/"motion_graphic", written by
# `add_beat_spans` -- the only op the dialog/suggester-accept paths use now). "aroll" (keep
# the A-roll) has no generative workflow at all -- there is nothing to instantiate for it.
KIND_TO_RECIPE = {
    "video": "live_action",
    "live_action": "live_action",
    "anim": "motion_graphic",
    "motion_graphic": "motion_graphic",
    "overlay": "overlay",
    "provided": "provided",
}

# Fixture-priced model options (T12's Higgsfield fixtures) offered per spending node type,
# in fake-provider mode -- the only mode this task ever runs in. T29: a second stills option
# (`seedream_v4_5`) so the graph inspector's model swap has something to swap *to*.
MODEL_OPTIONS: dict[str, list[str]] = {
    "still.generate": ["nano_banana_2", "seedream_v4_5"],
    "endframe.generate": ["nano_banana_2", "seedream_v4_5"],
    "video.generate": ["kling3_0"],
}


def _project_kit(root: Path):
    """T33: the project's own kit (`Project.brand_kit`, `_demo` when unset), via the one
    helper the CLI and `routes/suggest.py` share. A kit that can't load is a 500 naming it."""
    try:
        return brand_mod.load_project_kit(root)
    except (brand_mod.UnknownKit, BrandKitError) as exc:
        raise HTTPException(status_code=500, detail=f"brand kit {brand_mod.project_kit_id(root)}: {exc}") from exc


def _find_span(cut: Cut, span_id: str):
    for span in cut.spans:
        if span.id == span_id:
            return span
    raise HTTPException(status_code=404, detail=f"no span {span_id!r} in cut {cut.id!r}")


def _span_text_and_seconds(root: Path, span) -> tuple[str, float]:
    """Best-effort words + duration under the span's anchors, straight from the anchored
    transcript's own word list (not the timeline -- this only needs an approximate seconds
    figure for `video.generate`'s duration and some prompt context, not frame-accurate
    placement)."""
    try:
        transcript, _rev = store_module.read(root, "transcript", span.start_anchor.transcript_id)
    except Exception:
        return "", 4.0
    words = {w.id: w for w in transcript.words}
    start_w = words.get(span.start_anchor.word_id)
    end_w = words.get(span.end_anchor.word_id)
    if start_w is None or end_w is None:
        return "", 4.0
    start_i = transcript.words.index(start_w)
    end_i = transcript.words.index(end_w)
    lo, hi = min(start_i, end_i), max(start_i, end_i)
    text = " ".join(w.text for w in transcript.words[lo : hi + 1])
    seconds = max(0.5, end_w.end - start_w.start)
    return text, seconds


@router.post("/cuts/{cut_id}/spans/{span_id}/workflow", response_model=SpanWorkflowOut)
def span_workflow(
    cut_id: str, span_id: str, root: Path = Depends(get_project_root),
) -> SpanWorkflowOut:
    """Instantiate the recipe for one span's kind and record the new workflow's id on the
    span. Idempotent: a span that already has a `workflow_id` just returns it (re-adding a
    visual to an already-planned beat should not silently orphan the existing graph)."""
    cut, cut_rev = store_module.read(root, "cut", cut_id)
    span = _find_span(cut, span_id)
    recipe_id = KIND_TO_RECIPE.get(span.kind)
    if recipe_id is None:
        raise HTTPException(status_code=400, detail=f"span kind {span.kind!r} has no generative recipe")
    if span.workflow_id:
        return SpanWorkflowOut(span_id=span.id, workflow_id=span.workflow_id, recipe_id=recipe_id)

    text, seconds = _span_text_and_seconds(root, span)
    spec_kwargs: dict = dict(id=span.id, seconds=seconds, instruction=span.note or text)
    # T37: generate for the span's own cut (a 4:5 short gets 4:5 B-roll, or nearest + crop),
    # hold generated video to its fps, and let a brief that asks for a hold end on one.
    spec_kwargs.update(
        aspect=aspect_mod.label(cut.aspect), fps=f"{cut.fps.num}/{cut.fps.den}",
        hold_ok=brief_asks_for_hold(f"{span.brief.text} {span.note}"),
    )
    if recipe_id in ("overlay", "provided"):
        # T30d: instantiate with the demo catalogue's first fixture clip as a placeholder
        # pick, instead of an empty path that made `instantiate()` refuse to build a
        # workflow at all (a 400 with nothing to show, no `provided.clip` node ever created
        # for the card/graph's in-node clip picker to edit). The in-node picker
        # (`nodes/ProvidedClipNode.tsx`) is exactly how the user swaps this placeholder for
        # their real pick from `GET .../provided-catalogue`; patching a node's params is
        # always allowed regardless of how it was first instantiated.
        spec_kwargs["path"] = DEMO_PROVIDED_CLIPS[0].path
    if recipe_id == "overlay":
        # T30b: the beat model's own overlay depth/position (T30a matrix) drives the
        # measure/cutout branch and the `overlay.place` node -- carried on the OVERLAY span,
        # not the picture span this recipe route is keyed off of, since a beat's picture and
        # overlay are independent Spans sharing anchors (model/cut.py's own docstring).
        overlay_span = next(
            (s for s in cut.spans if s.layer == "overlay" and s.start_anchor == span.start_anchor
             and s.end_anchor == span.end_anchor),
            None,
        )
        if overlay_span is not None and overlay_span.overlay_depth is not None:
            spec_kwargs["overlay_depth"] = overlay_span.overlay_depth
            spec_kwargs["overlay_position"] = overlay_span.overlay_position
    if recipe_id == "live_action":
        # The spoken words are NOT the picture. Until the brief-writing node has run, the
        # action slot is the editor's own direction if given, else a neutral placeholder;
        # raw transcript text (with its quotes) never enters an image prompt.
        spec_kwargs["action"] = span.note.strip() if span.note and span.note.strip() else "a scene that illustrates what is being said"
        spec_kwargs["include_end_frame"] = recommend_end_frame(span.brief.text or span.note or text)
    if recipe_id == "motion_graphic":
        spec_kwargs["words_text"] = text
        spec_kwargs["direction_note"] = span.direction_note
        spec_kwargs["writer_context"] = brand_mod.project_writer_context(root)
    span_spec = SpanSpec(**spec_kwargs)
    kit = _project_kit(root)

    try:
        workflow = instantiate(recipe_id, span_spec, kit, None, root)
    except CastNotReady as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        # `overlay`/`provided` with no `path` yet: leave the span unwired and let the card
        # tell the user to drop a clip first, rather than a 500.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    from post_core.cli.context import save_workflow

    save_workflow(root, workflow, expected_rev=0)

    new_span = span.model_copy(update={"workflow_id": workflow.id})
    new_spans = [new_span if s.id == span_id else s for s in cut.spans]
    new_cut = cut.model_copy(update={"spans": new_spans})
    store_module.write(root, "cut", new_cut, expected_rev=cut_rev)

    return SpanWorkflowOut(span_id=span.id, workflow_id=workflow.id, recipe_id=recipe_id)


class MoreVariantsRequest(BaseModel):
    count: int = 3


@router.post(
    "/cuts/{cut_id}/spans/{span_id}/workflow/more-variants", response_model=MoreVariantsOut,
)
def span_workflow_more_variants(
    cut_id: str, span_id: str, body: MoreVariantsRequest, root: Path = Depends(get_project_root),
) -> MoreVariantsOut:
    """T30b card action ("+3 more"): grow an already-instantiated `live_action` span's
    workflow with `body.count` more `still.generate` nodes sharing its existing pick node
    (`recipes.instantiate.add_more_stills`)."""
    cut, _cut_rev = store_module.read(root, "cut", cut_id)
    span = _find_span(cut, span_id)
    if not span.workflow_id:
        raise HTTPException(status_code=400, detail=f"span {span_id!r} has no workflow yet")

    text, seconds = _span_text_and_seconds(root, span)
    action = span.note.strip() if span.note and span.note.strip() else "a scene that illustrates what is being said"
    span_spec = SpanSpec(id=span.id, seconds=seconds, instruction=span.note or text, action=action)
    kit = _project_kit(root)

    workflow, revision = load_workflow(root, span.workflow_id)
    before_ids = {n.id for n in workflow.nodes}
    try:
        grown = add_more_stills(workflow, span_spec, kit, None, body.count)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    from post_core.cli.context import save_workflow

    new_rev = save_workflow(root, grown, expected_rev=revision)
    new_ids = [n.id for n in grown.nodes if n.id not in before_ids]
    return MoreVariantsOut(workflow_id=grown.id, node_ids=new_ids, revision=new_rev)


def _node_type_out(node_type) -> NodeTypeOut:
    return NodeTypeOut(
        id=node_type.id,
        kind=node_type.kind,
        inputs=[{"name": i.name, "type": i.type, "required": i.required, "many": i.many} for i in node_type.inputs],
        outputs=[{"name": o.name, "type": o.type} for o in node_type.outputs],
        spends=node_type.spends,
        lane=node_type.lane,
        uses_brand_kit=node_type.uses_brand_kit,
        params_schema=node_type.params_schema.model_json_schema(),
    )


@router.get("/node-registry", response_model=NodeRegistryOut)
def node_registry(pid: str, root: Path = Depends(get_project_root)) -> NodeRegistryOut:
    """Every node type the app can build a node from, the handle-type vocabulary
    `isValidConnection` checks edges against, and the model choices for the node types that
    expose a `model` param. T39: every image/video model `higgsfield model list` offers
    (cached in `.post3/`, refreshed by `POST .../models/refresh`), labelled with its display
    name; only the ones in `MODEL_OPTIONS` carry a price and capability chips."""
    registry = combined_registry()
    node_types = [_node_type_out(nt) for nt in registry.all()]
    handle_types = list(typing.get_args(HandleType))
    try:
        listed = model_list_mod.list_models(root)["models"]
    except Exception:  # noqa: BLE001 - no CLI / no network: the contracted models still show
        listed = [{"id": m, "label": m, "kind": "video" if t == "video.generate" else "image"}
                  for t, ids in MODEL_OPTIONS.items() for m in ids]
    models = model_options(listed)
    return NodeRegistryOut(node_types=node_types, handle_types=handle_types, models=models)


def model_options(listed: list[dict]) -> list[ModelOptionOut]:
    """Listed models -> picker options; pricing + chips from the contract of the ones Post3
    has priced (`MODEL_OPTIONS`), never a CLI call per listed model."""
    priced = {m for ids in MODEL_OPTIONS.values() for m in ids}
    endframe_models = set(MODEL_OPTIONS.get("endframe.generate", []))
    out: list[ModelOptionOut] = []
    seen: set[str] = set()
    for m in listed:
        if m["id"] in seen:
            continue
        seen.add(m["id"])
        pricing, capabilities = {}, []
        if m["id"] in priced:
            try:
                info = models_mod.model_get(m["id"])
                pricing = info.get("pricing", {})
                capabilities = models_mod.capabilities_for(info, offers_end_frame=m["id"] in endframe_models)
            except Exception:  # noqa: BLE001
                pass
        out.append(ModelOptionOut(id=m["id"], kind=m["kind"], label=m["label"], pricing=pricing,
                                  capabilities=capabilities))
    return out


# T30d: 3 fixed fake clips for the demo's "provided" clip-picker node (spec: "for the demo,
# seed 3 fake clips") -- not read off disk. A real `provided/` folder catalogue is future
# work (see docs/TASKS.md T30b follow-ups on `provided.clip`'s pre-existing gaps); this list
# only needs to be stable and pickable so the node's select has something real to choose.
DEMO_PROVIDED_CLIPS: list[ProvidedClipOut] = [
    ProvidedClipOut(path="provided/office-establishing.mp4", label="Office establishing shot", duration_seconds=6.0),
    ProvidedClipOut(path="provided/team-standup.mp4", label="Team standup", duration_seconds=9.5),
    ProvidedClipOut(path="provided/product-closeup.mp4", label="Product close-up", duration_seconds=4.0),
]


@router.get("/provided-catalogue", response_model=ProvidedCatalogueOut)
def provided_catalogue(pid: str) -> ProvidedCatalogueOut:
    """The project's `provided/` folder catalogue (T30 taxonomy: footage the editor
    supplies, not generated) -- fixture-backed for the demo per the task spec."""
    return ProvidedCatalogueOut(clips=DEMO_PROVIDED_CLIPS)


@router.get("/cast", response_model=CastListOut)
def cast_list(pid: str, root: Path = Depends(get_project_root)) -> CastListOut:
    """The project's cast registry (T12), with each entry's continuity-anchor readiness --
    feeds the graph's `character` node picker (T30d)."""
    entries = cast_mod.list_cast(root)
    return CastListOut(cast=[
        CastEntryOut(
            id=e.id, name=e.name, kind=e.kind, description=e.description,
            anchor_ready=cast_mod.anchor_ready(root, e.name), anchor_asset_path=e.anchor_asset_path,
        )
        for e in entries
    ])


class CastCreateIn(BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    kind: str = "character"
    description: str = ""


@router.post("/cast", response_model=CastEntryOut)
def cast_create(pid: str, body: CastCreateIn, root: Path = Depends(get_project_root)) -> CastEntryOut:
    """No cast-authoring UI exists yet (T12's own scope) -- this exists so the graph's
    `character` node picker (T30d) and its e2e have a real entry to reference; a full cast
    registry UI is future work."""
    from post_core.model.cast import CastEntry

    entry = CastEntry(name=body.name, kind=body.kind, description=body.description)  # type: ignore[arg-type]
    cast_mod.upsert_cast(root, entry)
    return CastEntryOut(id=entry.id, name=entry.name, kind=entry.kind, description=entry.description, anchor_ready=False)


@router.get("/workflows/{workflow_id}/nodes/{node_id}/artifact")
def node_artifact(pid: str, workflow_id: str, node_id: str, root: Path = Depends(get_project_root)) -> dict:
    """A node's current artifact (if it has ever run and passed its check), as
    `{sha256, url, ...extra-manifest-fields}` per output -- `url` points at the existing
    content-addressed `/assets/{sha256}` route, so a card/graph-view thumbnail or clip
    player never needs to know an artifact directory's on-disk layout."""
    workflow, _rev = load_workflow(root, workflow_id)
    registry = combined_registry()
    node = workflow.node(node_id)  # KeyError -> 400
    node_hash = compute_hashes(workflow, registry).get(node_id)
    if node_hash is None:
        return {"exists": False, "outputs": [], "cost": None}
    directory = artifact_dir(root, node.type_id, node_hash)
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        return {"exists": False, "outputs": [], "cost": None}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    outputs = [
        {**o, "url": f"/api/projects/{pid}/assets/{o['sha256']}"}
        for o in manifest.get("outputs", []) if o.get("sha256")
    ]
    return {"exists": True, "outputs": outputs, "cost": manifest.get("cost"), "content_hash": node_hash}


__all__ = ["router"]
