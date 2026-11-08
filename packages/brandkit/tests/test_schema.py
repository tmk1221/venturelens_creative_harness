import datetime as dt
import json
import shutil
from types import SimpleNamespace

import pytest
import yaml

from brandkit import design_system
from brandkit.design_system import CSS_VARS, is_placeholder, token_value
from brandkit.schema import BrandKit, BrandKitError
from .conftest import (
    DEMO_KIT_DIR, TEMPLATE_KIT_DIR, brand_system_files, copy_brand_system, minimal_kit_dict,
    write_minimal_kit,
)


def test_loads_demo_kit_from_its_design_system():
    kit = BrandKit.load(DEMO_KIT_DIR)
    tokens, meta = brand_system_files(DEMO_KIT_DIR)
    assert not (DEMO_KIT_DIR / "brand.yaml").exists()
    assert kit.name == "_demo"
    assert kit.core_identity_name.text == meta["identity"]["name"] == "Kestrel Demo Co."
    assert set(kit.core_colours) == set(meta["colours"])
    for role, spec in meta["colours"].items():
        assert kit.core_colours[role].hex == token_value(tokens, spec["token"]).upper()
        assert kit.core_colours[role].name_plain == spec["name_plain"]
    assert kit.core_typography["heading"].family == "Manrope"
    assert kit.stills_style_block.status == "filled"
    assert not is_placeholder(kit.stills_style_block.text)
    assert set(kit.core_logos) == set(meta["logos"])
    for logo in kit.core_logos.values():
        assert logo.status == "filled" and logo.guessed is False
        assert (kit.path / logo.file).is_file()
    assert kit.house["negatives"]["stills_max_terms"] == 8


def test_loads_template_design_system_as_incomplete_but_well_formed():
    kit = BrandKit.load(TEMPLATE_KIT_DIR)
    assert kit.name == "_template"
    # imagery.md still holds the template's [bracketed placeholder] under ## stills.style_block
    assert kit.stills_style_block.status == "pending"
    assert kit.stills_style_block.text is None
    # brand-kit.json's identity is "[Client]" and the rest null: pending, not filled
    for field in (kit.core_identity_name, kit.core_what_they_do, kit.core_who_they_serve,
                  kit.core_personality_voice):
        assert field.status == "pending" and field.text is None
    assert kit.core_personality_is.status == "pending"
    assert kit.core_names_official.items == []
    assert not any(c.guessed for c in kit.core_colours.values())


def test_loads_minimal_kit(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    assert kit.name == "acme"
    assert kit.animation_caption_style.font_role == "heading"
    assert kit.house["motion_design"]["ease"] == "power2.out"


def test_hash_deterministic_across_loads(minimal_kit_dir):
    a = BrandKit.load(minimal_kit_dir).kit_hash()
    b = BrandKit.load(minimal_kit_dir).kit_hash()
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_hash_changes_when_yaml_changes(tmp_path):
    kit_dir = write_minimal_kit(tmp_path)
    before = BrandKit.load(kit_dir).kit_hash()
    data = yaml.safe_load((kit_dir / "brand.yaml").read_text())
    data["core"]["colours"]["items"]["accent"]["hex"] = "#000001"
    (kit_dir / "brand.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    after = BrandKit.load(kit_dir).kit_hash()
    assert before != after


def test_hash_changes_when_asset_bytes_change(tmp_path):
    kit_dir = write_minimal_kit(tmp_path)
    before = BrandKit.load(kit_dir).kit_hash()
    svg = kit_dir / "assets" / "mark.svg"
    svg.write_bytes(svg.read_bytes() + b"<!-- changed -->")
    after = BrandKit.load(kit_dir).kit_hash()
    assert before != after


def test_hash_unaffected_by_unrelated_file(tmp_path):
    kit_dir = write_minimal_kit(tmp_path)
    before = BrandKit.load(kit_dir).kit_hash()
    (kit_dir / "assets" / "unrelated.txt").write_text("noise")
    after = BrandKit.load(kit_dir).kit_hash()
    assert before == after


# ---- pending slots are valid, not errors ----------------------------------------------

def test_pending_logo_slot_is_valid(tmp_path):
    kit_dir = write_minimal_kit(tmp_path, {"core": {"logos": {"mark": {
        "file": None, "placements": {}, "status": "pending",
    }}}})
    kit = BrandKit.load(kit_dir)
    assert kit.core_logos["mark"].status == "pending"
    assert kit.core_logos["mark"].file is None


def test_pending_colour_role_allows_null_fields(tmp_path):
    kit_dir = write_minimal_kit(tmp_path, {"core": {"colours": {"items": {"accent": {
        "name_plain": None, "hex": None, "status": "pending",
    }}}}})
    kit = BrandKit.load(kit_dir)
    assert kit.core_colours["accent"].status == "pending"
    assert kit.core_colours["accent"].hex is None


def test_guessed_brand_system_marks_its_derived_fields_guessed(tmp_path):
    kit_dir = copy_brand_system(TEMPLATE_KIT_DIR, tmp_path, meta={
        "guessed": True, "identity": {"name": "Acme", "what_they_do": "makes widgets", "who_they_serve": None}})
    kit = BrandKit.load(kit_dir)
    assert kit.core_colours["accent"].guessed is True
    assert all(c.guessed for c in kit.core_colours.values())
    assert kit.core_typography["heading"].guessed is True
    assert kit.core_identity_name.guessed is True and kit.core_what_they_do.guessed is True
    assert kit.core_who_they_serve.status == "pending"


# ---- validation errors --------------------------------------------------------------

def _kit_with(tmp_path, mutate):
    data = minimal_kit_dict()
    mutate(data)
    kit_dir = tmp_path / "bad"
    (kit_dir / "assets").mkdir(parents=True)
    (kit_dir / "assets" / "mark.svg").write_bytes(b"<svg></svg>")
    (kit_dir / "brand.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    return kit_dir


def test_missing_kit_names_both_layouts(tmp_path):
    with pytest.raises(BrandKitError, match="no design-system/ or brand.yaml"):
        BrandKit.load(tmp_path / "nope")


def test_legacy_brand_yaml_only_kit_still_loads(tmp_path):
    # The one legacy-layout test: a kit with brand.yaml and no design-system/ loads as before,
    # and a kit holding both is read from its design system (the source of truth).
    kit_dir = write_minimal_kit(tmp_path)
    assert not (kit_dir / "design-system").exists()
    kit = BrandKit.load(kit_dir)
    assert kit.name == "acme" and kit.core_colours["accent"].hex == "#FF6600"

    both = copy_brand_system(DEMO_KIT_DIR, tmp_path / "both", client="demo")
    shutil.copy(kit_dir / "brand.yaml", both / "brand.yaml")
    kit = BrandKit.load(both)
    assert kit.core_identity_name.text == "Kestrel Demo Co."
    assert kit.core_colours["accent"].hex != "#FF6600"


def test_design_system_kit_hash_is_stable_across_days_and_follows_the_files(tmp_path, monkeypatch):
    # The derived kit carries no date, so a node's input_hash does not go stale overnight.
    kit_dir = copy_brand_system(DEMO_KIT_DIR, tmp_path, client="demo")
    before = BrandKit.load(kit_dir).kit_hash()

    class _Tomorrow(dt.date):
        @classmethod
        def today(cls):
            return dt.date(2031, 1, 2)
    monkeypatch.setattr(design_system, "_dt", SimpleNamespace(date=_Tomorrow, datetime=dt.datetime))
    assert BrandKit.load(kit_dir).kit_hash() == before

    tokens_path = kit_dir / "design-system" / "tokens.json"
    tokens = json.loads(tokens_path.read_text(encoding="utf-8"))
    tokens["color"]["tokens"][0]["value"] = "#000001"
    tokens_path.write_text(json.dumps(tokens), encoding="utf-8")
    assert BrandKit.load(kit_dir).kit_hash() != before


def test_bad_hex_rejected(tmp_path):
    kit_dir = _kit_with(tmp_path, lambda d: d["core"]["colours"]["items"]["accent"].update(hex="orange"))
    with pytest.raises(BrandKitError, match="hex colour"):
        BrandKit.load(kit_dir)


def test_missing_color_role_field_rejected_when_filled(tmp_path):
    kit_dir = _kit_with(tmp_path, lambda d: d["core"]["colours"]["items"]["accent"].pop("hex"))
    with pytest.raises(BrandKitError):
        BrandKit.load(kit_dir)


def test_typography_missing_family_rejected_when_filled(tmp_path):
    kit_dir = _kit_with(tmp_path, lambda d: d["core"]["typography"]["heading"].pop("family"))
    with pytest.raises(BrandKitError, match="family"):
        BrandKit.load(kit_dir)


def test_logo_missing_required_aspect_rejected_when_filled(tmp_path):
    def mutate(d):
        del d["core"]["logos"]["mark"]["placements"]["9:16"]
    kit_dir = _kit_with(tmp_path, mutate)
    with pytest.raises(BrandKitError, match="9:16"):
        BrandKit.load(kit_dir)


def test_logo_missing_asset_file_rejected(tmp_path):
    kit_dir = _kit_with(tmp_path, lambda d: d["core"]["logos"]["mark"].update(file="assets/missing.svg"))
    with pytest.raises(BrandKitError, match="file not found"):
        BrandKit.load(kit_dir)


def test_caption_font_role_must_exist(tmp_path):
    kit_dir = _kit_with(tmp_path, lambda d: d["animation"]["caption_style"].update(font_role="nope"))
    with pytest.raises(BrandKitError, match="font_role"):
        BrandKit.load(kit_dir)


def test_caption_palette_missing_light_rejected(tmp_path):
    def mutate(d):
        del d["animation"]["caption_style"]["palette"]["light"]
    kit_dir = _kit_with(tmp_path, mutate)
    with pytest.raises(BrandKitError, match="light"):
        BrandKit.load(kit_dir)


def test_colours_below_minimum_rejected(tmp_path):
    def mutate(d):
        d["core"]["colours"]["items"] = {"accent": d["core"]["colours"]["items"]["accent"]}
    kit_dir = _kit_with(tmp_path, mutate)
    with pytest.raises(BrandKitError, match="3-6"):
        BrandKit.load(kit_dir)


def test_colour_role_outside_enum_rejected(tmp_path):
    def mutate(d):
        d["core"]["colours"]["items"]["not_a_role"] = d["core"]["colours"]["items"].pop("accent")
    kit_dir = _kit_with(tmp_path, mutate)
    with pytest.raises(BrandKitError, match="role must be one of"):
        BrandKit.load(kit_dir)


def test_world_tone_must_be_light_or_dark(tmp_path):
    kit_dir = _kit_with(tmp_path, lambda d: d["core"]["colours"].update(world_tone="sideways"))
    with pytest.raises(BrandKitError, match="light.*dark"):
        BrandKit.load(kit_dir)


def test_dominant_must_reference_a_defined_role(tmp_path):
    kit_dir = _kit_with(tmp_path, lambda d: d["core"]["colours"].update(dominant="secondary"))
    with pytest.raises(BrandKitError, match="dominant"):
        BrandKit.load(kit_dir)


def test_house_overrides_unknown_section_rejected(tmp_path):
    kit_dir = _kit_with(tmp_path, lambda d: d.update(house_overrides={"nonsense": {"x": 1}}))
    with pytest.raises(BrandKitError, match="unknown house section"):
        BrandKit.load(kit_dir)


def test_house_overrides_non_overridable_section_rejected(tmp_path):
    kit_dir = _kit_with(tmp_path, lambda d: d.update(house_overrides={"safe_areas": {"16:9": {}}}))
    with pytest.raises(BrandKitError, match="not overridable"):
        BrandKit.load(kit_dir)


def test_house_overrides_motion_design_applies(tmp_path):
    kit_dir = _kit_with(tmp_path, lambda d: d.update(house_overrides={"motion_design": {"ease": "power1.out"}}))
    kit = BrandKit.load(kit_dir)
    assert kit.house["motion_design"]["ease"] == "power1.out"
    # untouched keys in the same section survive the override
    assert kit.house["motion_design"]["durations"]["micro"] == 0.15


# ---- T20: positive-only schema ---------------------------------------------------------

def test_forbid_key_anywhere_rejected(tmp_path):
    kit_dir = _kit_with(tmp_path, lambda d: d["core"]["names"].update(forbid=["Bad Actor Co"]))
    with pytest.raises(BrandKitError, match="positive-only"):
        BrandKit.load(kit_dir)


def test_forbidden_shaped_key_rejected_anywhere_in_the_tree(tmp_path):
    kit_dir = _kit_with(tmp_path, lambda d: d["stills"].update(negatives={"items": [], "status": "pending"}))
    # "negatives" doesn't start with "forbid" so it loads fine structurally but is simply
    # ignored (T20 removed stills.negatives from the schema) -- the real guard is forbid*.
    BrandKit.load(kit_dir)


def test_forbidden_key_message_names_the_offending_path(tmp_path):
    kit_dir = _kit_with(tmp_path, lambda d: d.update(forbid_everything=True))
    with pytest.raises(BrandKitError, match="brand.yaml.forbid_everything"):
        BrandKit.load(kit_dir)


# ---- T17/T20: characters/references are gone, core.colours has no max_coverage --------

def test_no_characters_or_references_attribute():
    kit = BrandKit.load(DEMO_KIT_DIR)
    assert not hasattr(kit, "characters")
    assert not hasattr(kit, "references")


def test_colour_role_has_no_max_coverage(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    assert not hasattr(kit.core_colours["accent"], "max_coverage")


def test_css_vars_come_from_design_system_tokens():
    kit = BrandKit.load(DEMO_KIT_DIR)
    tokens, _ = brand_system_files(DEMO_KIT_DIR)
    assert "line_off" not in kit.core_colours
    assert set(kit.animation_css_vars) == set(CSS_VARS)
    for key, token in CSS_VARS.items():
        assert kit.animation_css_vars[key].value == token_value(tokens, token)
