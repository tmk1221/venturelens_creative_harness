from brandkit.lint import lint_composition, lint_prompt
from brandkit.schema import BrandKit
from .conftest import MARK_SVG


def _write_comp(tmp_path, name, html, link_brand_css=True, logo_bytes=None):
    comp = tmp_path / name
    (comp / "assets").mkdir(parents=True)
    if link_brand_css:
        (comp / "assets" / "brand.css").write_text(":root{}")
    if logo_bytes is not None:
        (comp / "assets" / "mark.svg").write_bytes(logo_bytes)
    (comp / "index.html").write_text(html, encoding="utf-8")
    return comp


GOOD_HTML = """<html><head><link rel="stylesheet" href="assets/brand.css"></head>
<body style="background:#F0F0F0">
<div style="font-family: 'Acme Sans', sans-serif; color:#111111">Hello</div>
<span style="color:#FF6600">Acme mascot moment</span>
</body></html>"""


def test_lint_pass_clean_composition(minimal_kit_dir, tmp_path):
    kit = BrandKit.load(minimal_kit_dir)
    comp = _write_comp(tmp_path, "good", GOOD_HTML, logo_bytes=MARK_SVG)
    report = lint_composition(kit, comp)
    assert report["flags"] == []


def test_lint_fails_off_palette_hex(minimal_kit_dir, tmp_path):
    kit = BrandKit.load(minimal_kit_dir)
    html = GOOD_HTML.replace("#FF6600", "#123456")
    comp = _write_comp(tmp_path, "bad-hex", html)
    report = lint_composition(kit, comp)
    kinds = {f["kind"] for f in report["flags"]}
    assert "palette" in kinds


def test_lint_allows_derived_ui_shade_hex(minimal_kit_dir, tmp_path):
    from brandkit.compile import compiled_ui_shades
    kit = BrandKit.load(minimal_kit_dir)
    ground_hex = compiled_ui_shades(kit)["ground"]
    html = GOOD_HTML.replace("#F0F0F0", ground_hex)
    comp = _write_comp(tmp_path, "shade-ok", html)
    report = lint_composition(kit, comp)
    kinds = {f["kind"] for f in report["flags"]}
    assert "palette" not in kinds


def test_lint_fails_disallowed_font(minimal_kit_dir, tmp_path):
    kit = BrandKit.load(minimal_kit_dir)
    html = GOOD_HTML.replace("Acme Sans", "Comic Sans MS")
    comp = _write_comp(tmp_path, "bad-font", html)
    report = lint_composition(kit, comp)
    kinds = {f["kind"] for f in report["flags"]}
    assert "font" in kinds


def test_lint_fails_brand_css_not_linked(minimal_kit_dir, tmp_path):
    kit = BrandKit.load(minimal_kit_dir)
    comp = _write_comp(tmp_path, "no-link", GOOD_HTML, link_brand_css=False)
    # strip the link tag itself
    (comp / "index.html").write_text(GOOD_HTML.replace(
        '<link rel="stylesheet" href="assets/brand.css">', ""), encoding="utf-8")
    report = lint_composition(kit, comp)
    kinds = {f["kind"] for f in report["flags"]}
    assert "adopt" in kinds


def test_lint_fails_logo_hash_changed(minimal_kit_dir, tmp_path):
    kit = BrandKit.load(minimal_kit_dir)
    comp = _write_comp(tmp_path, "bad-logo", GOOD_HTML, logo_bytes=MARK_SVG + b"<!-- tampered -->")
    report = lint_composition(kit, comp)
    kinds = {f["kind"] for f in report["flags"]}
    assert "logo" in kinds


def test_lint_passes_when_logo_not_copied_in(minimal_kit_dir, tmp_path):
    # a composition that doesn't carry its own copy of the logo shouldn't be flagged for it
    kit = BrandKit.load(minimal_kit_dir)
    comp = _write_comp(tmp_path, "no-logo-copy", GOOD_HTML)
    report = lint_composition(kit, comp)
    kinds = {f["kind"] for f in report["flags"]}
    assert "logo" not in kinds


# ---- T20: unknown on-screen names WARN, never fail (positive-only) --------------------

def test_lint_warns_on_unknown_name_never_fails(minimal_kit_dir, tmp_path):
    kit = BrandKit.load(minimal_kit_dir)
    html = GOOD_HTML.replace("Hello", "Hello Invented Product")
    comp = _write_comp(tmp_path, "unknown-name", html)
    report = lint_composition(kit, comp)
    assert report["flags"] == []  # never fails
    assert any("Invented Product" in w["detail"] for w in report["warnings"])


def test_lint_no_warning_for_a_known_product_name(minimal_kit_dir, tmp_path):
    kit = BrandKit.load(minimal_kit_dir)
    html = GOOD_HTML.replace("Hello", "Hello Acme Sprocket")
    comp = _write_comp(tmp_path, "known-name", html)
    report = lint_composition(kit, comp)
    assert not any("Acme Sprocket" in w["detail"] for w in report["warnings"])


def test_lint_missing_index_html(minimal_kit_dir, tmp_path):
    kit = BrandKit.load(minimal_kit_dir)
    comp = tmp_path / "empty"
    comp.mkdir()
    report = lint_composition(kit, comp)
    kinds = {f["kind"] for f in report["flags"]}
    assert "missing" in kinds


# ---- lint_prompt -----------------------------------------------------------------------

def test_lint_prompt_flags_hex(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    flags = lint_prompt("a wall painted #FF6600", kit)
    assert flags


def test_lint_prompt_flags_font_name(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    flags = lint_prompt("set in Acme Sans", kit)
    assert flags


def test_lint_prompt_flags_brand_word(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    flags = lint_prompt("an Acme storefront", kit)
    assert flags


def test_lint_prompt_clean_text_has_no_flags(minimal_kit_dir):
    kit = BrandKit.load(minimal_kit_dir)
    flags = lint_prompt("bright even daylight, plain backdrop", kit)
    assert flags == []
