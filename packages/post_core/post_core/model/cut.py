"""Cut: an edit — sections of passages (picture) plus spans (picture/overlay/audio layers).

T30 beat model: a beat is one word-anchored region expressed as up to two `Span`s sharing
the same `(start_anchor, end_anchor)` -- a `layer="picture"` span (required) and an optional
`layer="overlay"` span. They're independent entities (not a nested struct) so the existing
`Layer`/`workflow_id`/`orphaned` machinery keeps working unchanged; `Cut`'s validators below
enforce the depth/position matrix across the pair.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field, field_validator, model_validator

from .base import Entity, Value
from .common import Rational, WordAnchor

DEFAULT_FPS = Rational(num=24000, den=1001)

Layer = Literal["picture", "overlay", "audio"]
Provenance = Literal["human", "agent"]

# ---- T30 taxonomy -----------------------------------------------------------------------

PictureKind = Literal["aroll", "provided", "live_action", "motion_graphic"]
OverlayDepth = Literal["in_front", "behind"]
OverlayPosition = Literal["right", "left", "lower-band", "full-frame", "center", "full-width"]
BeatFlag = Literal["must_have_shot", "presenter_stays_on_camera", "picture_must_match_words"]

PICTURE_KINDS: tuple[str, ...] = ("aroll", "provided", "live_action", "motion_graphic")

_AROLL_POSITIONS: dict[str, frozenset[str]] = {
    "in_front": frozenset({"right", "left", "lower-band"}),
    "behind": frozenset({"right", "left", "full-frame"}),
}
_BROLL_POSITIONS: dict[str, frozenset[str]] = {
    "in_front": frozenset({"right", "left", "lower-band", "center", "full-width"}),
}
_SWAP_PAIRS: dict[str, str] = {"lower-band": "full-frame", "full-frame": "lower-band"}


def valid_overlay_positions(picture_kind: str, depth: str) -> frozenset[str]:
    """The legal overlay positions for `depth` given the picture layer it sits over.
    `behind` is only meaningful over `aroll` (there has to be a subject to cut the overlay
    out from under) -- any other picture kind has no legal `behind` position at all."""
    if depth == "behind":
        return _AROLL_POSITIONS["behind"] if picture_kind == "aroll" else frozenset()
    if picture_kind == "aroll":
        return _AROLL_POSITIONS["in_front"]
    return _BROLL_POSITIONS["in_front"]


def swap_position_for_depth_change(position: str, picture_kind: str) -> str:
    """Old app's swap rule (`story_board.py:48-55`): flipping overlay depth swaps
    `lower-band` <-> `full-frame` instead of leaving a position that's illegal in the new
    depth. A no-op for positions that don't participate in the swap (`right`/`left`/
    `center`/`full-width` are legal — where applicable — on both sides)."""
    if picture_kind != "aroll":
        return position
    return _SWAP_PAIRS.get(position, position)


class Trim(Value):
    """Extra trim applied at the head/tail of a Passage's word range, in seconds."""

    head: float = 0.0
    tail: float = 0.0


class Passage(Entity):
    """A run of words from one SyncGroup, played back through one angle (Source)."""

    sync_group_id: str
    start_word_id: str
    end_word_id: str
    trims: Trim = Trim()
    angle_source_id: str
    framing: Optional[dict] = None


class Brief(Value):
    """What the viewer sees, in words -- human-typed or agent-drafted (`brief.write` in
    fake mode). Distinct from `Span.note`, which is a regenerate instruction, not the brief
    itself."""

    text: str = ""
    provenance: Provenance = "human"


class Span(Entity):
    """A word-anchored region on one layer: picture (B-roll), overlay, or audio.

    A beat pairs a `layer="picture"` span with an optional `layer="overlay"` span sharing
    the same anchors (see module docstring). `overlay_depth`/`overlay_position` are set only
    on overlay spans; `flags`/`cast_refs`/`density_hint`/`continuity_of_span_id` describe the
    beat and are conventionally carried on its picture span.
    """

    layer: Layer
    start_anchor: WordAnchor
    end_anchor: WordAnchor
    kind: str
    workflow_id: Optional[str] = None
    provenance: Provenance = "human"
    orphaned: bool = False
    note: str = ""
    brief: Brief = Field(default_factory=Brief)
    direction_note: str = ""
    flags: list[BeatFlag] = []
    density_hint: Optional[str] = None
    cast_refs: list[str] = []
    # Overlay-only (layer == "overlay"): both set or both unset.
    overlay_depth: Optional[OverlayDepth] = None
    overlay_position: Optional[OverlayPosition] = None
    # Chained-frame continuity ("+3 more" escape hatch): this beat's start frame continues
    # from another beat's *picked* frame -- a cross-beat edge, cast-style. Only meaningful
    # on a `live_action` picture span; the referenced span must itself be `live_action`.
    continuity_of_span_id: Optional[str] = None

    @model_validator(mode="after")
    def _overlay_fields_scoped(self) -> "Span":
        if self.layer == "overlay":
            if (self.overlay_depth is None) != (self.overlay_position is None):
                raise ValueError("Span: overlay_depth and overlay_position must be set together")
        elif self.overlay_depth is not None or self.overlay_position is not None:
            raise ValueError("Span: overlay_depth/overlay_position only apply to layer='overlay'")
        return self


class Section(Value):
    """A named grouping of passages within a Cut (e.g. a beat or chapter)."""

    id: str
    title: str
    passage_ids: list[str] = []


class Cut(Entity):
    """One edit of a project: a specific arrangement of passages and spans."""

    aspect: Rational
    fps: Rational = Field(default_factory=lambda: DEFAULT_FPS)
    parent_cut_id: Optional[str] = None
    variant_label: str = ""
    sections: list[Section] = []
    passages: list[Passage] = []
    spans: list[Span] = []

    @field_validator("passages")
    @classmethod
    def _passages_unique(cls, v: list[Passage]) -> list[Passage]:
        ids = [p.id for p in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Cut.passages must have unique ids")
        return v

    @field_validator("spans")
    @classmethod
    def _spans_unique(cls, v: list[Span]) -> list[Span]:
        ids = [s.id for s in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Cut.spans must have unique ids")
        return v

    @model_validator(mode="after")
    def _sections_reference_known_passages(self) -> "Cut":
        passage_ids = {p.id for p in self.passages}
        for section in self.sections:
            unknown = [pid for pid in section.passage_ids if pid not in passage_ids]
            if unknown:
                raise ValueError(f"Section {section.id!r} references unknown passage ids: {unknown}")
        return self

    def _picture_span_for_anchors(self, start: WordAnchor, end: WordAnchor) -> Optional[Span]:
        for s in self.spans:
            if s.layer == "picture" and s.start_anchor == start and s.end_anchor == end:
                return s
        return None

    @model_validator(mode="after")
    def _overlay_depth_position_matrix(self) -> "Cut":
        """The depth/position matrix (module docstring) is checked here, not on `Span`
        alone: legality depends on the *sibling* picture span's kind, which only the Cut
        can see. An overlay span with no sibling picture span in this Cut yet (e.g. built
        standalone, picture added later) is left unchecked -- it's re-validated whenever the
        Cut is reassembled with both spans present."""
        for span in self.spans:
            if span.layer != "overlay" or span.overlay_depth is None:
                continue
            picture = self._picture_span_for_anchors(span.start_anchor, span.end_anchor)
            if picture is None:
                continue
            allowed = valid_overlay_positions(picture.kind, span.overlay_depth)
            if span.overlay_position not in allowed:
                raise ValueError(
                    f"Span {span.id!r}: overlay position {span.overlay_position!r} invalid for "
                    f"depth={span.overlay_depth!r} over picture kind {picture.kind!r} "
                    f"(allowed: {sorted(allowed)})"
                )
        return self

    @model_validator(mode="after")
    def _continuity_refs_known_live_action(self) -> "Cut":
        by_id = {s.id: s for s in self.spans}
        for span in self.spans:
            if span.continuity_of_span_id is None:
                continue
            target = by_id.get(span.continuity_of_span_id)
            if target is None:
                raise ValueError(
                    f"Span {span.id!r}: continuity_of_span_id {span.continuity_of_span_id!r} not found"
                )
            if target.kind != "live_action" or span.kind != "live_action":
                raise ValueError(
                    f"Span {span.id!r}: continuity_of_span_id must link two live_action picture spans"
                )
        return self
