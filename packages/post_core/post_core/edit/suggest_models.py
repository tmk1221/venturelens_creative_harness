"""Data shapes for T13b/T30b's automated "Suggest visuals" pass -- proposals, never spans
(spec: "validated ...; stored as suggestions, never as spans"). Kept separate from
`model/cut.py`'s `Span` on purpose: a `Suggestion` is provisional and lives in its own
on-disk file (`suggest_store.py`) until a human accepts it, at which point
`suggest.py::accept_suggestion` turns it into real `Span`s (`edit._spans.add_beat_spans`) and
the suggestion row disappears.

T30b: the suggester now chooses the *whole* beat model, not just a `video`/`anim`/`overlay`
bucket -- `medium` (the T30 picture taxonomy) and, independently, an optional overlay
(depth+position). A proposal must set at least one of the two ("propose nothing" isn't a
valid suggestion); `layers_for` tells a caller which Span layer(s) accepting it will create.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..model.base import new_id
from ..model.common import WordAnchor
from ..model.cut import BeatFlag, OverlayDepth, OverlayPosition, PictureKind, valid_overlay_positions


class SuggestError(ValueError):
    """A scope or proposal could not be turned into suggestions."""


# T42: the fields that make up one idea for a beat's words (everything but the range).
IDEA_FIELDS = ("medium", "overlay_depth", "overlay_position", "brief", "direction_note", "flags",
               "cast_refs", "density_hint", "rationale")


class SuggestionVariant(BaseModel):
    """T42: one idea for a proposal's words -- when the agent offers two for the same range, the
    card shows "Variant A" / "Variant B" and the person switches between them."""

    model_config = ConfigDict(extra="forbid")

    medium: Optional[PictureKind] = None
    overlay_depth: Optional[OverlayDepth] = None
    overlay_position: Optional[OverlayPosition] = None
    brief: str
    direction_note: str = ""
    flags: list[BeatFlag] = []
    cast_refs: list[str] = []
    density_hint: Optional[str] = None
    rationale: str = ""


class Suggestion(BaseModel):
    """One proposed beat: a word range, the full T30 beat model the suggester chose for it
    (medium and/or overlay depth+position), flags, a brief, and why."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    start_anchor: WordAnchor
    end_anchor: WordAnchor
    medium: Optional[PictureKind] = None
    overlay_depth: Optional[OverlayDepth] = None
    overlay_position: Optional[OverlayPosition] = None
    brief: str
    direction_note: str = ""
    flags: list[BeatFlag] = []
    cast_refs: list[str] = []
    density_hint: Optional[str] = None
    rationale: str
    # T42: every idea for these words (A, B, ...) when there is more than one; the fields above
    # are the active one, `variants[active_variant]` is refreshed from them on a switch.
    variants: list[SuggestionVariant] = []
    active_variant: int = 0

    def idea(self) -> SuggestionVariant:
        return SuggestionVariant(**{k: getattr(self, k) for k in IDEA_FIELDS})

    @model_validator(mode="after")
    def _proposes_something_and_is_self_consistent(self) -> "Suggestion":
        if self.medium is None and self.overlay_depth is None:
            raise ValueError("Suggestion: must propose a medium and/or an overlay")
        if (self.overlay_depth is None) != (self.overlay_position is None):
            raise ValueError("Suggestion: overlay_depth/overlay_position must be set together")
        if self.overlay_depth is not None and self.medium is not None:
            allowed = valid_overlay_positions(self.medium, self.overlay_depth)
            if self.overlay_position not in allowed:
                raise ValueError(
                    f"Suggestion: overlay position {self.overlay_position!r} invalid for "
                    f"depth={self.overlay_depth!r} over medium {self.medium!r} (allowed: {sorted(allowed)})"
                )
        return self


class SuggestionsFile(BaseModel):
    """The whole on-disk record for one cut: pending proposals plus every word-range key a
    human has dismissed (so re-running "Suggest visuals" never resurfaces it -- spec step 4:
    "dismissed ranges are not re-suggested")."""

    model_config = ConfigDict(extra="forbid")

    cut_id: str
    items: list[Suggestion] = []
    dismissed_keys: list[str] = []


def dismissed_key(start_word_id: str, end_word_id: str) -> str:
    return f"{start_word_id}:{end_word_id}"


def layers_for(suggestion: Suggestion) -> list[str]:
    """Which `Span.layer`(s) accepting `suggestion` will create -- "picture", "overlay",
    both, or (never valid, see the validator above) neither."""
    layers = []
    if suggestion.medium is not None:
        layers.append("picture")
    if suggestion.overlay_depth is not None:
        layers.append("overlay")
    return layers


__all__ = ["SuggestError", "IDEA_FIELDS", "SuggestionVariant", "Suggestion", "SuggestionsFile", "dismissed_key", "layers_for"]
