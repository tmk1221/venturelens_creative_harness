import pytest
import yaml

from brandkit.look import Look, LookError


def _write(tmp_path, data, name="episode-1.yaml"):
    p = tmp_path / name
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    return p


def test_look_loads_allowed_overrides(tmp_path):
    path = _write(tmp_path, {
        "name": "episode-1",
        "style_block": "grainy overexposed daylight",
        "accents": "orange flash on a prop",
        "camera_personality": "quick handheld",
        "caption_style": {"max_words": 4},
    })
    look = Look.load(path)
    assert look.name == "episode-1"
    assert look.style_block == "grainy overexposed daylight"
    assert look.accents == "orange flash on a prop"
    assert look.camera_personality == "quick handheld"
    assert look.caption_style == {"max_words": 4}


def test_look_defaults_name_to_filename(tmp_path):
    path = _write(tmp_path, {"style_block": "x"}, name="my-series.yaml")
    look = Look.load(path)
    assert look.name == "my-series"


def test_look_rejects_disallowed_field(tmp_path):
    # a look may not touch animation.type/logos/palette — only caption_style within animation
    path = _write(tmp_path, {"name": "bad", "logos": {"primary": {"file": "x.svg"}}})
    with pytest.raises(LookError, match="may not override"):
        Look.load(path)


def test_look_rejects_palette_override(tmp_path):
    path = _write(tmp_path, {"name": "bad", "palette": {"accent": {"hex": "#000000"}}})
    with pytest.raises(LookError, match="may not override"):
        Look.load(path)


def test_look_missing_file(tmp_path):
    with pytest.raises(LookError, match="no look file"):
        Look.load(tmp_path / "nope.yaml")
