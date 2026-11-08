import json

import pytest

from brandkit.design_system import token_value
from brandkit.fetch import extract_colour_frequencies, extract_font_families, fetch_site
from brandkit.generate import FakeTextProvider, GenerateError, assign_colour_roles, init_from_url
from brandkit.schema import BrandKit
from .conftest import TEMPLATE_KIT_DIR

FIXTURE_CSS = """
:root {
  --brand-cream: #F1EEE8;
  --brand-charcoal: #16161A;
  --brand-ochre: #B5662A;
}
body { background: var(--brand-cream); font-family: "Space Grotesk", sans-serif; }
h1 { font-family: "Space Grotesk", sans-serif; color: var(--brand-charcoal); }
p { font-family: "Inter", sans-serif; }
"""

FIXTURE_HTML = f"""<!doctype html>
<html><head>
<title>Acme Support Co</title>
<meta name="description" content="Calm, capable IT support for small businesses.">
<link rel="stylesheet" href="/style.css">
</head><body>
<img class="site-logo" src="/logo.svg" alt="Acme logo">
<h1>We keep your business running</h1>
</body></html>
"""

FIXTURE_LOGO_SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><circle r="4"/></svg>'


def _fake_http_get(fixtures: dict):
    def get(url: str) -> bytes:
        for suffix, payload in fixtures.items():
            if url.endswith(suffix):
                return payload
        raise AssertionError(f"unexpected fetch of {url} (test must never touch the network)")
    return get


def _fixtures():
    return {
        "acme.example/": FIXTURE_HTML.encode("utf-8"),
        "/style.css": FIXTURE_CSS.encode("utf-8"),
        "/logo.svg": FIXTURE_LOGO_SVG,
    }


TEXT_DRAFT = json.dumps({
    "what_they_do": "Provides calm, capable IT support",
    "who_they_serve": "small businesses",
    "personality_is": ["calm", "precise"],
    "personality_voice": "Reassuring and plain-spoken.",
    "world_places": ["a tidy server closet"],
    "world_people": ["a technician mid-repair"],
    "world_objects": ["a laptop"],
    "world_textures": ["brushed metal"],
    "products": [],
    "style_block": "soft even daylight, clean digital capture, normal lens, tidy uncluttered rooms",
    "accents": "one ochre object in the frame",
    "camera_personality": "calm, locked-off shots",
})


# ---- fetch.py -----------------------------------------------------------------------

def test_fetch_site_never_touches_the_network():
    snap = fetch_site("http://acme.example/", http_get=_fake_http_get(_fixtures()))
    assert snap.title == "Acme Support Co"
    assert "Space Grotesk" in snap.css
    assert snap.logo_bytes == FIXTURE_LOGO_SVG or b"<svg" in (snap.logo_bytes or b"")
    assert "keep your business running" in snap.hero_text


def test_extract_colour_frequencies_prefers_custom_properties():
    hexes = extract_colour_frequencies(FIXTURE_CSS)
    assert "#F1EEE8" in hexes
    assert "#16161A" in hexes
    assert "#B5662A" in hexes


def test_extract_font_families_skips_generics():
    fonts = extract_font_families(FIXTURE_CSS)
    assert "Space Grotesk" in fonts
    assert "sans-serif" not in fonts


def test_assign_colour_roles_picks_light_and_dark_neutral():
    roles = assign_colour_roles(["#F1EEE8", "#16161A", "#B5662A"])
    assert roles["light_neutral"] == "#F1EEE8"
    assert roles["dark_neutral"] == "#16161A"
    assert roles["accent"] == "#B5662A"


def test_assign_colour_roles_pads_when_too_few():
    roles = assign_colour_roles(["#111111"])
    assert len(roles) >= 3


# ---- init_from_url: end-to-end, no network, no real agent CLI -------------------------

def test_init_from_url_produces_a_loadable_all_guessed_kit(tmp_path):
    kits_root = tmp_path / "kits"
    kits_root.mkdir()
    dest = init_from_url(
        "acmesupport", "http://acme.example/", kits_root, TEMPLATE_KIT_DIR,
        http_get=_fake_http_get(_fixtures()), text_provider=FakeTextProvider(TEXT_DRAFT),
    )
    assert dest == kits_root / "acmesupport"
    kit = BrandKit.load(dest)

    assert kit.name == "acmesupport"
    assert kit.core_identity_name.text == "Acme Support Co"
    assert kit.core_what_they_do.guessed is True

    assert kit.core_colours["light_neutral"].hex == "#F1EEE8"
    assert kit.core_colours["dark_neutral"].hex == "#16161A"
    assert kit.core_colours["accent"].hex == "#B5662A"
    assert all(c.guessed for c in kit.core_colours.values())

    assert kit.core_typography["heading"].family == "Space Grotesk"
    assert kit.core_typography["heading"].guessed is True

    assert kit.core_logos["primary"].status == "filled"
    assert (dest / kit.core_logos["primary"].file).is_file()

    assert kit.stills_style_block.status == "filled"
    assert kit.stills_style_block.text == json.loads(TEXT_DRAFT)["style_block"]

    assert kit.core_sources[0]["kind"] == "website"
    assert kit.core_sources[0]["ref"] == "http://acme.example/"


def _tokens(kit_dir):
    return json.loads((kit_dir / "design-system" / "tokens.json").read_text(encoding="utf-8"))


def test_init_from_url_site_without_a_primary_colour_no_keyerror(tmp_path):
    # Regression (T32): three site colours give light/dark neutral + accent and no primary;
    # generate.py used to read roles["primary"] and raise KeyError. The primary role now
    # resolves through brand-kit.json to the template's primary token, kept as-is.
    template_tokens = _tokens(TEMPLATE_KIT_DIR)
    dest = init_from_url("acmesupport", "http://acme.example/", tmp_path, TEMPLATE_KIT_DIR,
                         http_get=_fake_http_get(_fixtures()), text_provider=FakeTextProvider(TEXT_DRAFT))
    tokens = _tokens(dest)
    kit = BrandKit.load(dest)
    assert kit.core_colours["primary"].hex == token_value(template_tokens, "primary").upper()
    assert token_value(tokens, "on-primary") == "#ffffff"  # template primary is near-black
    assert token_value(tokens, "surface") == "#f1eee8"     # light_neutral -> its token, light theme
    assert token_value(tokens, "surface", "dark") == token_value(template_tokens, "surface", "dark")


def test_init_from_url_sets_on_primary_against_the_sites_primary(tmp_path):
    css = """:root { --a: #FFFFFF; --b: #111111; --c: #B5662A; --d: #F5D76E; --e: #336699; }
    .x { color: #B5662A; background: #F5D76E; border-color: #336699; }"""
    fixtures = dict(_fixtures(), **{"/style.css": css.encode("utf-8")})
    dest = init_from_url("acmesupport", "http://acme.example/", tmp_path, TEMPLATE_KIT_DIR,
                         http_get=_fake_http_get(fixtures), text_provider=FakeTextProvider(TEXT_DRAFT))
    kit = BrandKit.load(dest)
    assert kit.core_colours["primary"].hex == "#F5D76E"
    assert kit.core_colours["secondary"].hex == "#336699"
    # a light primary takes the dark neutral (ink) for text on it, not white
    assert token_value(_tokens(dest), "on-primary") == "#111111"


def test_init_from_url_refuses_existing_client(tmp_path):
    kits_root = tmp_path / "kits"
    kits_root.mkdir()
    (kits_root / "dupe").mkdir()
    with pytest.raises(GenerateError, match="already exists"):
        init_from_url("dupe", "http://acme.example/", kits_root, TEMPLATE_KIT_DIR,
                       http_get=_fake_http_get(_fixtures()), text_provider=FakeTextProvider(TEXT_DRAFT))
