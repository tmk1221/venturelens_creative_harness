"""`instantiate(recipe_id, span, kit, look, project_root)`: compile a `templates/*.json`
recipe (metadata: `exposed` params, `human_gates`) into a concrete `graph.workflow.Workflow`
for one beat/span, per T12 spec. Prompt text is computed here (via `recipes.prompts`, so it
enters each node's params -- and therefore its `input_hash` -- as real content, keeping
`graph.hashing` a pure function of the workflow alone) and cast continuity is checked here
(via `recipes.cast.anchor_ready`) before any node is built, per module `SpanSpec` below.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from brandkit.look import Look
from brandkit.schema import BrandKit

from ..graph.registry import SourceFileParams
from ..graph.workflow import Edge, Node, Workflow
from ..model.cut import OverlayDepth, OverlayPosition
from . import cast as cast_mod
from . import node_types as nt
from .instantiate_extra import add_more_stills  # re-exported for callers' convenience
from .instantiate_extra import beat_aspects
from .prompts import build_still_prompt

TEMPLATES_DIR = Path(__file__).with_name("templates")


class CastNotReady(ValueError):
    """A span names cast members with no approved continuity anchor yet -- instantiate
    refuses to build a runnable graph for that beat until they exist (T12 spec: "a beat
    using 'Dave' before Dave has an approved anchor is blocked on that beat's pick")."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(f"cast anchor(s) not ready: {', '.join(missing)}")


@dataclass
class SpanSpec:
    """Everything one beat's recipe needs that isn't the kit/look: content slots (for
    `still_prompt`/`motion_prompt`), timing, and cast/variant/source config. Deliberately
    not `model.cut.Span` -- that's word-anchored Cut state; this is graph-instantiation
    input, decoupled from the Cut/timeline math (`export._spans`) so recipes can be built
    and tested without a full Cut/Transcript fixture."""

    id: str
    seconds: float = 4.0
    shot_type: str = "Medium shot"
    subject: str = "a person"
    action: str = "working"
    setting: str = "an office"
    subject_motion: str = "leans forward slightly"
    static: str = "background stays still"
    camera: Optional[str] = None
    pacing: Optional[str] = None
    negatives: list[str] = field(default_factory=list)
    continuity_names: list[str] = field(default_factory=list)
    variants: int = 3
    instruction: str = ""
    # Test-only escape hatch, threaded through to `animation.design`'s
    # `params.brief_extra["raw_css_injection"]` -- see that worker's docstring.
    raw_css_injection: str = ""
    path: Optional[str] = None
    in_seconds: float = 0.0
    out_seconds: Optional[float] = None
    # T30b: overlay depth/position (only read by the "overlay" recipe -- the matrix itself
    # lives in `model.cut.valid_overlay_positions`; instantiate doesn't re-check it here,
    # `Cut`'s own validator is the source of truth once the Span exists).
    overlay_depth: OverlayDepth = "in_front"
    overlay_position: OverlayPosition = "lower-band"
    # T30b: end frame is optional on the live_action recipe -- `recipes.prompts.
    # recommend_end_frame` gives callers a brief-driven default, but the caller decides.
    include_end_frame: bool = False
    end_frame_prompt: str = ""
    # T30b: another beat's *picked* frame this beat's stills continue from (a `continuity`
    # edge, cast-style) -- resolved by the caller (e.g. `post_api`'s span-workflow route, via
    # `cmd_for.resolve_pick_path` against the referenced beat's own workflow) into a literal
    # file path, kept decoupled from other workflows the same way `SpanSpec` always has been.
    continuity_source_path: Optional[str] = None
    # T30b: `brief.write` fake-mode context (words + direction + brand writer_context) --
    # only `motion_graphic`/aroll-regen callers that want a plausible fake brief need to set
    # these; the plain `instruction` alone still works exactly as it did in T12.
    words_text: str = ""
    direction_note: str = ""
    writer_context: dict = field(default_factory=dict)
    # T30b: `aroll_regenerate` recipe only.
    regen_mode: str = "fix_line"
    # T37: from the span's cut. `aspect` ("4:5") is what the beat is generated for
    # (`instantiate_extra.beat_aspects`), `fps` ("24000/1001") the rate `asset.verify` holds
    # generated video to (unset: unchecked), `hold_ok` lets a brief asking for a held last
    # frame pass the frozen-tail check.
    aspect: str = "16:9"
    fps: Optional[str] = None
    hold_ok: bool = False


def load_template(recipe_id: str) -> dict:
    path = TEMPLATES_DIR / f"{recipe_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _check_cast(project_root: str | Path, span: SpanSpec) -> None:
    missing = [n for n in span.continuity_names if not cast_mod.anchor_ready(project_root, n)]
    if missing:
        raise CastNotReady(missing)


def instantiate(
    recipe_id: str, span: SpanSpec, kit: BrandKit, look: Optional[Look], project_root: str | Path,
) -> Workflow:
    load_template(recipe_id)  # validates the recipe_id exists; metadata itself is UI-facing
    _check_cast(project_root, span)
    from .instantiate_extra import build_aroll_regenerate

    builder = {
        "live_action": _build_live_action,
        "motion_graphic": _build_motion_graphic,
        "overlay": _build_overlay,
        "provided": _build_provided,
        "aroll_regenerate": build_aroll_regenerate,
    }.get(recipe_id)
    if builder is None:
        raise ValueError(f"instantiate: unknown recipe_id {recipe_id!r}")
    nodes, edges = builder(span, kit, look)
    workflow = Workflow(recipe_id=recipe_id, brand_kit_hash=kit.kit_hash(), nodes=nodes, edges=edges)
    if recipe_id == "aroll_regenerate":
        from .instantiate_extra import maybe_preapprove_consent

        maybe_preapprove_consent(workflow, project_root)
    return workflow


def _edge(nid: str, from_node: str, from_output: str, to_node: str, to_input: str) -> Edge:
    return Edge(id=nid, from_node=from_node, from_output=from_output, to_node=to_node, to_input=to_input)


def _params(model_cls, **kwargs) -> dict:
    """Build a node's `params` dict through its own pydantic schema (`model_dump`) rather
    than a raw literal -- every field lands with its schema default filled in, so
    `cmd_for.py` can always read e.g. `params['model']` without a `KeyError`, and two nodes
    that differ only in an unset-vs-explicit-default field still hash identically."""
    return model_cls(**kwargs).model_dump(mode="json")


def _add_still_variants(
    nodes: list[Node], bid: str, still_result, count: int, start_index: int, out_ids: list[str],
    aspect: str = "16:9",
) -> None:
    """Append `count` `still.generate` nodes (ids `{bid}-still{start_index}..`) sharing one
    prompt/style block, appending their ids to `out_ids` in place -- callers wire the edges
    into the beat's `human.pick` node themselves, so the same helper builds both a beat's
    initial variant batch and a later "+3 more" batch (`add_more_stills`) sharing that pick."""
    for i in range(count):
        v = start_index + i
        sid = f"{bid}-still{v}"
        out_ids.append(sid)
        nodes.append(Node(id=sid, type_id="still.generate", params=_params(
            nt.StillGenerateParams, prompt_text=still_result.text, count=count, variant_index=v, aspect=aspect,
            style_block_version=still_result.style_block_version, style_block_hash=still_result.style_block_hash,
        )))


def _build_live_action(span: SpanSpec, kit: BrandKit, look: Optional[Look]) -> tuple[list[Node], list[Edge]]:
    bid = span.id
    still_result = build_still_prompt(
        {"shot_type": span.shot_type, "subject": span.subject, "action": span.action,
         "setting": span.setting, "negatives": span.negatives},
        kit, look,
    )
    nodes: list[Node] = []
    edges: list[Edge] = []
    aspects = beat_aspects(span.aspect)

    still_ids: list[str] = []
    _add_still_variants(nodes, bid, still_result, max(1, span.variants), 0, still_ids, aspect=aspects.still)

    pick_id = f"{bid}-pick"
    nodes.append(Node(id=pick_id, type_id="human.pick"))
    for i, sid in enumerate(still_ids):
        edges.append(_edge(f"{bid}-e-still{i}", sid, "image", pick_id, "options"))

    # T30b: another beat's *picked* frame feeds this beat's stills as an extra continuity
    # reference (a cross-beat `continuity_of_span_id` edge, cast-style) -- a literal resolved
    # path, not a live edge into another Workflow (see `SpanSpec.continuity_source_path`'s
    # docstring for why).
    if span.continuity_source_path:
        cont_id = f"{bid}-continuity-source"
        nodes.append(Node(id=cont_id, type_id="source.file", params=_params(
            SourceFileParams, path=span.continuity_source_path, handle_type="image",
        )))
        for sid in still_ids:
            edges.append(_edge(f"{bid}-e-cont-{sid}", cont_id, "file", sid, "continuity"))

    motion_id = f"{bid}-motion"
    nodes.append(Node(id=motion_id, type_id="motion.from_frame", params=_params(
        nt.MotionFromFrameParams, kit_dir=str(kit.path), look_path=None,
        subject_motion_hint=span.subject_motion, static_hint=span.static,
        camera=span.camera, pacing=span.pacing,
    )))
    edges.append(_edge(f"{bid}-e-frame", pick_id, "chosen", motion_id, "frame"))

    end_image_id: Optional[str] = None
    if span.include_end_frame:
        end_image_id = f"{bid}-endframe"
        nodes.append(Node(id=end_image_id, type_id="endframe.generate", params=_params(
            nt.EndframeGenerateParams, prompt_text=span.end_frame_prompt or still_result.text,
            aspect=aspects.still,
        )))
        edges.append(_edge(f"{bid}-e-endframe", pick_id, "chosen", end_image_id, "frame"))

    video_id = f"{bid}-video"
    nodes.append(Node(id=video_id, type_id="video.generate", params=_params(
        nt.VideoGenerateParams, duration=math.ceil(span.seconds) + 1,
        aspect=aspects.video, crop_to=aspects.crop_to, fps=span.fps,
    )))
    edges.append(_edge(f"{bid}-e-start", pick_id, "chosen", video_id, "start_image"))
    edges.append(_edge(f"{bid}-e-motion", motion_id, "prompt", video_id, "motion_prompt"))
    if end_image_id is not None:
        edges.append(_edge(f"{bid}-e-end", end_image_id, "image", video_id, "end_image"))

    verify_id = f"{bid}-verify"
    nodes.append(Node(id=verify_id, type_id="asset.verify", params=_params(
        nt.AssetVerifyParams, expect_kind="video", role="picture", expect_fps=span.fps,
        min_seconds=span.seconds, expect_aspect=aspects.crop_to or span.aspect, allow_hold=span.hold_ok,
    )))
    edges.append(_edge(f"{bid}-e-verify", video_id, "video", verify_id, "media"))

    approve_id = f"{bid}-approve"
    nodes.append(Node(id=approve_id, type_id="human.approve"))
    edges.append(_edge(f"{bid}-e-approve", verify_id, "media", approve_id, "subject"))

    return nodes, edges


def _build_motion_graphic(span: SpanSpec, kit: BrandKit, look: Optional[Look]) -> tuple[list[Node], list[Edge]]:
    bid = span.id
    nodes: list[Node] = []
    edges: list[Edge] = []

    brief_id = f"{bid}-brief"
    nodes.append(Node(id=brief_id, type_id="brief.write", params=_params(
        nt.BriefWriteParams, instruction=span.instruction, words_text=span.words_text,
        direction_note=span.direction_note, writer_context=span.writer_context,
    )))

    design_id = f"{bid}-design"
    brief_extra = {"beat": bid}
    if span.raw_css_injection:
        brief_extra["raw_css_injection"] = span.raw_css_injection
    nodes.append(Node(id=design_id, type_id="animation.design", params=_params(
        nt.AnimationDesignParams, kit_dir=str(kit.path), look_path=None, brief_extra=brief_extra,
    )))
    edges.append(_edge(f"{bid}-e-brief", brief_id, "text", design_id, "brief"))

    draft_id = f"{bid}-draft"
    nodes.append(Node(id=draft_id, type_id="animation.draft_render", params=_params(
        nt.AnimationRenderParams, draft=True,
    )))
    edges.append(_edge(f"{bid}-e-draft", design_id, "composition", draft_id, "composition"))

    approve_draft_id = f"{bid}-approve-draft"
    nodes.append(Node(id=approve_draft_id, type_id="human.approve"))
    edges.append(_edge(f"{bid}-e-approve-draft", draft_id, "video", approve_draft_id, "subject"))

    render_id = f"{bid}-render"
    nodes.append(Node(id=render_id, type_id="animation.render", params=_params(nt.AnimationRenderParams)))
    edges.append(_edge(f"{bid}-e-render", design_id, "composition", render_id, "composition"))

    verify_id = f"{bid}-verify"
    nodes.append(Node(id=verify_id, type_id="asset.verify", params=_params(
        nt.AssetVerifyParams, expect_kind="video", role="overlay",
    )))
    edges.append(_edge(f"{bid}-e-verify", render_id, "video", verify_id, "media"))

    approve_final_id = f"{bid}-approve-final"
    nodes.append(Node(id=approve_final_id, type_id="human.approve"))
    edges.append(_edge(f"{bid}-e-approve-final", verify_id, "media", approve_final_id, "subject"))

    return nodes, edges


def _build_overlay(span: SpanSpec, kit: BrandKit, look: Optional[Look]) -> tuple[list[Node], list[Edge]]:
    """T30b: gains an `overlay.place` node carrying depth/position (spec: "change ⇒
    downstream stale" -- true for free, since `place` sits between the measure/cutout branch
    and `asset.verify`/`human.approve`, so its own `input_hash` -- which depends on its
    params -- is what everything downstream hashes off). `overlay.measure`/`overlay.cutout`
    only run when `depth == "behind"` (there's a subject to cut out from under); `in_front`
    wires `provided.clip` straight into `place`, per the T30 taxonomy's own note that
    `behind` is only meaningful over `aroll`."""
    bid = span.id
    if not span.path:
        raise ValueError("overlay recipe requires span.path (an overlay candidate to measure/cut out)")
    nodes: list[Node] = []
    edges: list[Edge] = []

    provided_id = f"{bid}-provided"
    nodes.append(Node(id=provided_id, type_id="provided.clip", params=_params(
        nt.ProvidedClipParams, path=span.path, in_seconds=span.in_seconds,
        out_seconds=span.out_seconds, role="overlay",
    )))

    place_input_id = provided_id
    if span.overlay_depth == "behind":
        measure_id = f"{bid}-measure"
        nodes.append(Node(id=measure_id, type_id="overlay.measure", params=_params(nt.OverlayMeasureParams)))
        edges.append(_edge(f"{bid}-e-measure", provided_id, "video", measure_id, "video"))

        cutout_id = f"{bid}-cutout"
        nodes.append(Node(id=cutout_id, type_id="overlay.cutout", params=_params(nt.OverlayCutoutParams)))
        edges.append(_edge(f"{bid}-e-cutout", provided_id, "video", cutout_id, "video"))
        place_input_id = cutout_id

    place_id = f"{bid}-place"
    nodes.append(Node(id=place_id, type_id="overlay.place", params=_params(
        nt.OverlayPlaceParams, depth=span.overlay_depth, position=span.overlay_position,
    )))
    edges.append(_edge(f"{bid}-e-place", place_input_id, "video", place_id, "video"))

    verify_id = f"{bid}-verify"
    nodes.append(Node(id=verify_id, type_id="asset.verify", params=_params(
        nt.AssetVerifyParams, expect_kind="video", role="overlay",
    )))
    edges.append(_edge(f"{bid}-e-verify", place_id, "video", verify_id, "media"))

    approve_id = f"{bid}-approve"
    nodes.append(Node(id=approve_id, type_id="human.approve"))
    edges.append(_edge(f"{bid}-e-approve", verify_id, "media", approve_id, "subject"))

    return nodes, edges


def _build_provided(span: SpanSpec, kit: BrandKit, look: Optional[Look]) -> tuple[list[Node], list[Edge]]:
    bid = span.id
    if not span.path:
        raise ValueError("provided recipe requires span.path")
    nodes = [Node(id=f"{bid}-provided", type_id="provided.clip", params=_params(
        nt.ProvidedClipParams, path=span.path, in_seconds=span.in_seconds,
        out_seconds=span.out_seconds, role="picture",
    ))]
    approve_id = f"{bid}-approve"
    nodes.append(Node(id=approve_id, type_id="human.approve"))
    edges = [_edge(f"{bid}-e-approve", f"{bid}-provided", "video", approve_id, "subject")]
    return nodes, edges


__all__ = ["instantiate", "SpanSpec", "CastNotReady", "load_template", "add_more_stills"]
