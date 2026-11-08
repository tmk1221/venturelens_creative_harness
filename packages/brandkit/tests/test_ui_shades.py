import pytest

from brandkit.ui_shades import (
    SHADE_KEYS, UIShadesError, check_contrast, contrast_ratio, derive_ui_shades, mix,
)

SAMPLE_COLOURS = {"light_neutral": "#F1EEE8", "dark_neutral": "#16161A", "accent": "#B5662A"}


def test_derive_ui_shades_returns_all_keys():
    shades = derive_ui_shades(SAMPLE_COLOURS, "light")
    assert set(shades.keys()) == set(SHADE_KEYS)


def test_derive_ui_shades_light_tone_uses_light_neutral_as_ground():
    shades = derive_ui_shades(SAMPLE_COLOURS, "light")
    assert shades["ground"] == "#F1EEE8"
    assert shades["ink"] == "#16161A"


def test_derive_ui_shades_dark_tone_swaps_ground_and_ink():
    shades = derive_ui_shades(SAMPLE_COLOURS, "dark")
    assert shades["ground"] == "#16161A"
    assert shades["ink"] == "#F1EEE8"


def test_derive_ui_shades_passes_contrast_check():
    shades = derive_ui_shades(SAMPLE_COLOURS, "light")
    check_contrast(shades)  # must not raise
    assert contrast_ratio(shades["ink"], shades["ground"]) >= 4.5


def test_derive_ui_shades_rejects_bad_world_tone():
    with pytest.raises(UIShadesError, match="light.*dark"):
        derive_ui_shades(SAMPLE_COLOURS, "sideways")


def test_check_contrast_raises_on_low_contrast_pair():
    # a ground almost identical to ink fails 4.5:1
    with pytest.raises(UIShadesError, match="contrast"):
        check_contrast({"ground": "#808080", "surface": "#808080", "surface_2": "#808080",
                         "surface_3": "#808080", "ink": "#7A7A7A"})


def test_mix_interpolates_between_two_hexes():
    assert mix("#000000", "#FFFFFF", 0.5) == "#808080"
    assert mix("#000000", "#FFFFFF", 0.0) == "#000000"
    assert mix("#000000", "#FFFFFF", 1.0) == "#FFFFFF"
