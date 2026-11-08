"""house.py — load `house/house.yaml`, Travis's universal craft rules.

House rules are shipped with the package (one file, not per-client). `schema.BrandKit`
loads and merges house rules at kit-load time via `merge.merge_house`, so every downstream
consumer (compile.py, status.py) reads `kit.house` — a plain dict — rather than touching
this module or the raw file directly.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

HOUSE_PATH = Path(__file__).resolve().parent.parent / "house" / "house.yaml"


class HouseError(ValueError):
    """house.yaml failed to load or is malformed."""


def load_house(path: Path | None = None) -> dict[str, Any]:
    path = path or HOUSE_PATH
    if not path.is_file():
        raise HouseError(f"no house.yaml at {path}")
    try:
        data = yaml.safe_load(path.read_bytes())
    except yaml.YAMLError as exc:
        raise HouseError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise HouseError(f"{path}: expected a mapping at the top level")
    return data
