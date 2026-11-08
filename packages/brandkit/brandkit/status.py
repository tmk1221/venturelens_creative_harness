"""status.py — `python -m brandkit status <kit>` readiness report.

Walks every fillable field on a `BrandKit`, buckets it into filled / pending / guessed,
and notes what a pending field blocks downstream (a still/video prompt, an overlay, a
composited logo, ...). Nothing here mutates the kit; it only reads what `schema.py`
already validated. Field paths follow the T20 schema: `core.*` (identity, colours,
typography, logos, personality, world, names), `stills.*`, `video.*`, `animation.*`.
"""
from __future__ import annotations

from dataclasses import dataclass

from .schema import BrandKit


@dataclass
class FieldStatus:
    path: str
    status: str  # "filled" | "pending"
    guessed: bool
    blocks: str = ""


def _field(path: str, status: str, guessed: bool, blocks: str = "") -> FieldStatus:
    return FieldStatus(path=path, status=status, guessed=guessed, blocks=blocks if status == "pending" else "")


def collect_fields(kit: BrandKit) -> list[FieldStatus]:
    out: list[FieldStatus] = []

    out.append(_field("core.identity.name", kit.core_identity_name.status, kit.core_identity_name.guessed,
                       "core.identity.name pending -> compiled artifacts fall back to the kit slug"))
    out.append(_field("core.identity.what_they_do", kit.core_what_they_do.status, kit.core_what_they_do.guessed,
                       "core.identity.what_they_do pending -> writer_context()'s identity string is empty"))
    out.append(_field("core.identity.who_they_serve", kit.core_who_they_serve.status, kit.core_who_they_serve.guessed,
                       "core.identity.who_they_serve pending -> writer_context()'s identity string omits an audience"))

    for role, c in kit.core_colours.items():
        out.append(_field(f"core.colours.{role}", c.status, c.guessed,
                           f"core.colours.{role} pending -> compiled brand.css/design.md/animation_brief omit this colour"))

    for key, t in kit.core_typography.items():
        out.append(_field(f"core.typography.{key}", t.status, t.guessed,
                           f"core.typography.{key} pending -> captions/overlays using this role render with no declared font"))
    for key, logo in kit.core_logos.items():
        out.append(_field(f"core.logos.{key}", logo.status, logo.guessed,
                           f"core.logos.{key} pending -> overlays/composites needing this logo cannot render; stills/video generation is unaffected (logos are never generated)"))

    out.append(_field("core.personality.is", kit.core_personality_is.status, kit.core_personality_is.guessed,
                       "core.personality.is pending -> writer_context()'s personality string has no adjectives"))
    out.append(_field("core.personality.voice", kit.core_personality_voice.status, kit.core_personality_voice.guessed,
                       "core.personality.voice pending -> writer_context()'s personality string has no voice sentence"))

    out.append(_field("core.world.places", kit.core_world_places.status, kit.core_world_places.guessed,
                       "core.world.places pending -> writer_context()'s world string omits places"))
    out.append(_field("core.world.people", kit.core_world_people.status, kit.core_world_people.guessed,
                       "core.world.people pending -> writer_context()'s world string omits people"))
    out.append(_field("core.world.objects", kit.core_world_objects.status, kit.core_world_objects.guessed,
                       "core.world.objects pending -> writer_context()'s world string omits objects"))
    out.append(_field("core.world.textures", kit.core_world_textures.status, kit.core_world_textures.guessed,
                       "core.world.textures pending -> writer_context()'s world string omits textures"))

    out.append(_field("core.names.official", kit.core_names_official.status, kit.core_names_official.guessed,
                       "core.names.official pending -> lint's on-screen-name check has nothing to allow against"))
    out.append(_field("core.names.products", kit.core_names_products.status, kit.core_names_products.guessed,
                       "core.names.products pending -> lint's on-screen-name check has nothing to allow against"))

    out.append(_field("stills.style_block", kit.stills_style_block.status, kit.stills_style_block.guessed,
                       "stills.style_block pending -> still_prompt and motion_prompt refuse to build; fill "
                       "'## stills.style_block' in design-system/imagery.md (derive-style drafts one from approved stills)"))
    out.append(_field("stills.accents", kit.stills_accents.status, kit.stills_accents.guessed,
                       "stills.accents pending -> stills omit a brand-colour wardrobe/prop accent; not blocking"))

    out.append(_field("video.camera_personality", kit.video_camera_personality.status, kit.video_camera_personality.guessed,
                       "video.camera_personality pending -> motion_prompt uses the beat's camera, else the house neutral camera"))
    out.append(_field("video.pacing_default", kit.video_pacing_default.status, kit.video_pacing_default.guessed,
                       "video.pacing_default pending -> motion_prompt uses the beat's pacing, else the house neutral pacing"))

    out.append(_field("animation.grid_safe_areas", kit.animation_grid_safe_areas.status, kit.animation_grid_safe_areas.guessed,
                       "animation.grid_safe_areas pending -> falls back to house safe-area defaults only"))
    out.append(_field("animation.easing", kit.animation_easing.status, kit.animation_easing.guessed,
                       "animation.easing pending -> falls back to house motion_design defaults only"))
    out.append(_field("animation.durations", kit.animation_durations.status, kit.animation_durations.guessed,
                       "animation.durations pending -> falls back to house motion_design defaults only"))
    out.append(_field("animation.colour_ratio", kit.animation_colour_ratio.status, kit.animation_colour_ratio.guessed,
                       "animation.colour_ratio pending -> falls back to house color_ratio default only"))
    out.append(_field("animation.caption_style", kit.animation_caption_style.status, kit.animation_caption_style.guessed,
                       "animation.caption_style pending -> compile_captions still runs off the declared defaults; review before trusting the output"))
    out.append(_field("animation.sfx_palette", kit.animation_sfx_palette.status, kit.animation_sfx_palette.guessed,
                       "animation.sfx_palette pending -> no SFX cues available for this kit"))
    for key, v in kit.animation_css_vars.items():
        out.append(_field(f"animation.css_vars.{key}", v.status, v.guessed,
                           f"animation.css_vars.{key} pending -> compiled brand.css uses the plain derived value for this token"))

    return out


def status_report(kit: BrandKit) -> dict:
    fields = collect_fields(kit)
    filled = [f for f in fields if f.status == "filled" and not f.guessed]
    guessed = [f for f in fields if f.status == "filled" and f.guessed]
    pending = [f for f in fields if f.status == "pending"]
    return {
        "kit": kit.name,
        "version": kit.version,
        "counts": {"filled": len(filled), "guessed": len(guessed), "pending": len(pending), "total": len(fields)},
        "filled": [f.path for f in filled],
        "guessed": [f.path for f in guessed],
        "pending": [{"field": f.path, "blocks": f.blocks} for f in pending],
    }
