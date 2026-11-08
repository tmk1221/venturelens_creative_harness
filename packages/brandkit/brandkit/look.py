"""look.py — an optional, per-video/series layer on top of a brand kit.

A look never invents brand values; it only narrows or varies the brand layer for one
video or series. Per T17, a look may override exactly:

  - `stills.style_block` (as plain `style_block` text)
  - `stills.accents` (as plain `accents` text)
  - `video.camera_personality` (as plain `camera_personality` text)
  - nothing in `animation` except `caption_style`

Anything else in a `looks/<name>.yaml` file is an error — a look cannot invent a palette,
change logos, or touch house-level craft rules. Loading a look does not require
house.yaml or the kit it will later apply to — merging happens at prompt-build time in
`compile.still_prompt` / `compile.motion_prompt` / `compile.compile_captions`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ALLOWED_KEYS = {"name", "style_block", "accents", "camera_personality", "caption_style"}


class LookError(ValueError):
    """A looks/<name>.yaml failed to load or is malformed, or overrides a field it isn't
    allowed to."""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise LookError(msg)


def _require_str(value: Any, path: str) -> str:
    _require(isinstance(value, str) and value.strip() != "", f"{path}: expected a non-empty string")
    return value


@dataclass
class Look:
    name: str
    style_block: str | None = None
    accents: str | None = None
    camera_personality: str | None = None
    caption_style: dict[str, Any] | None = None

    @classmethod
    def load(cls, path: str | Path) -> "Look":
        path = Path(path)
        _require(path.is_file(), f"no look file at {path}")
        try:
            data = yaml.safe_load(path.read_bytes())
        except yaml.YAMLError as exc:
            raise LookError(f"{path}: invalid YAML: {exc}") from exc
        _require(isinstance(data, dict), f"{path}: expected a mapping at the top level")

        unknown = set(data.keys()) - ALLOWED_KEYS
        _require(not unknown, f"{path}: a look may not override {sorted(unknown)} — only "
                               f"{sorted(ALLOWED_KEYS - {'name'})} are allowed")

        name = _require_str(data.get("name", path.stem), "name")
        caption_style = data.get("caption_style")
        if caption_style is not None:
            _require(isinstance(caption_style, dict), "caption_style: expected a mapping")

        return cls(
            name=name,
            style_block=data.get("style_block"),
            accents=data.get("accents"),
            camera_personality=data.get("camera_personality"),
            caption_style=caption_style,
        )
