"""merge.py — house -> brand -> look layering.

A kit's effective craft rules are the house defaults with a kit's `house_overrides:`
applied on top, section by section, and only where the house section says
`overridable: true`. Anything else in `house_overrides` is an error — a kit cannot
silently change a rule Travis has fixed as universal (safe areas, the QA checklist,
negative-prompt caps, the prompt template structures).

`Look` (per-video) never touches house rules — it only overrides a handful of brand-layer
prompt inputs (setting, wardrobe, mood, references), applied directly inside
`compile.still_prompt` / `compile.motion_prompt`.
"""
from __future__ import annotations

import copy
from typing import Any


class MergeError(ValueError):
    """A kit's `house_overrides` touched a section it isn't allowed to."""


def merge_house(house: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    merged = copy.deepcopy(house)
    if not overrides:
        return merged
    for section, override_vals in overrides.items():
        if section not in merged:
            raise MergeError(f"house_overrides.{section}: unknown house section")
        if not merged[section].get("overridable", False):
            raise MergeError(f"house_overrides.{section}: not overridable by a kit")
        if not isinstance(override_vals, dict):
            raise MergeError(f"house_overrides.{section}: expected a mapping")
        merged[section] = {**merged[section], **override_vals}
    return merged
