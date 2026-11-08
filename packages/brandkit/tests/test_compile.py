import json

import pytest

from brandkit.compile import (
    CompileError, animation_brief, compile_kit, compiled_ui_shades, find_prompt_violations,
    motion_prompt, still_prompt, style_test_prompts, writer_context,
)
from brandkit.design_system import CSS_VARS, token_value
from brandkit.look import Look
from brandkit.schema import BrandKit
from .conftest import (
    DEMO_KIT_DIR, TEMPLATE_KIT_DIR, brand_system_files, copy_brand_system, write_minimal_kit,
)


def test_compiling_demo_kit_works(tmp_path):
    kit = BrandKit.load(DEMO_KIT_DIR)
    out = tmp_path / "out"
    written = compile_kit(kit, out)
    for name in ("brand.css", "design.md", "captions.json", "qa_checklist.md", "kit.json", "writer_context.json"):
        assert name in written
        assert written[name].is_file()


def test_brand_css_has_color_and_font_vars(minimal_kit_dir, tmp_path):
    kit = BrandKit.load(minimal_kit_dir)
    written = compile_kit(kit, tmp_path / "out")
    css = written["brand.css"].read_text()
    assert "--accent: #FF6600;" in css
    assert "--hairline: #E6E1D8;" in css
    assert '--font-heading: "Acme Sans", sans-serif;' in css
    assert "--ease: power2.out;" in css
    assert "--safe-title-16x9: 0.8;" in css


def test_brand_css_includes_derived_ui_shades(minimal_kit_dir, tmp_path):
    kit = BrandKit.load(minimal_kit_dir)
    written = compile_kit(kit, tmp_path / "out")
    css = written["brand.css"].read_text()
    for key in ("ground", "surface", "surface_2", "surface_3", "ink", "ink_dim", "ink_faint", "accent_wash"):
        assert f"--{key.replace('_', '-')}:" in css


def test_demo_brand_css_carries_its_design_system_tokens(tmp_path):
    # Colour roles come from brand-kit.json -> tokens.json; the surface/ink/line tokens win over
    # the generated UI shades of the same name, so brand.css matches the Brand System.
    kit = BrandKit.load(DEMO_KIT_DIR)
    tokens, meta = brand_system_files(DEMO_KIT_DIR)
    written = compile_kit(kit, tmp_path / "out")
    css = written["brand.css"].read_text()
    for role, spec in meta["colours"].items():
        assert f"--{role.replace('_', '-')}: {token_value(tokens, spec['token']).upper()};" in css
    for key in ("surface", "surface_2", "ink_dim", "hairline"):
        assert f"--{key.replace('_', '-')}: {token_value(tokens, CSS_VARS[key])};" in css
    assert '--font-heading: "Manrope", sans-serif;' in css


def test_design_md_frontmatter_has_colors_and_typography(minimal_kit_dir, tmp_path):
    import yaml
    kit = BrandKit.load(minimal_kit_dir)
    written = compile_kit(kit, tmp_path / "out")
    text = written["design.md"].read_text()
    assert text.startswith("---\n")
    fm_text = text.split("---\n")[1]
    fm = yaml.safe_load(fm_text)
    assert fm["colors"]["accent"] == "#FF6600"
    assert fm["typography"]["heading"]["fontFamily"] == "Acme Sans"
    assert "16:9" in fm["logos"]["mark"]["placements"]


def test_captions_json_keys_match_what_build_captions_reads(minimal_kit_dir, tmp_path):
    kit = BrandKit.load(minimal_kit_dir)
    written = compile_kit(kit, tmp_path / "out")
    data = json.loads(written["captions.json"].read_text())
    assert data["fonts"]["body"] == "Acme Sans"
    assert data["palette_dark"]["brand"] == "#FF6600"
    assert data["palette_light"]["brand"] == "#FF6600"


def test_qa_checklist_has_house_items_and_kit_extras(tmp_path):
    kit_dir = write_minimal_kit(tmp_path, {"qa_checklist_extra": ["Screens stay blank or composited in post."]})
    kit = BrandKit.load(kit_dir)
    written = compile_kit(kit, tmp_path / "out")
    text = written["qa_checklist.md"].read_text()
    assert "No stray legible text" in text
    assert "Screens stay blank or composited in post." in text


def test_kit_json_has_hash_and_version(minimal_kit_dir, tmp_path):
    kit = BrandKit.load(minimal_kit_dir)
    written = compile_kit(kit, tmp_path / "out")
    data = json.loads(written["kit.json"].read_text())
    assert data["hash"] == kit.kit_hash()
    assert data["version"] == "1"
    assert data["name"] == "acme"


def test_compile_is_deterministic(minimal_kit_dir, tmp_path):
    kit = BrandKit.load(minimal_kit_dir)
    out_a = compile_kit(kit, tmp_path / "a")
    out_b = compile_kit(kit, tmp_path / "b")
    for name in out_a:
        assert out_a[name].read_bytes() == out_b[name].read_bytes()


# ---- still_prompt / motion_prompt / animation_brief: no cross-contamination -----------

_STILL_SLOTS = {"shot_type": "Medium shot", "subject": "a person", "action": "typing at a desk",
                 "setting": "a bright open office"}


def test_still_prompt_is_pure_for_minimal_kit(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    result = still_prompt(_STILL_SLOTS, kit)
    assert find_prompt_violations(result.text, kit) == []
    assert "#" not in result.text
    assert "Acme Sans" not in result.text
    assert "Acme" not in result.text
    assert '"' not in result.text and "'" not in result.text
    assert result.style_block_version == "1"
    assert result.style_block_hash is not None


def test_still_prompt_never_attaches_a_reference_image(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    result = still_prompt(_STILL_SLOTS, kit)
    assert "reference image attached" not in result.text.lower()


def test_still_prompt_passes_through_caller_continuity_refs(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    slots = dict(_STILL_SLOTS, continuity_refs=["cast/agent-sheet.jpg"])
    result = still_prompt(slots, kit)
    assert "Continuity reference image attached: cast/agent-sheet.jpg" in result.text


def test_still_prompt_refuses_when_style_block_pending(tmp_path):
    kit_dir = write_minimal_kit(tmp_path, {"stills": {"style_block": {
        "text": None, "version": None, "derived_from": [], "status": "pending",
    }}})
    kit = BrandKit.load(kit_dir)
    with pytest.raises(CompileError, match="pending"):
        still_prompt(_STILL_SLOTS, kit)


def test_still_prompt_refuses_too_many_negatives(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    slots = dict(_STILL_SLOTS, negatives=["a"] * 9)
    with pytest.raises(CompileError, match="cap"):
        still_prompt(slots, kit)


def test_still_prompt_applies_look_overrides(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    look = Look(name="episode-1", style_block="hand-tinted overexposed daylight, grainy medium format film",
                accents="upbeat orange flash on a single prop")
    result = still_prompt(_STILL_SLOTS, kit, look)
    assert "hand-tinted overexposed daylight" in result.text
    assert "upbeat orange flash" in result.text


# ---- T20: house never_generate defaults + per-beat allow lift -------------------------

def test_still_prompt_appends_house_never_generate_defaults(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    result = still_prompt(_STILL_SLOTS, kit)
    assert "legible on-screen text" in result.text
    assert "a logo" in result.text
    assert "a screen or UI surface" in result.text


def test_still_prompt_allow_lifts_matching_house_default(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    slots = dict(_STILL_SLOTS, allow=["text"])
    result = still_prompt(slots, kit)
    assert "legible on-screen text" not in result.text
    assert "a logo" in result.text  # not lifted, still forced


def test_motion_prompt_is_pure(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    text = motion_prompt({"camera": "slow dolly in", "subject_motion": "hand reaches for a mug",
                           "static": "the desk and monitor", "pacing": "subtle"}, kit)
    assert find_prompt_violations(text, kit) == []
    assert "Camera: slow dolly in." in text


def test_motion_prompt_defaults_camera_and_pacing_from_kit(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    text = motion_prompt({"subject_motion": "hand reaches for a mug", "static": "the desk"}, kit)
    assert "Camera: slow, deliberate moves." in text
    assert "Pacing: subtle." in text


def test_motion_prompt_never_fails_on_missing_camera_or_pacing():
    # The demo Brand System leaves video.camera_personality/pacing_default to the beat
    # (31f5cdd): a beat that names neither gets the house neutral defaults, not an error.
    kit = BrandKit.load(DEMO_KIT_DIR)
    assert kit.video_camera_personality.status == "pending"
    text = motion_prompt({"subject_motion": "hand reaches for a mug", "static": "the desk"}, kit)
    assert "Camera: locked-off, steady frame." in text
    assert "Pacing: subtle." in text


def test_motion_prompt_beat_camera_beats_look_and_kit_defaults(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    look = Look(name="series", camera_personality="quick handheld")
    slots = {"subject_motion": "hand reaches for a mug", "static": "the desk"}
    assert "Camera: quick handheld." in motion_prompt(slots, kit, look)
    assert "Camera: slow push-in." in motion_prompt({**slots, "camera": "slow push-in"}, kit, look)


def test_motion_prompt_rejects_house_forbidden_term(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    with pytest.raises(CompileError, match="forbidden"):
        motion_prompt({"camera": "static", "subject_motion": "logo does a slow spin",
                        "static": "background", "pacing": "subtle"}, kit)


def test_motion_prompt_refuses_too_many_negatives(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    with pytest.raises(CompileError, match="cap"):
        motion_prompt({"camera": "static", "subject_motion": "a hand waves",
                        "static": "background", "pacing": "subtle",
                        "negatives": ["a"] * 7}, kit)


def test_template_still_prompt_blocked_pending_style_block():
    # The template's imagery.md holds a [placeholder] under ## stills.style_block: pending.
    kit = BrandKit.load(TEMPLATE_KIT_DIR)
    with pytest.raises(CompileError, match="stills.style_block is pending"):
        still_prompt(_STILL_SLOTS, kit)


def test_template_motion_prompt_blocked_pending_style_block():
    kit = BrandKit.load(TEMPLATE_KIT_DIR)
    with pytest.raises(CompileError, match="stills.style_block is pending"):
        motion_prompt({"camera": "locked-off", "subject_motion": "a hand waves",
                       "static": "background", "pacing": "subtle"}, kit)


def test_brand_system_without_a_style_block_heading_blocks_prompts(tmp_path):
    kit_dir = copy_brand_system(DEMO_KIT_DIR, tmp_path, client="demo")
    (kit_dir / "design-system" / "imagery.md").write_text("# Imagery\n\nNo block yet.\n", encoding="utf-8")
    kit = BrandKit.load(kit_dir)
    assert kit.stills_style_block.status == "pending"
    with pytest.raises(CompileError, match="stills.style_block"):
        still_prompt(_STILL_SLOTS, kit)
    with pytest.raises(CompileError, match="stills.style_block"):
        motion_prompt({"camera": "locked-off", "subject_motion": "a hand waves",
                       "static": "background", "pacing": "subtle"}, kit)
    # a look's own style block is a filled block: it lifts the guard for that look only
    look = Look(name="ep1", style_block="soft window light, normal lens, fine grain")
    assert "soft window light" in still_prompt(_STILL_SLOTS, kit, look).text


def test_animation_brief_contains_hex(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    brief = animation_brief(kit)
    assert "#FF6600" in brief
    data = json.loads(brief)
    assert data["palette"]["accent"]["hex"] == "#FF6600"
    assert "ground" in data["ui_shades"]


def test_still_and_motion_prompts_never_contain_hex(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    still = still_prompt(_STILL_SLOTS, kit)
    motion = motion_prompt({"camera": "static", "subject_motion": "a hand waves",
                             "static": "background", "pacing": "subtle"}, kit)
    assert "#" not in still.text
    assert "#" not in motion


def test_style_test_prompts_returns_six_prompts_no_generation(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    results = style_test_prompts(kit)
    assert len(results) == 6
    for r in results:
        assert find_prompt_violations(r.text, kit) == []


# ---- per-beat mood handling -------------------------------------------------------------------

def test_still_prompt_has_no_mood_line_by_default(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    result = still_prompt(_STILL_SLOTS, kit)
    assert "Mood:" not in result.text


def test_still_prompt_has_mood_line_when_mood_in_slots(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    slots = dict(_STILL_SLOTS, mood="tense")
    result = still_prompt(slots, kit)
    assert "Mood: tense." in result.text


def test_still_prompt_refuses_per_beat_mood_with_hex(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    slots = dict(_STILL_SLOTS, mood="energetic #FF6600")
    with pytest.raises(CompileError, match="per-beat mood would leak brand content"):
        still_prompt(slots, kit)


def test_still_prompt_refuses_per_beat_mood_with_brand_name(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    slots = dict(_STILL_SLOTS, mood="Acme corporate feeling")
    with pytest.raises(CompileError, match="per-beat mood would leak brand content"):
        still_prompt(slots, kit)


def test_demo_still_prompt_is_pure(minimal_kit_dir):
    kit = BrandKit.load(DEMO_KIT_DIR)
    result = still_prompt(_STILL_SLOTS, kit)
    assert find_prompt_violations(result.text, kit) == []
    assert "Kestrel" not in result.text
    assert "typeface" not in result.text
    assert "#" not in result.text
    assert "Mood:" not in result.text  # No mood line unless caller provides one


def test_writer_context_returns_expected_keys(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    ctx = writer_context(kit)
    assert set(ctx.keys()) == {"identity", "personality", "world", "accents", "camera_personality"}
    assert all(isinstance(v, str) for v in ctx.values())
    assert "small manufacturers" in ctx["identity"]
    assert "bright" in ctx["personality"]
    assert "workshop" in ctx["world"]


def test_writer_context_respects_look_overrides(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    look = Look(name="episode-1",
                accents="bright blue pops only",
                camera_personality="fast orbital shots")
    ctx = writer_context(kit, look)
    assert ctx["accents"] == "bright blue pops only"
    assert ctx["camera_personality"] == "fast orbital shots"
    # personality is from kit, not look
    assert "bright" in ctx["personality"]


def test_compiled_ui_shades_respects_explicit_overrides(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    shades = compiled_ui_shades(kit)
    assert shades["hairline"] == "#E6E1D8"  # explicit css_vars override, not the derived value
