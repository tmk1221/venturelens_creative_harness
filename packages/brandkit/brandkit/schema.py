"""schema.py — load and validate a client `brand.yaml`, and compute its content hash.

A brand kit is a directory: `brand.yaml` plus the asset files (SVG logos, font files) it
points to by relative path. `brand.yaml` is the *brand* layer only — universal craft
rules live in `house/house.yaml` (see `house.py`) and are merged onto every kit at load
time (see `merge.py`), landing on `kit.house`.

T20 rebuilds the kit around a single `core`: identity, colours (role-tagged from a fixed
enum, plus world_tone/dominant), typography, logos (moved here from `animation`),
personality, world (subject matter that belongs in this brand's pictures), names, and
sources. `animation` shrinks to pure motion/graphics behaviour (grid, easing, durations,
colour_ratio, caption_style, sfx_palette, css_vars). Everything is POSITIVE ONLY: no
`forbid` keys anywhere in a kit, no `negatives` lists on `stills`/`video` — house-level
technical defaults (never generate legible text/a logo/a screen — a model limitation,
not a brand rule) live in `house.never_generate` and a per-beat `slots["allow"]` lifts
them (see `compile.still_prompt`).

Most fields here are "fillable": they carry `status: filled|pending` and an optional
`guessed: true`. A `pending` field is valid, not an error — `python -m brandkit status`
reports it and what it blocks. `guessed: true` marks a filled field whose value was
inferred (by a human's first guess or `brandkit init --from`) rather than confirmed
against a real brand source; it should be reviewed, not trusted. Everything downstream
(compile.py, lint.py, status.py) works off the validated `BrandKit` object this module
produces — nothing else in this package reads YAML directly.

Field-level parsing (the `parse_*` functions called below) lives in `schema_parse.py`,
split out purely to keep this file small.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .fields import CaptionStyle, ColourEntry, CssVar, ItemsList, Logo, StyleBlock, TextField, TypeRole
from .house import load_house
from .merge import MergeError, merge_house
from .schema_parse import (
    BrandKitError, parse_captions, parse_colours, parse_css_vars, parse_items_list,
    parse_logos, parse_sources, parse_style_block, parse_text_field, parse_typography,
    reject_positive_only, require_dict, require_str,
)

__all__ = ["BrandKit", "BrandKitError"]


@dataclass
class BrandKit:
    path: Path
    name: str
    version: str
    house: dict[str, Any]

    # ---- core ---------------------------------------------------------------------
    core_identity_name: TextField
    core_what_they_do: TextField
    core_who_they_serve: TextField

    core_colours: dict[str, ColourEntry]
    core_world_tone: str
    core_dominant: str | None

    core_typography: dict[str, TypeRole]
    core_logos: dict[str, Logo]

    core_personality_is: ItemsList
    core_personality_voice: TextField

    core_world_places: ItemsList
    core_world_people: ItemsList
    core_world_objects: ItemsList
    core_world_textures: ItemsList

    core_names_official: ItemsList
    core_names_products: ItemsList
    core_names_pronunciation: list[dict[str, str]]

    core_sources: list[dict[str, str]]

    # ---- stills / video -------------------------------------------------------------
    stills_style_block: StyleBlock
    stills_accents: TextField

    video_camera_personality: TextField
    video_pacing_default: TextField

    # ---- animation (behaviour only) --------------------------------------------------
    animation_grid_safe_areas: TextField
    animation_easing: TextField
    animation_durations: TextField
    animation_colour_ratio: TextField
    animation_caption_style: CaptionStyle
    animation_sfx_palette: ItemsList
    animation_css_vars: dict[str, CssVar]

    qa_checklist_extra: list[str]
    _raw_yaml_bytes: bytes = b""

    # ---- loading -----------------------------------------------------------

    @classmethod
    def load(cls, kit_dir: str | Path, house: dict[str, Any] | None = None) -> "BrandKit":
        kit_dir = Path(kit_dir)
        yaml_path = kit_dir / "brand.yaml"
        ds_dir = kit_dir / "design-system"
        if (ds_dir / "design-system.json").is_file():
            # The Brand System export is the source of truth: derive the kit in memory,
            # so no brand.yaml is ever written or edited for such a client.
            from .design_system import pull_brand_yaml
            raw = pull_brand_yaml(ds_dir).encode("utf-8")
            yaml_path = ds_dir / "design-system.json"
        elif yaml_path.is_file():
            raw = yaml_path.read_bytes()
        else:
            raise BrandKitError(f"no design-system/ or brand.yaml at {kit_dir}")
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise BrandKitError(f"{yaml_path}: invalid YAML: {exc}") from exc
        data = require_dict(data, "brand.yaml")
        reject_positive_only(data)
        house_default = house if house is not None else load_house()
        try:
            merged_house = merge_house(house_default, data.get("house_overrides"))
        except MergeError as exc:
            raise BrandKitError(str(exc)) from exc
        kit = cls._from_dict(data, kit_dir, merged_house)
        kit._raw_yaml_bytes = raw
        kit._validate_assets_exist()
        return kit

    @classmethod
    def _from_dict(cls, data: dict, kit_dir: Path, house: dict[str, Any]) -> "BrandKit":
        name = require_str(data.get("name"), "name")
        version = require_str(str(data.get("version", "")), "version")

        core = require_dict(data.get("core"), "core")

        identity = require_dict(core.get("identity"), "core.identity")
        core_identity_name = parse_text_field(require_dict(identity.get("name"), "core.identity.name"), "core.identity.name")
        core_what_they_do = parse_text_field(
            require_dict(identity.get("what_they_do"), "core.identity.what_they_do"), "core.identity.what_they_do")
        core_who_they_serve = parse_text_field(
            require_dict(identity.get("who_they_serve"), "core.identity.who_they_serve"), "core.identity.who_they_serve")

        core_colours, core_world_tone, core_dominant = parse_colours(require_dict(core.get("colours"), "core.colours"))
        core_typography = parse_typography(require_dict(core.get("typography"), "core.typography"))
        core_logos = parse_logos(require_dict(core.get("logos"), "core.logos"))

        personality = require_dict(core.get("personality"), "core.personality")
        core_personality_is = parse_items_list(
            require_dict(personality.get("is"), "core.personality.is"), "core.personality.is", cap=5)
        core_personality_voice = parse_text_field(
            require_dict(personality.get("voice"), "core.personality.voice"), "core.personality.voice")

        world = require_dict(core.get("world"), "core.world")
        empty_items = {"items": [], "status": "pending"}
        core_world_places = parse_items_list(require_dict(world.get("places", empty_items), "core.world.places"), "core.world.places")
        core_world_people = parse_items_list(require_dict(world.get("people", empty_items), "core.world.people"), "core.world.people")
        core_world_objects = parse_items_list(require_dict(world.get("objects", empty_items), "core.world.objects"), "core.world.objects")
        core_world_textures = parse_items_list(require_dict(world.get("textures", empty_items), "core.world.textures"), "core.world.textures")

        names = require_dict(core.get("names"), "core.names")
        core_names_official = parse_items_list(
            require_dict(names.get("official", empty_items), "core.names.official"), "core.names.official")
        core_names_products = parse_items_list(
            require_dict(names.get("products", empty_items), "core.names.products"), "core.names.products")
        pronunciation = names.get("pronunciation", [])
        if not isinstance(pronunciation, list):
            raise BrandKitError("core.names.pronunciation: expected a list")
        core_names_pronunciation = pronunciation

        sources = core.get("sources", [])
        if not isinstance(sources, list):
            raise BrandKitError("core.sources: expected a list")
        core_sources = parse_sources(sources)

        stills = require_dict(data.get("stills"), "stills")
        stills_style_block = parse_style_block(require_dict(stills.get("style_block"), "stills.style_block"))
        stills_accents = parse_text_field(require_dict(stills.get("accents"), "stills.accents"), "stills.accents")

        video = require_dict(data.get("video"), "video")
        video_camera = parse_text_field(require_dict(video.get("camera_personality"), "video.camera_personality"),
                                         "video.camera_personality")
        video_pacing = parse_text_field(require_dict(video.get("pacing_default"), "video.pacing_default"),
                                         "video.pacing_default")

        animation = require_dict(data.get("animation"), "animation")
        animation_grid = parse_text_field(
            require_dict(animation.get("grid_safe_areas"), "animation.grid_safe_areas"), "animation.grid_safe_areas")
        animation_easing = parse_text_field(require_dict(animation.get("easing"), "animation.easing"), "animation.easing")
        animation_durations = parse_text_field(
            require_dict(animation.get("durations"), "animation.durations"), "animation.durations")
        animation_ratio = parse_text_field(
            require_dict(animation.get("colour_ratio"), "animation.colour_ratio"), "animation.colour_ratio")
        animation_captions = parse_captions(
            require_dict(animation.get("caption_style"), "animation.caption_style"), core_typography)
        animation_sfx = parse_items_list(
            require_dict(animation.get("sfx_palette", empty_items), "animation.sfx_palette"), "animation.sfx_palette")
        animation_css_vars = parse_css_vars(animation.get("css_vars", {}) or {})

        qa_extra = data.get("qa_checklist_extra", [])
        if not isinstance(qa_extra, list):
            raise BrandKitError("qa_checklist_extra: expected a list")
        qa_extra = [require_str(x, "qa_checklist_extra[]") for x in qa_extra]

        return cls(
            path=kit_dir, name=name, version=version, house=house,
            core_identity_name=core_identity_name, core_what_they_do=core_what_they_do,
            core_who_they_serve=core_who_they_serve,
            core_colours=core_colours, core_world_tone=core_world_tone, core_dominant=core_dominant,
            core_typography=core_typography, core_logos=core_logos,
            core_personality_is=core_personality_is, core_personality_voice=core_personality_voice,
            core_world_places=core_world_places, core_world_people=core_world_people,
            core_world_objects=core_world_objects, core_world_textures=core_world_textures,
            core_names_official=core_names_official, core_names_products=core_names_products,
            core_names_pronunciation=core_names_pronunciation, core_sources=core_sources,
            stills_style_block=stills_style_block, stills_accents=stills_accents,
            video_camera_personality=video_camera, video_pacing_default=video_pacing,
            animation_grid_safe_areas=animation_grid, animation_easing=animation_easing,
            animation_durations=animation_durations, animation_colour_ratio=animation_ratio,
            animation_caption_style=animation_captions, animation_sfx_palette=animation_sfx,
            animation_css_vars=animation_css_vars,
            qa_checklist_extra=qa_extra,
        )

    def _validate_assets_exist(self) -> None:
        for logo in self.core_logos.values():
            if logo.file:
                p = self.path / logo.file
                if not p.is_file():
                    raise BrandKitError(f"core.logos.{logo.variant}.file: file not found at {p}")
        for t in self.core_typography.values():
            if t.file:
                p = self.path / t.file
                if not p.is_file():
                    raise BrandKitError(f"core.typography.{t.key}.file: file not found at {p}")

    # ---- derived -------------------------------------------------------------

    def asset_paths(self) -> list[Path]:
        """All asset files this kit's hash depends on, sorted for determinism."""
        rel_paths = {logo.file for logo in self.core_logos.values() if logo.file}
        rel_paths |= {t.file for t in self.core_typography.values() if t.file}
        return sorted((self.path / p) for p in rel_paths)

    def kit_hash(self) -> str:
        """sha256 over brand.yaml's bytes plus every referenced asset's bytes, in a fixed
        (sorted-by-relative-path) order — so the hash only changes when the kit's actual
        content changes, never by directory-listing order or unrelated files."""
        h = hashlib.sha256()
        h.update(self._raw_yaml_bytes)
        for p in self.asset_paths():
            h.update(str(p.relative_to(self.path)).encode("utf-8"))
            h.update(p.read_bytes())
        return h.hexdigest()
