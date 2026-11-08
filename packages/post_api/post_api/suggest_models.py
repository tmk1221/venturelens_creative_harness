"""T13b/T30b/T42: response shapes for `/api/projects/{pid}/cuts/{cut_id}/suggested-visuals`
(re-exported by `post_api.models`)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class SuggestionVariantOut(BaseModel):
    """T42: one idea for a proposal's words ("Variant A", "Variant B", ...)."""

    model_config = ConfigDict(extra="forbid")

    medium: Optional[str] = None
    overlay_depth: Optional[str] = None
    overlay_position: Optional[str] = None
    brief: str
    direction_note: str = ""
    flags: list[str] = []
    cast_refs: list[str] = []
    density_hint: Optional[str] = None
    rationale: str = ""


class VisualSuggestionOut(BaseModel):
    """T13b/T30b: one pending automated "Suggest visuals" proposal -- distinct from
    `SuggestionOut` (the older filler/silence removal suggestions). T30b: carries the full
    beat model (`medium` + optional overlay depth/position/flags), not just a layer bucket."""

    model_config = ConfigDict(extra="forbid")

    id: str
    transcript_id: str
    start_word_id: str
    end_word_id: str
    medium: Optional[str] = None
    overlay_depth: Optional[str] = None
    overlay_position: Optional[str] = None
    brief: str
    direction_note: str = ""
    flags: list[str] = []
    cast_refs: list[str] = []
    density_hint: Optional[str] = None
    rationale: str
    # T42: every idea for these words when the agent offered more than one; the fields above
    # are `variants[active_variant]` (switch with `POST .../{id}/variant`).
    variants: list[SuggestionVariantOut] = []
    active_variant: int = 0


class SuggestVisualsResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[VisualSuggestionOut]


class AcceptSuggestionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cut_id: str
    revision: int
    span_id: str


class AcceptAllOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: list[str]
    blocked: list[str]


__all__ = ["SuggestionVariantOut", "VisualSuggestionOut", "SuggestVisualsResult", "AcceptSuggestionOut", "AcceptAllOut"]
