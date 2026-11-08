import copy
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_KIT_DIR = REPO_ROOT / "kits" / "_demo"
TEMPLATE_KIT_DIR = REPO_ROOT / "kits" / "_template"

MARK_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'
HERO_JPG = b"\xff\xd8\xff\xe0fake-jpeg-bytes-for-tests"


def minimal_kit_dict() -> dict:
    """A small, fully-filled kit (not the demo kit) for fast unit tests that don't need real
    brand assets. Callers that need real asset files should use `write_minimal_kit`."""
    return {
        "name": "acme",
        "version": "1",
        "core": {
            "identity": {
                "name": {"text": "Acme", "status": "filled", "guessed": False},
                "what_they_do": {"text": "makes widgets", "status": "filled", "guessed": False},
                "who_they_serve": {"text": "small manufacturers", "status": "filled", "guessed": False},
            },
            "colours": {
                "items": {
                    "light_neutral": {"name_plain": "plain white", "hex": "#F0F0F0", "status": "filled", "guessed": False},
                    "dark_neutral": {"name_plain": "near black", "hex": "#111111", "status": "filled", "guessed": False},
                    "accent": {"name_plain": "acme orange", "hex": "#FF6600", "status": "filled", "guessed": False},
                },
                "world_tone": "light",
                "dominant": "light_neutral",
            },
            "typography": {
                "heading": {"family": "Acme Sans", "source": "google", "file": None, "status": "filled", "guessed": False},
                "body": {"family": "Acme Sans", "source": "google", "file": None, "status": "filled", "guessed": False},
                "mono": {"family": "Acme Mono", "source": "google", "file": None, "status": "filled", "guessed": False},
            },
            "logos": {
                "mark": {
                    "file": "assets/mark.svg", "clear_space": 0.2, "min_size_px": 24,
                    "placements": {
                        "16:9": {"position": "top-left", "inset_px": 32, "height_px": 48},
                        "9:16": {"position": "top-center", "inset_px": 24, "height_px": 40},
                    },
                    "status": "filled", "guessed": False,
                }
            },
            "personality": {
                "is": {"items": ["bright", "friendly", "direct"], "status": "filled"},
                "voice": {"text": "Speaks plainly, one idea at a time.", "status": "filled", "guessed": False},
            },
            "world": {
                "places": {"items": ["a small workshop"], "status": "filled"},
                "people": {"items": ["a technician at a bench"], "status": "filled"},
                "objects": {"items": ["a widget", "a toolbox"], "status": "filled"},
                "textures": {"items": ["brushed metal"], "status": "filled"},
            },
            "names": {
                "official": {"items": ["Acme"], "status": "filled"},
                "products": {"items": ["Acme Sprocket"], "status": "filled"},
                "pronunciation": [],
            },
            "sources": [],
        },
        "stills": {
            "style_block": {
                "text": "clean digital capture, soft even light, wide open uncluttered rooms, "
                        "normal lens, relaxed unposed people",
                "version": "1", "derived_from": ["deadbeef"], "status": "filled",
            },
            "accents": {"text": "orange may appear as a small accent on a prop.",
                        "status": "filled", "guessed": False},
        },
        "video": {
            "camera_personality": {"text": "slow, deliberate moves", "status": "filled", "guessed": False},
            "pacing_default": {"text": "subtle", "status": "filled", "guessed": False},
        },
        "animation": {
            "grid_safe_areas": {"text": None, "status": "pending", "guessed": False},
            "easing": {"text": "matches house default", "status": "filled", "guessed": False},
            "durations": {"text": "matches house default", "status": "filled", "guessed": False},
            "colour_ratio": {"text": "60/30/10", "status": "filled", "guessed": False},
            "caption_style": {
                "font_role": "heading",
                "palette": {"dark": {"brand": "#FF6600"}, "light": {"brand": "#FF6600"}},
                "band": 0.9, "max_words": 6, "font_scale": 1.0,
                "status": "filled", "guessed": False,
            },
            "sfx_palette": {"items": [], "status": "pending"},
            "css_vars": {
                "hairline": {"value": "#E6E1D8", "status": "filled", "guessed": True},
            },
        },
        "qa_checklist_extra": [],
    }


def write_minimal_kit(tmp_path: Path, overrides: dict | None = None) -> Path:
    data = minimal_kit_dict()
    if overrides:
        data = _deep_merge(data, overrides)
    kit_dir = tmp_path / "acme"
    (kit_dir / "assets").mkdir(parents=True)
    (kit_dir / "assets" / "mark.svg").write_bytes(MARK_SVG)
    (kit_dir / "brand.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return kit_dir


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@pytest.fixture
def minimal_kit_dir(tmp_path) -> Path:
    return write_minimal_kit(tmp_path)


def copy_brand_system(src: Path, tmp_path: Path, client: str = "acme", meta: dict | None = None) -> Path:
    """Copy a design-system kit (the demo kit or the template) to `tmp_path/<client>/`, optionally
    updating top-level keys of its brand-kit.json. The shipped kits are never edited."""
    import json
    import shutil
    dest = tmp_path / client
    shutil.copytree(src, dest)
    if meta:
        path = dest / "design-system" / "brand-kit.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update(meta)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return dest


def brand_system_files(kit_dir: Path) -> tuple[dict, dict]:
    """(tokens.json, brand-kit.json) of a design-system kit, for asserting against the source."""
    import json
    ds = kit_dir / "design-system"
    return (json.loads((ds / "tokens.json").read_text(encoding="utf-8")),
            json.loads((ds / "brand-kit.json").read_text(encoding="utf-8")))
