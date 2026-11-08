"""style_axes.py — load `house/style_axes.yaml`.

The style axes are shipped with the package, same for every client (like house.yaml).
`derive.py` reads them to build the prompt asking a vision model to describe what a
folder of reference images share, axis by axis.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

STYLE_AXES_PATH = Path(__file__).resolve().parent.parent / "house" / "style_axes.yaml"


class StyleAxesError(ValueError):
    """style_axes.yaml failed to load or is malformed."""


def load_style_axes(path: Path | None = None) -> dict[str, Any]:
    path = path or STYLE_AXES_PATH
    if not path.is_file():
        raise StyleAxesError(f"no style_axes.yaml at {path}")
    try:
        data = yaml.safe_load(path.read_bytes())
    except yaml.YAMLError as exc:
        raise StyleAxesError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict) or "axes" not in data or not isinstance(data["axes"], dict):
        raise StyleAxesError(f"{path}: expected a mapping with an 'axes' key")
    return data


def axis_keys(data: dict[str, Any] | None = None) -> list[str]:
    data = data or load_style_axes()
    return list(data["axes"].keys())
