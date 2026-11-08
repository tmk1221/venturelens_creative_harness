from brandkit.schema import BrandKit
from brandkit.status import status_report
from .conftest import DEMO_KIT_DIR, REPO_ROOT, TEMPLATE_KIT_DIR, copy_brand_system, write_minimal_kit


def test_status_report_all_filled_for_minimal_kit(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    report = status_report(kit)
    assert report["kit"] == "acme"
    pending_fields = {p["field"] for p in report["pending"]}
    # fixture leaves animation.sfx_palette / animation.grid_safe_areas pending on purpose
    assert "animation.sfx_palette" in pending_fields
    assert "animation.grid_safe_areas" in pending_fields
    assert report["counts"]["pending"] == len(pending_fields)
    assert all("blocks" in p and p["blocks"] for p in report["pending"])


def test_status_report_pending_field_has_blocking_note(tmp_path):
    kit_dir = write_minimal_kit(tmp_path, {"core": {"logos": {"mark": {
        "file": None, "placements": {}, "status": "pending",
    }}}})
    kit = BrandKit.load(kit_dir)
    report = status_report(kit)
    pending_paths = {p["field"]: p["blocks"] for p in report["pending"]}
    assert "core.logos.mark" in pending_paths
    assert "overlay" in pending_paths["core.logos.mark"].lower() or "composite" in pending_paths["core.logos.mark"].lower()


def test_status_report_demo_brand_system_is_confirmed_and_beat_fields_pending():
    kit = BrandKit.load(DEMO_KIT_DIR)
    report = status_report(kit)
    # brand-kit.json says guessed: false -- nothing in the demo Brand System is a first guess
    assert report["counts"]["guessed"] == 0
    for field in ("stills.style_block", "core.colours.accent", "core.logos.lockup", "core.logos.mark",
                  "core.typography.heading"):
        assert field in report["filled"]
    # world and camera moved to the beat in 31f5cdd: pending, each with what it blocks
    pending = {p["field"]: p["blocks"] for p in report["pending"]}
    assert "video.camera_personality" in pending and "camera" in pending["video.camera_personality"]
    assert "core.world.places" in pending


def test_a_guessed_brand_system_has_no_field_reported_confirmed(tmp_path):
    # T33: `init --from` marks the whole kit guessed, so lists and the style block a site
    # drafted read as guessed too, never as confirmed `filled`.
    kit_dir = copy_brand_system(DEMO_KIT_DIR, tmp_path, meta={"guessed": True})
    report = status_report(BrandKit.load(kit_dir))
    assert report["filled"] == []
    for field in ("core.personality.is", "core.names.official", "stills.style_block", "animation.caption_style"):
        assert field in report["guessed"]


def test_status_report_lists_guessed_fields_of_a_guessed_brand_system(tmp_path):
    kit_dir = copy_brand_system(TEMPLATE_KIT_DIR, tmp_path, meta={
        "guessed": True, "identity": {"name": "Acme", "what_they_do": None, "who_they_serve": None}})
    report = status_report(BrandKit.load(kit_dir))
    assert report["counts"]["guessed"] > 0
    for field in ("core.identity.name", "core.colours.accent", "core.typography.heading"):
        assert field in report["guessed"]


def test_status_report_template_has_style_block_and_identity_pending():
    kit = BrandKit.load(TEMPLATE_KIT_DIR)
    report = status_report(kit)
    assert report["counts"]["guessed"] == 0
    pending = {p["field"]: p["blocks"] for p in report["pending"]}
    for field in ("stills.style_block", "core.identity.name", "core.identity.what_they_do",
                  "core.identity.who_they_serve", "core.personality.is", "core.personality.voice"):
        assert field in pending
    assert "still_prompt and motion_prompt refuse" in pending["stills.style_block"]
