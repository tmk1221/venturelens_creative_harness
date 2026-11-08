"""T12 real compute node types: params schemas, wiring, cost, and (for `animation.design`)
a brand-lint check -- wrapping today's generators (Higgsfield stills/video, HyperFrames
animation) as T03-contract workers. `instantiate.py` builds concrete `Node`s carrying these
types' ids; `recipes/workers/*.py` are the subprocesses `recipes.cmd_for.make_cmd_for`
launches (see that module for why the argv is built dynamically at enqueue time rather than
stored in a node's own params).

Every `spends` node type's `estimate_cost` calls `recipes.models.estimate_cost`, which is
fixture-backed under `POST3_FAKE_PROVIDERS=1` (every test) and never shells out in that
mode -- see `models.py`'s docstring for the one place a real-CLI assumption lives.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..graph.types import ANY_TYPE, Cost, InputSpec, NodeType, NoParams, OutputSpec
from ..model.cut import OverlayDepth, OverlayPosition
from . import models

# ---- shared param bits ---------------------------------------------------------------
#
# Params here hold only JSON-scalar, upstream-independent data (prompt text, model ids,
# durations...) -- never a worker argv. A node's argv (`recipes.cmd_for.make_cmd_for`) is
# built dynamically at *enqueue* time, not baked in at instantiate time: a node downstream
# of a `human.pick` (e.g. `motion.from_frame`'s start frame) only has a resolvable upstream
# artifact path once the pick is made, which is after the workflow is built -- so params
# must stay self-contained and `cmd_for` resolves upstream file paths itself, from
# `graph.hashing.compute_hashes` + `graph.state.artifact_dir`, at the moment each node
# actually becomes runnable.


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BriefWriteParams(_Params):
    instruction: str
    # T30b: extra context the fake-mode writer composes into a plausible brief (all optional
    # so the T12 motion_graphic recipe, which only ever set `instruction`, keeps working
    # unchanged). Real mode still only needs `instruction` (`_run_agent` is unwired anyway).
    words_text: str = ""
    direction_note: str = ""
    writer_context: dict = Field(default_factory=dict)


class StillGenerateParams(_Params):
    model: str = "nano_banana_2"
    aspect: str = "16:9"
    count: int = 1
    variant_index: int = 0
    prompt_text: str
    style_block_version: Optional[str] = None
    style_block_hash: Optional[str] = None


class MotionFromFrameParams(_Params):
    kit_dir: str
    look_path: Optional[str] = None
    subject_motion_hint: str
    static_hint: str
    camera: Optional[str] = None
    pacing: Optional[str] = None


class EndframeGenerateParams(_Params):
    model: str = "nano_banana_2"
    aspect: str = "16:9"
    prompt_text: str


class VideoGenerateParams(_Params):
    model: str = "kling3_0"
    aspect: str = "16:9"
    mode: str = "pro"
    sound: bool = True
    duration: int  # seconds, = ceil(span seconds) + 1 -- see instantiate.py
    # T37: `aspect` is what the model is asked for; `crop_to` (the cut's aspect, set only when
    # the model doesn't offer it) is centre-cropped locally after download. `fps` is the
    # project's rate ("24000/1001"): fake mode renders at it; a real provider picks its own.
    crop_to: Optional[str] = None
    fps: Optional[str] = None
    # No `motion_prompt` field: the text comes from the upstream `motion.from_frame` node
    # (`cmd_for` reads its artifact file at enqueue time) -- its own edge already makes
    # video.generate's input_hash depend on that text, so duplicating it here would only
    # let params and the real upstream content drift out of sync.


class AnimationDesignParams(_Params):
    kit_dir: str
    look_path: Optional[str] = None
    brief_extra: dict = Field(default_factory=dict)


class AnimationRenderParams(_Params):
    width: int = 1920
    height: int = 1080
    fps: int = 30
    draft: bool = False


class OverlayMeasureParams(_Params):
    pass


class OverlayCutoutParams(_Params):
    pass


class ProvidedClipParams(_Params):
    """`kind="compute"` (not `"source"`): T04's `source` kind has no code path that ever
    marks one `done` (`queue.enqueue` only enqueues `compute` nodes; nothing else writes a
    source node's manifest) -- treating already-ingested footage as a trivial, always-
    passing compute job sidesteps that gap instead of half-fixing shared T04 infra as a
    T12 side effect. Its worker never moves/copies the referenced footage (AGENTS.md: never
    mutate live footage); it only probes it and writes its own small pointer artifact plus
    an Asset record naming the *original* path.

    No `record_as_node`/`record_as_hash` here (would be circular: this node's own params
    feed its own input_hash, which the downstream `human.approve` node's hash is derived
    from -- a param can't name a hash that depends on itself). `cmd_for.py` resolves the
    downstream approve node's id/hash dynamically at enqueue time instead."""

    path: str
    in_seconds: float = 0.0
    out_seconds: Optional[float] = None
    role: str = "picture"


class OverlayPlaceParams(_Params):
    """`overlay.place`: no media transform of its own -- it tags an already-produced overlay
    candidate with the depth/position the beat's Span carries (T30 taxonomy), so changing
    either one gives the node a new `input_hash` and marks everything downstream (`asset.
    verify`, `human.approve`) stale, per T30b's spec line. `_build_overlay` wires it
    downstream of `overlay.cutout` when `depth == "behind"`, or directly downstream of
    `provided.clip` when `depth == "in_front"` (no cutout needed -- nothing to matte out
    from under)."""

    depth: OverlayDepth
    position: OverlayPosition


class ArollRegenerateParams(_Params):
    """`aroll.regenerate` (T15 stub, T30b spec line): the request itself. No generation
    happens yet -- this just records what a future A-roll regen job would need (mode +
    instruction) so the `consent.gate` node downstream has something to gate."""

    mode: Literal["fix_line", "alternate_opening", "synthetic_segment"]
    instruction: str = ""


class AssetVerifyParams(_Params):
    """See `ProvidedClipParams`' docstring for why there's no `record_as_node`/
    `record_as_hash` param here either."""

    expect_kind: str = "video"  # "video" | "image"
    min_width: int = 0
    min_height: int = 0
    role: str = "picture"
    # T37 render contract (`recipes.render_contract`; unset skips a check): the project's fps,
    # at least the span's length, the cut's aspect, and -- when `allow_hold` is False, as
    # live_action sets it unless the brief asks for one -- no frozen last 0.5 s.
    expect_fps: Optional[str] = None
    min_seconds: Optional[float] = None
    expect_aspect: Optional[str] = None
    allow_hold: bool = True


# ---- cost -------------------------------------------------------------------------


def _still_cost(params: StillGenerateParams) -> Optional[Cost]:
    return models.estimate_still(params.model, params.aspect)


def _endframe_cost(params: EndframeGenerateParams) -> Optional[Cost]:
    return models.estimate_still(params.model, params.aspect)


def _video_cost(params: VideoGenerateParams) -> Optional[Cost]:
    return models.estimate_video(params.model, params.duration, params.mode)


# ---- check --------------------------------------------------------------------------


def _default_check(directory: Path) -> bool:
    return (directory / "manifest.json").is_file()


def _asset_verify_check(directory: Path) -> bool:
    """`asset.verify` additionally requires the probe to have passed (its worker writes
    `verify.json` with `{"ok": bool, ...}` alongside the usual manifest -- a worker that
    fails the probe exits non-zero instead, per the T03 contract, so this is mostly belt
    and braces for a verify.json left behind by an older, looser worker version)."""
    if not _default_check(directory):
        return False
    verify_path = directory / "verify.json"
    if not verify_path.is_file():
        return True
    import json

    try:
        data = json.loads(verify_path.read_text(encoding="utf-8"))
    except ValueError:
        return False
    return bool(data.get("ok", True))


# ---- node types -----------------------------------------------------------------------

BRIEF_WRITE = NodeType(
    id="brief.write",
    kind="compute",
    inputs=(InputSpec(name="context", type="text", required=False, many=False),),
    outputs=(OutputSpec(name="text", type="text"),),
    params_schema=BriefWriteParams,
    lane="design",
)

STILL_GENERATE = NodeType(
    id="still.generate",
    kind="compute",
    # No wired "prompt" input: `prompt_text` is a static param, built directly from
    # `brandkit` at instantiate time (it has no upstream node dependency) -- a `text.prompt`
    # source-node edge would work for hashing (`graph.hashing` doesn't care about `kind`)
    # but never for readiness: `graph.state.compute_states` requires every upstream node to
    # reach `DONE`, and nothing in T02-T11 ever marks a `kind="source"` node `done` (`queue.
    # enqueue` only enqueues `compute` nodes) -- a real gap in shared T04 infra, out of
    # scope to fix here (see `ProvidedClipParams`' docstring for the same reasoning).
    inputs=(InputSpec(name="continuity", type="image", required=False, many=True),),
    outputs=(OutputSpec(name="image", type="image"),),
    params_schema=StillGenerateParams,
    spends=True,
    lane="remote",
    uses_brand_kit=True,
    estimate_cost=_still_cost,
)

MOTION_FROM_FRAME = NodeType(
    id="motion.from_frame",
    kind="compute",
    inputs=(InputSpec(name="frame", type="image", required=True, many=False),),
    outputs=(OutputSpec(name="prompt", type="prompt"),),
    params_schema=MotionFromFrameParams,
    lane="design",
    uses_brand_kit=True,
)

ENDFRAME_GENERATE = NodeType(
    id="endframe.generate",
    kind="compute",
    inputs=(InputSpec(name="frame", type="image", required=True, many=False),),
    outputs=(OutputSpec(name="image", type="image"),),
    params_schema=EndframeGenerateParams,
    spends=True,
    lane="remote",
    uses_brand_kit=True,
    estimate_cost=_endframe_cost,
)

VIDEO_GENERATE = NodeType(
    id="video.generate",
    kind="compute",
    inputs=(
        InputSpec(name="start_image", type="image", required=True, many=False),
        InputSpec(name="end_image", type="image", required=False, many=False),
        InputSpec(name="motion_prompt", type="prompt", required=True, many=False),
    ),
    outputs=(OutputSpec(name="video", type="video"),),
    params_schema=VideoGenerateParams,
    spends=True,
    lane="remote",
    estimate_cost=_video_cost,
)

ANIMATION_DESIGN = NodeType(
    id="animation.design",
    kind="compute",
    inputs=(InputSpec(name="brief", type="text", required=False, many=False),),
    outputs=(OutputSpec(name="composition", type="text"),),
    params_schema=AnimationDesignParams,
    lane="design",
    uses_brand_kit=True,
)

ANIMATION_DRAFT_RENDER = NodeType(
    id="animation.draft_render",
    kind="compute",
    inputs=(InputSpec(name="composition", type="text", required=True, many=False),),
    outputs=(OutputSpec(name="video", type="video"),),
    params_schema=AnimationRenderParams,
    lane="render",
    resources=("hyperframes_render",),
)

ANIMATION_RENDER = NodeType(
    id="animation.render",
    kind="compute",
    inputs=(InputSpec(name="composition", type="text", required=True, many=False),),
    outputs=(OutputSpec(name="video", type="video"),),
    params_schema=AnimationRenderParams,
    lane="render",
    resources=("hyperframes_render",),
)

OVERLAY_MEASURE = NodeType(
    id="overlay.measure",
    kind="compute",
    inputs=(InputSpec(name="video", type="video", required=True, many=False),),
    outputs=(OutputSpec(name="measurements", type="text"),),
    params_schema=OverlayMeasureParams,
    # Measuring one clip at a time (T18 gave `graph.lanes` a "default" lane, limit 2).
    lane="single",
)

OVERLAY_CUTOUT = NodeType(
    id="overlay.cutout",
    kind="compute",
    inputs=(InputSpec(name="video", type="video", required=True, many=False),),
    outputs=(OutputSpec(name="video", type="video"),),
    params_schema=OverlayCutoutParams,
    lane="single",
)

OVERLAY_PLACE = NodeType(
    id="overlay.place",
    kind="compute",
    inputs=(InputSpec(name="video", type="video", required=True, many=False),),
    outputs=(OutputSpec(name="video", type="video"),),
    params_schema=OverlayPlaceParams,
    lane="single",
)

AROLL_REGENERATE = NodeType(
    id="aroll.regenerate",
    kind="compute",
    inputs=(),
    outputs=(OutputSpec(name="request", type="text"),),
    params_schema=ArollRegenerateParams,
    lane="design",
)

# `consent.gate` re-uses the "approve" kind's own state derivation (NEEDS_APPROVAL/DONE, via
# `graph.approvals`) -- its own name (not a plain `human.approve`) is what lets `plan()`/
# `decisions.py` label the row distinctly ("waiting on consent", not "waiting on approval").
# `recipes.consent.has_consent` + `instantiate._build_aroll_regenerate` pre-approve its hash
# automatically once a project has a consent record on disk, so a human never has to click an
# explicit approve button for it if consent was already granted.
CONSENT_GATE = NodeType(
    id="consent.gate",
    kind="approve",
    inputs=(InputSpec(name="subject", type="any", required=True, many=False),),
    outputs=(OutputSpec(name="approved", type="any"),),
    params_schema=NoParams,
)

PROVIDED_CLIP = NodeType(
    id="provided.clip",
    kind="compute",
    inputs=(),
    outputs=(OutputSpec(name="video", type=ANY_TYPE),),
    params_schema=ProvidedClipParams,
    lane="single",
)

ASSET_VERIFY = NodeType(
    id="asset.verify",
    kind="compute",
    # "any" (not "video"): asset.verify probes both generated video and generated stills
    # (`expect_kind` param tells the worker which ffprobe expectations to enforce).
    inputs=(InputSpec(name="media", type=ANY_TYPE, required=True, many=False),),
    outputs=(OutputSpec(name="media", type=ANY_TYPE),),
    params_schema=AssetVerifyParams,
    check=_asset_verify_check,
    lane="single",
)

RECIPE_NODE_TYPES = (
    BRIEF_WRITE, STILL_GENERATE, MOTION_FROM_FRAME, ENDFRAME_GENERATE, VIDEO_GENERATE,
    ANIMATION_DESIGN, ANIMATION_DRAFT_RENDER, ANIMATION_RENDER, OVERLAY_MEASURE,
    OVERLAY_CUTOUT, OVERLAY_PLACE, AROLL_REGENERATE, CONSENT_GATE, PROVIDED_CLIP,
    ASSET_VERIFY,
)

__all__ = [
    "RECIPE_NODE_TYPES",
    "BriefWriteParams", "StillGenerateParams", "MotionFromFrameParams",
    "EndframeGenerateParams", "VideoGenerateParams", "AnimationDesignParams",
    "AnimationRenderParams", "OverlayMeasureParams", "OverlayCutoutParams",
    "OverlayPlaceParams", "ArollRegenerateParams", "ProvidedClipParams", "AssetVerifyParams",
    "BRIEF_WRITE", "STILL_GENERATE", "MOTION_FROM_FRAME", "ENDFRAME_GENERATE",
    "VIDEO_GENERATE", "ANIMATION_DESIGN", "ANIMATION_DRAFT_RENDER", "ANIMATION_RENDER",
    "OVERLAY_MEASURE", "OVERLAY_CUTOUT", "OVERLAY_PLACE", "AROLL_REGENERATE",
    "CONSENT_GATE", "PROVIDED_CLIP", "ASSET_VERIFY",
]
