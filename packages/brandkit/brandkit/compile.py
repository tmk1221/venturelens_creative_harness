"""compile.py — turn a validated `BrandKit` into what each downstream tool expects.

Three separate prompt builders, one per medium:

  - `still_prompt` — content slots (shot_type/subject/action/setting, continuity refs
    supplied by the CALLER, never read off the kit) + the kit's derived `style_block` +
    `accents`. No reference image is attached. House `never_generate` defaults (no
    legible text / logo / screen) are appended as negatives unless a per-beat
    `slots["allow"]` lifts one (T20: "any beat may warrant anything").
  - `motion_prompt` — camera, one subject action, statics, pacing. Never restates style;
    the start frame is the anchor.
  - `animation_brief` — tokens + logo paths + rules for the HyperFrames agent. This is
    the ONE place hex/font-family/brand words are expected and allowed; it is NOT run
    through the purity check the other two builders enforce.

`compile_kit` writes the rest of the kit's static artifacts (brand.css, design.md,
captions.json, qa_checklist.md, kit.json, logo assets) into an out dir.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .look import Look
from .schema import BrandKit
from .ui_shades import derive_ui_shades

# Tokens a still/motion prompt must never contain: hexes, quotes, font-family names, and
# any brand/logo word. Kept in one place so still_prompt/motion_prompt (which must refuse
# to emit a dirty fragment) and lint.py (`lint_prompt`) agree. derive.py reuses the hex/
# quote patterns for its own, standalone purity check on a derived style block.
HEX_TOKEN_RE = re.compile(r"#[0-9A-Fa-f]{3,6}\b")
# Quotation marks only: an apostrophe inside a word (clients', don't) is not quoted text.
QUOTE_RE = re.compile(r"[\"“”]|(?<![A-Za-z])['‘’]|['‘’](?![A-Za-z])")

# House technical defaults (a model limitation, not a brand rule — house.never_generate):
# forced negatives unless a per-beat `slots["allow"]` lifts the matching token.
NEVER_GENERATE_ALLOW_MAP = {
    "text": "legible on-screen text of any kind",
    "logo": "a logo",
    "screen": "a screen or UI surface with legible content",
}

TEST_STYLE_SUBJECTS = [
    {"shot_type": "Medium shot", "subject": "a person", "action": "working at a desk", "setting": "an office"},
    {"shot_type": "Wide shot", "subject": "a street", "action": "with pedestrians passing", "setting": "a city exterior"},
    {"shot_type": "Macro shot", "subject": "an object", "action": "resting on a surface", "setting": "a plain surface"},
    {"shot_type": "Medium two-shot", "subject": "two people", "action": "talking", "setting": "a meeting room"},
    {"shot_type": "Wide shot", "subject": "an empty room", "action": "with no people present", "setting": "an interior space"},
    {"shot_type": "Close-up", "subject": "a pair of hands", "action": "working on a tool", "setting": "a workbench"},
]


class CompileError(ValueError):
    """The kit could not be compiled — e.g. a prompt would leak a brand token, or a
    required field is still `pending`."""


@dataclass
class StillPromptResult:
    text: str
    style_block_version: str | None
    style_block_hash: str | None


def _brand_words(kit: BrandKit) -> list[str]:
    words = set(kit.core_names_official.items) | set(kit.core_names_products.items)
    if kit.core_identity_name.text:
        words.add(kit.core_identity_name.text)
    words.add(kit.name)
    for t in kit.core_typography.values():
        if t.family:
            words.add(t.family)
    return sorted(w for w in words if w)


def find_prompt_violations(text: str, kit: BrandKit) -> list[str]:
    """Everything wrong with `text` as a generation-prompt fragment for this kit."""
    violations = []
    if HEX_TOKEN_RE.search(text):
        violations.append("contains a hex colour code")
    if QUOTE_RE.search(text):
        violations.append("contains quoted text")
    lower = text.lower()
    for word in _brand_words(kit):
        if word and word.lower() in lower:
            violations.append(f"contains brand/logo word: {word!r}")
    return violations


def _require_style_block(kit: BrandKit, look: Look | None) -> str:
    """The style block a still/video prompt is built under: the look's, else the kit's. Refuses
    while it is pending (for a Brand System kit: the blockquote under `## stills.style_block` in
    design-system/imagery.md is missing or still the template's placeholder), so an unbranded
    prompt never reaches a paid generator."""
    if look and look.style_block:
        return look.style_block
    if kit.stills_style_block.status != "filled" or not kit.stills_style_block.text:
        raise CompileError(
            f"{kit.name}: stills.style_block is pending — cannot build a still or video prompt yet; "
            "fill the blockquote under '## stills.style_block' in design-system/imagery.md "
            "(derive-style drafts one from approved stills)")
    return kit.stills_style_block.text


def _house_forced_negatives(kit: BrandKit, allow: list[str]) -> list[str]:
    allow_set = set(allow or [])
    items = kit.house.get("never_generate", {}).get("items", [])
    lifted = {v for k, v in NEVER_GENERATE_ALLOW_MAP.items() if k in allow_set}
    return [i for i in items if i not in lifted]


# ---- still_prompt / motion_prompt / animation_brief -----------------------------------

def still_prompt(slots: dict[str, Any], kit: BrandKit, look: Look | None = None) -> StillPromptResult:
    """Build one still-image prompt. `slots` supplies everything the kit/look can't know:
    shot_type, subject, action, setting, and optionally negatives (list[str]),
    continuity_refs (list[str] of reference image paths — supplied by the CALLER, e.g. a
    project cast registry; never read off the kit), mood (a per-beat mood string), and
    `allow` (list of "text"/"logo"/"screen" — lifts the matching house default for this
    one beat; T20: "any beat may warrant anything")."""
    style_block = _require_style_block(kit, look)
    for req in ("shot_type", "subject", "action", "setting"):
        if not slots.get(req):
            raise CompileError(f"still_prompt: slots['{req}'] is required")

    accents = look.accents if (look and look.accents) else (
        kit.stills_accents.text if kit.stills_accents.status == "filled" else None)

    negatives = _house_forced_negatives(kit, slots.get("allow", [])) + list(slots.get("negatives", []))
    cap = kit.house["negatives"]["stills_max_terms"]
    if len(negatives) > cap:
        raise CompileError(f"still_prompt: {len(negatives)} negatives exceeds house cap of {cap}")

    lines = [
        f"{slots['shot_type']} of {slots['subject']} {slots['action']} in {slots['setting']}.",
        f"Style: {style_block}",
    ]

    # Handle per-beat mood from caller, if provided and non-empty
    per_beat_mood = slots.get("mood", "").strip() if slots.get("mood") else None
    if per_beat_mood:
        violations = find_prompt_violations(per_beat_mood, kit)
        if violations:
            raise CompileError(f"still_prompt: per-beat mood would leak brand content: {'; '.join(violations)}")
        lines.append(f"Mood: {per_beat_mood}.")

    if accents:
        lines.append(accents)
    if negatives:
        lines.append("Negative: " + ", ".join(negatives) + ".")
    for ref in slots.get("continuity_refs", []):
        lines.append(f"Continuity reference image attached: {ref}")

    text = "\n".join(lines)
    violations = find_prompt_violations(text, kit)
    if violations:
        raise CompileError(f"{kit.name}: still_prompt would leak brand content: {'; '.join(violations)}")

    style_hash = _text_hash(style_block) if style_block else None
    return StillPromptResult(text=text, style_block_version=kit.stills_style_block.version, style_block_hash=style_hash)


def motion_prompt(slots: dict[str, Any], kit: BrandKit, look: Look | None = None) -> str:
    """Build one motion prompt. `slots`: camera and pacing (each: the beat's own value, else
    the look's/kit's default, else the house neutral default -- never a hard failure, since a
    Brand System kit leaves both to the beat), subject_motion, static, optionally negatives
    (list[str]). Never restates style/lighting/palette — the start frame from `still_prompt`
    is the anchor — but still refuses while the kit's style block is pending (T32), like
    `still_prompt`."""
    _require_style_block(kit, look)
    house_defaults = kit.house.get("motion_prompt", {}).get("defaults", {})
    camera = slots.get("camera") or (look.camera_personality if (look and look.camera_personality) else (
        kit.video_camera_personality.text if kit.video_camera_personality.status == "filled" else None)) \
        or house_defaults.get("camera")
    pacing = slots.get("pacing") or (
        kit.video_pacing_default.text if kit.video_pacing_default.status == "filled" else None) \
        or house_defaults.get("pacing")
    for name, val in (("camera", camera), ("subject_motion", slots.get("subject_motion")),
                       ("static", slots.get("static")), ("pacing", pacing)):
        if not val:
            raise CompileError(f"motion_prompt: slots['{name}'] is required (and no kit/look default is filled)")

    negatives = list(slots.get("negatives", []))
    cap = kit.house["negatives"]["video_max_terms"]
    if len(negatives) > cap:
        raise CompileError(f"motion_prompt: {len(negatives)} negatives exceeds house cap of {cap}")

    forbidden = kit.house["motion_design"]["forbidden"]
    for term in (camera, slots["subject_motion"]):
        for f in forbidden:
            if f.lower() in term.lower():
                raise CompileError(f"motion_prompt: '{f}' is forbidden by house/kit motion rules")

    lines = [
        f"Camera: {camera}.",
        f"Subject motion: {slots['subject_motion']}.",
        f"Static: {slots['static']}.",
        f"Pacing: {pacing}.",
    ]
    if negatives:
        lines.append("Negative: " + ", ".join(negatives) + ".")

    text = "\n".join(lines)
    violations = find_prompt_violations(text, kit)
    if violations:
        raise CompileError(f"{kit.name}: motion_prompt would leak brand content: {'; '.join(violations)}")
    return text


def _colour_hex_map(kit: BrandKit) -> dict[str, str]:
    return {role: c.hex for role, c in kit.core_colours.items() if c.status == "filled" and c.hex}


def compiled_ui_shades(kit: BrandKit) -> dict[str, str]:
    """Derived shades, with any explicit `animation.css_vars` override of the same key
    name winning (this is how Acme's recorded brand.css values survive unchanged)."""
    shades = derive_ui_shades(_colour_hex_map(kit), kit.core_world_tone)
    for key, var in kit.animation_css_vars.items():
        if key in shades and var.status == "filled" and var.value:
            shades[key] = var.value
    return shades


def animation_brief(kit: BrandKit, extra: dict[str, Any] | None = None, look: Look | None = None) -> str:
    """Build a JSON brief for the HyperFrames agent: tokens (hex, font families), logo
    paths + placements, and the kit's craft rules. Unlike still/motion prompts, this
    DELIBERATELY contains hex codes and font names — it drives literal HTML/CSS, not an
    image-generation model — so it is never run through `find_prompt_violations`."""
    caption_style = dict(kit.animation_caption_style.__dict__)
    if look and look.caption_style:
        caption_style.update(look.caption_style)

    brief = {
        "name": kit.core_identity_name.text or kit.name,
        "palette": {k: {"name": c.name_plain, "hex": c.hex} for k, c in kit.core_colours.items() if c.status == "filled"},
        "ui_shades": compiled_ui_shades(kit),
        "css_vars": {k: v.value for k, v in kit.animation_css_vars.items() if v.status == "filled"},
        "type": {k: {"family": t.family, "source": t.source} for k, t in kit.core_typography.items() if t.status == "filled"},
        "logos": {
            k: {"file": l.file, "clear_space": l.clear_space, "min_size_px": l.min_size_px,
                "placements": {a: {"position": p.position, "inset_px": p.inset_px, "height_px": p.height_px}
                               for a, p in l.placements.items()}}
            for k, l in kit.core_logos.items() if l.status == "filled"
        },
        "grid_safe_areas": kit.animation_grid_safe_areas.text,
        "easing": kit.animation_easing.text,
        "durations": kit.animation_durations.text,
        "colour_ratio": kit.animation_colour_ratio.text,
        "caption_style": caption_style,
        "house_motion_design": kit.house["motion_design"],
        "house_safe_areas": kit.house["safe_areas"],
        "names": {"official": kit.core_names_official.items, "products": kit.core_names_products.items},
    }
    if extra:
        brief["extra"] = extra
    return json.dumps(brief, indent=2)


def style_test_prompts(kit: BrandKit, look: Look | None = None) -> list[StillPromptResult]:
    """Six still prompts for deliberately unrelated subjects, built from the kit/look's
    style block — prompts only, NO generation — so a human can run them and judge family
    resemblance. See docs/BRAND-KIT.md."""
    return [still_prompt(dict(slots), kit, look) for slots in TEST_STYLE_SUBJECTS]


def writer_context(kit: BrandKit, look: Look | None = None) -> dict[str, str]:
    """Build a context dict for the agent that writes beat briefs and motion prompts.
    Returns {"identity", "personality", "world", "accents", "camera_personality"} as
    plain text — the kit's defaults for accents/camera_personality unless overridden by
    look."""
    who = kit.core_who_they_serve.text or ""
    what = kit.core_what_they_do.text or ""
    identity = " ".join(p for p in (what, f"Serves {who}." if who else "") if p).strip()

    is_list = ", ".join(kit.core_personality_is.items)
    voice = kit.core_personality_voice.text or ""
    personality = " ".join(p for p in (f"Is: {is_list}." if is_list else "", voice) if p).strip()

    world_parts = []
    for label, lst in (("places", kit.core_world_places), ("people", kit.core_world_people),
                        ("objects", kit.core_world_objects), ("textures", kit.core_world_textures)):
        if lst.items:
            world_parts.append(f"{label}: {', '.join(lst.items)}")
    world = " | ".join(world_parts)

    accents = look.accents if (look and look.accents) else (
        kit.stills_accents.text if kit.stills_accents.status == "filled" else "")

    camera = look.camera_personality if (look and look.camera_personality) else (
        kit.video_camera_personality.text if kit.video_camera_personality.status == "filled" else "")

    return {
        "identity": identity,
        "personality": personality,
        "world": world,
        "accents": accents,
        "camera_personality": camera,
    }


def _text_hash(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


# `artifacts.py` (brand.css/design.md/captions.json/qa_checklist.md/kit.json/compile_kit)
# imports `compiled_ui_shades`/`writer_context` from here; re-exported below so existing
# callers (`from brandkit.compile import compile_css, compile_kit, ...`) keep working
# without caring that the artifact writers live in their own module (kept small per
# AGENTS.md's ~400-line file guidance).
from .artifacts import (  # noqa: E402  (must follow the definitions artifacts.py imports)
    compile_captions, compile_css, compile_design_md, compile_kit, compile_kit_json,
    compile_qa_checklist,
)

__all__ = [
    "CompileError", "StillPromptResult", "find_prompt_violations", "still_prompt",
    "motion_prompt", "animation_brief", "compiled_ui_shades", "style_test_prompts",
    "writer_context", "compile_css", "compile_design_md", "compile_captions",
    "compile_qa_checklist", "compile_kit_json", "compile_kit",
]
