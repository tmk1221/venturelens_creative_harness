"""Prompt building for recipe nodes: thin wrappers over `brandkit.compile`.

Kept separate from `node_types.py`/`instantiate.py` so callers have one place that imports
`brandkit` for prompt text -- a node's own params must stay JSON-serialisable
(`graph.hashing` hashes them), so a `BrandKit`/`Look` object never enters a node's params;
`instantiate.py` calls these at graph-build time and stores only the resulting text (plus,
for stills, the style block's version/hash) in the node's params.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from brandkit.compile import StillPromptResult, animation_brief, motion_prompt, still_prompt
from brandkit.look import Look
from brandkit.schema import BrandKit


def build_still_prompt(slots: dict[str, Any], kit: BrandKit, look: Optional[Look] = None) -> StillPromptResult:
    return still_prompt(slots, kit, look)


def build_motion_prompt(slots: dict[str, Any], kit: BrandKit, look: Optional[Look] = None) -> str:
    return motion_prompt(slots, kit, look)


def build_animation_brief(kit: BrandKit, extra: Optional[dict[str, Any]] = None, look: Optional[Look] = None) -> str:
    return animation_brief(kit, extra, look)


# Cheapest possible heuristic for "this beat's brief describes a transformation, so an end
# frame is worth generating" (T30b: "optional, recommended flag from the brief") -- a plain
# keyword scan, no provider call. `instantiate.py`/callers pass it a brief/instruction string
# and get back whether the live_action recipe should default to including `endframe.
# generate`; the human can always override the recommendation either way.
_END_FRAME_KEYWORDS = (
    "transform", "before and after", "before/after", "becomes", "turns into",
    "morphs", "changes into", "reveal", "unveils", "progress", "evolves",
)


def recommend_end_frame(text: str) -> bool:
    lowered = (text or "").lower()
    return any(keyword in lowered for keyword in _END_FRAME_KEYWORDS)


# T37: a frozen last 0.5 s fails `asset.verify` unless the brief asks for it. Only phrases
# that mean "hold the frame" -- not every "holds" (a person holding a cup is not a hold).
_HOLD_RE = re.compile(
    r"\b(freeze[- ]?frame|freezes? on|hold(s|ing)? (on|at) the (end|last|final)"
    r"|hold(s|ing)? the (last|final|end) frame|(ends?|ending) (on|with) a hold|a hold at the end)\b"
)


def brief_asks_for_hold(text: str) -> bool:
    return bool(_HOLD_RE.search((text or "").lower()))


__all__ = [
    "build_still_prompt", "build_motion_prompt", "build_animation_brief", "recommend_end_frame",
    "brief_asks_for_hold",
]
