"""schema_parse.py — the field-level YAML→dataclass parsers `schema.BrandKit` calls.

Split out of `schema.py` purely to keep files small (AGENTS.md: no file over ~400
lines). `schema.py` owns `BrandKit` itself (loading, hashing, asset validation);
everything here is a pure function of raw dicts/lists (no `BrandKit` dependency), so it
has no circular import back to `schema.py` — `schema.py` imports from here, never the
reverse.
"""
from __future__ import annotations

import re
from typing import Any

from .fields import (
    COLOUR_ROLES, SOURCE_KINDS, TYPOGRAPHY_ROLES, TYPOGRAPHY_SOURCES, WORLD_TONES,
    CaptionStyle, ColourEntry, CssVar, ItemsList, Logo, LogoPlacement, StyleBlock,
    TextField, TypeRole,
)

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
REQUIRED_ASPECTS = ("16:9", "9:16")
STATUS_VALUES = ("filled", "pending")
FORBID_KEY_RE = re.compile(r"^forbid")


class BrandKitError(ValueError):
    """A brand.yaml (or its referenced assets) failed validation."""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise BrandKitError(msg)


def require_dict(value: Any, path: str) -> dict:
    _require(isinstance(value, dict), f"{path}: expected a mapping, got {type(value).__name__}")
    return value


def require_str(value: Any, path: str, allow_empty: bool = False) -> str:
    _require(isinstance(value, str), f"{path}: expected a string, got {type(value).__name__}")
    if not allow_empty:
        _require(value.strip() != "", f"{path}: must not be empty")
    return value


def require_hex(value: Any, path: str) -> str:
    s = require_str(value, path)
    _require(bool(HEX_RE.match(s)), f"{path}: '{s}' is not a 6-digit hex colour like #AABBCC")
    return s


def require_number(value: Any, path: str, lo: float | None = None, hi: float | None = None) -> float:
    _require(isinstance(value, (int, float)) and not isinstance(value, bool),
              f"{path}: expected a number, got {type(value).__name__}")
    v = float(value)
    if lo is not None:
        _require(v >= lo, f"{path}: {v} must be >= {lo}")
    if hi is not None:
        _require(v <= hi, f"{path}: {v} must be <= {hi}")
    return v


def status_of(v: dict, path: str) -> str:
    s = v.get("status", "filled")
    _require(s in STATUS_VALUES, f"{path}.status: must be one of {STATUS_VALUES}, got {s!r}")
    return s


def guessed_of(v: dict, path: str) -> bool:
    g = v.get("guessed", False)
    _require(isinstance(g, bool), f"{path}.guessed: expected true/false")
    return g


def opt_str(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return require_str(value, path)


def parse_text_field(v: dict, path: str) -> TextField:
    status = status_of(v, path)
    text = v.get("text")
    text = require_str(text, f"{path}.text") if status == "filled" else opt_str(text, f"{path}.text")
    return TextField(text=text, status=status, guessed=guessed_of(v, path))


def parse_items_list(v: dict, path: str, cap: int | None = None) -> ItemsList:
    items = v.get("items", [])
    _require(isinstance(items, list), f"{path}.items: expected a list")
    items = [require_str(x, f"{path}.items[]") for x in items]
    if cap is not None:
        _require(len(items) <= cap, f"{path}.items: {len(items)} entries exceeds house cap of {cap}")
    status = status_of(v, path)
    return ItemsList(items=items, status=status, guessed=guessed_of(v, path))


def reject_positive_only(data: Any, path: str = "brand.yaml") -> None:
    """Positive-only schema (T20): a kit may never carry a `forbid`-shaped key anywhere.
    Recurses the whole raw YAML tree before any other parsing happens, so a mistake fails
    fast with a helpful, path-qualified message rather than silently loading."""
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(key, str) and FORBID_KEY_RE.match(key):
                raise BrandKitError(
                    f"{path}.{key}: brand kits are positive-only (T20) — a 'forbid'/'negatives' "
                    "list has no home here; describe what the brand IS instead. Model-level "
                    "restrictions (no generated text/logo/screen) live in house.never_generate."
                )
            reject_positive_only(value, f"{path}.{key}")
    elif isinstance(data, list):
        for i, item in enumerate(data):
            reject_positive_only(item, f"{path}[{i}]")


def parse_sources(raw: list) -> list[dict[str, str]]:
    out = []
    for i, s in enumerate(raw):
        s = require_dict(s, f"core.sources[{i}]")
        kind = require_str(s.get("kind"), f"core.sources[{i}].kind")
        _require(kind in SOURCE_KINDS, f"core.sources[{i}].kind: must be one of {SOURCE_KINDS}, got {kind!r}")
        ref = require_str(s.get("ref"), f"core.sources[{i}].ref")
        fetched_at = opt_str(s.get("fetched_at"), f"core.sources[{i}].fetched_at")
        out.append({"kind": kind, "ref": ref, "fetched_at": fetched_at})
    return out


def parse_colours(raw: dict) -> tuple[dict[str, ColourEntry], str, str | None]:
    items = require_dict(raw.get("items"), "core.colours.items")
    _require(3 <= len(items) <= 6, f"core.colours.items: must define 3-6 colours, got {len(items)}")
    out = {}
    for role, v in items.items():
        _require(role in COLOUR_ROLES, f"core.colours.items.{role}: role must be one of {COLOUR_ROLES}")
        v = require_dict(v, f"core.colours.items.{role}")
        status = status_of(v, f"core.colours.items.{role}")
        if status == "filled":
            plain_name = require_str(v.get("name_plain"), f"core.colours.items.{role}.name_plain")
            hexv = require_hex(v.get("hex"), f"core.colours.items.{role}.hex")
        else:
            plain_name = opt_str(v.get("name_plain"), f"core.colours.items.{role}.name_plain")
            hexv = v.get("hex")
            if hexv is not None:
                hexv = require_hex(hexv, f"core.colours.items.{role}.hex")
        out[role] = ColourEntry(
            role=role, name_plain=plain_name, hex=hexv, status=status,
            guessed=guessed_of(v, f"core.colours.items.{role}"),
        )
    world_tone = opt_str(raw.get("world_tone"), "core.colours.world_tone")
    if world_tone is not None:
        _require(world_tone in WORLD_TONES, f"core.colours.world_tone: must be one of {WORLD_TONES}")
    else:
        world_tone = "light"
    dominant = opt_str(raw.get("dominant"), "core.colours.dominant")
    if dominant is not None:
        _require(dominant in out, f"core.colours.dominant: {dominant!r} is not one of core.colours.items' roles {sorted(out)}")
    return out, world_tone, dominant


def parse_typography(raw: dict) -> dict[str, TypeRole]:
    _require("heading" in raw and "body" in raw,
              "core.typography: must define 'heading' and 'body' ('mono' is optional)")
    out = {}
    for key, v in raw.items():
        _require(key in TYPOGRAPHY_ROLES, f"core.typography.{key}: role must be one of {TYPOGRAPHY_ROLES}")
        v = require_dict(v, f"core.typography.{key}")
        status = status_of(v, f"core.typography.{key}")
        if status == "filled":
            family = require_str(v.get("family"), f"core.typography.{key}.family")
            source = require_str(v.get("source"), f"core.typography.{key}.source")
            _require(source in TYPOGRAPHY_SOURCES, f"core.typography.{key}.source: must be one of {TYPOGRAPHY_SOURCES}")
        else:
            family = opt_str(v.get("family"), f"core.typography.{key}.family")
            source = v.get("source")
            if source is not None:
                source = require_str(source, f"core.typography.{key}.source")
                _require(source in TYPOGRAPHY_SOURCES, f"core.typography.{key}.source: must be one of {TYPOGRAPHY_SOURCES}")
        file_ = opt_str(v.get("file"), f"core.typography.{key}.file")
        out[key] = TypeRole(key=key, family=family, source=source, file=file_,
                             status=status, guessed=guessed_of(v, f"core.typography.{key}"))
    return out


def parse_logos(raw: dict) -> dict[str, Logo]:
    _require(len(raw) > 0, "core.logos: must define at least one slot")
    out = {}
    for key, v in raw.items():
        v = require_dict(v, f"core.logos.{key}")
        status = status_of(v, f"core.logos.{key}")
        file_ = opt_str(v.get("file"), f"core.logos.{key}.file")
        placements_raw = v.get("placements", {}) or {}
        placements_raw = require_dict(placements_raw, f"core.logos.{key}.placements")
        if status == "filled":
            _require(file_ is not None, f"core.logos.{key}.file: required when status is 'filled'")
            for aspect in REQUIRED_ASPECTS:
                _require(aspect in placements_raw,
                          f"core.logos.{key}.placements: missing required aspect '{aspect}'")
        placements = {}
        for aspect, p in placements_raw.items():
            p = require_dict(p, f"core.logos.{key}.placements.{aspect}")
            placements[aspect] = LogoPlacement(
                position=require_str(p.get("position"), f"core.logos.{key}.placements.{aspect}.position"),
                inset_px=require_number(p.get("inset_px"), f"core.logos.{key}.placements.{aspect}.inset_px", lo=0),
                height_px=require_number(p.get("height_px"), f"core.logos.{key}.placements.{aspect}.height_px", lo=0),
            )
        clear_space = v.get("clear_space")
        min_size = v.get("min_size_px")
        out[key] = Logo(
            variant=key, file=file_,
            clear_space=require_number(clear_space, f"core.logos.{key}.clear_space", lo=0) if clear_space is not None else None,
            min_size_px=require_number(min_size, f"core.logos.{key}.min_size_px", lo=0) if min_size is not None else None,
            placements=placements, status=status, guessed=guessed_of(v, f"core.logos.{key}"),
        )
    return out


def parse_style_block(v: dict) -> StyleBlock:
    status = status_of(v, "stills.style_block")
    text = v.get("text")
    text = require_str(text, "stills.style_block.text") if status == "filled" else opt_str(text, "stills.style_block.text")
    derived_from = v.get("derived_from", [])
    _require(isinstance(derived_from, list), "stills.style_block.derived_from: expected a list")
    version = v.get("version")
    if version is not None:
        version = require_str(str(version), "stills.style_block.version")
    return StyleBlock(text=text, version=version,
                       derived_from=[require_str(x, "stills.style_block.derived_from[]") for x in derived_from],
                       status=status, guessed=guessed_of(v, "stills.style_block"))


def parse_captions(raw: dict, typography: dict[str, TypeRole]) -> CaptionStyle:
    status = status_of(raw, "animation.caption_style")
    font_role = require_str(raw.get("font_role"), "animation.caption_style.font_role")
    _require(font_role in typography, f"animation.caption_style.font_role: '{font_role}' is not a defined core.typography role")
    palette_raw = require_dict(raw.get("palette"), "animation.caption_style.palette")
    for k in ("dark", "light"):
        _require(k in palette_raw, f"animation.caption_style.palette: missing required key '{k}'")
    palette = {}
    for k, v in palette_raw.items():
        v = require_dict(v, f"animation.caption_style.palette.{k}")
        palette[k] = require_hex(v.get("brand"), f"animation.caption_style.palette.{k}.brand")
    return CaptionStyle(
        font_role=font_role, palette=palette,
        band=require_number(raw.get("band", 0.905), "animation.caption_style.band", lo=0, hi=1),
        max_words=int(require_number(raw.get("max_words", 6), "animation.caption_style.max_words", lo=1)),
        font_scale=require_number(raw.get("font_scale", 1.0), "animation.caption_style.font_scale", lo=0),
        status=status, guessed=guessed_of(raw, "animation.caption_style"),
    )


def parse_css_vars(raw: dict) -> dict[str, CssVar]:
    out = {}
    for key, v in raw.items():
        v = require_dict(v, f"animation.css_vars.{key}")
        status = status_of(v, f"animation.css_vars.{key}")
        value = v.get("value")
        value = require_str(value, f"animation.css_vars.{key}.value") if status == "filled" else opt_str(value, f"animation.css_vars.{key}.value")
        out[key] = CssVar(key=key, value=value, status=status, guessed=guessed_of(v, f"animation.css_vars.{key}"))
    return out
