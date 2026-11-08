"""T37: aspect ratios in plain words, delivery resolutions, and what to generate at when a
model doesn't offer the cut's aspect."""
from __future__ import annotations

from fractions import Fraction

import pytest

from post_core import aspect
from post_core.model.common import Rational

KLING = ["16:9", "9:16", "1:1"]


def test_label_token_and_parse_forms():
    assert aspect.label(Rational(num=16, den=9)) == "16:9"
    assert aspect.label("8:10") == "4:5"
    assert aspect.label("4x5") == "4:5"
    assert aspect.token(Rational(num=4, den=5)) == "4x5"
    assert aspect.to_fraction("9/16") == Fraction(9, 16)
    with pytest.raises(ValueError):
        aspect.to_fraction("wide")


@pytest.mark.parametrize("value,size", [
    ("4:5", (1080, 1350)), ("9:16", (1080, 1920)), ("16:9", (1920, 1080)), ("1:1", (1080, 1080)),
    ("21:9", (2520, 1080)), ("2:3", (1080, 1620)),
])
def test_intended_resolution(value, size):
    assert aspect.intended_resolution(value) == size


def test_offered_aspect_is_used_as_is():
    assert aspect.choose_generation_aspect("9:16", KLING) == ("9:16", None)
    assert aspect.choose_generation_aspect("1:1", KLING) == ("1:1", None)


def test_4x5_on_a_model_without_it_generates_9x16_and_crops():
    # 1:1 is numerically nearer, but only a taller frame covers a 4:5 frame at full width.
    assert aspect.choose_generation_aspect("4:5", KLING) == ("9:16", "4:5")


def test_landscape_target_prefers_a_wider_covering_aspect():
    assert aspect.choose_generation_aspect("4:3", KLING) == ("16:9", "4:3")


def test_nothing_covers_falls_back_to_nearest():
    assert aspect.choose_generation_aspect("21:9", KLING) == ("16:9", "21:9")


def test_unknown_offering_assumes_the_target():
    assert aspect.choose_generation_aspect("4:5", None) == ("4:5", None)
    assert aspect.choose_generation_aspect("4:5", []) == ("4:5", None)


def test_matches_tolerates_even_pixel_rounding():
    assert aspect.matches(1080, 1350, "4:5")
    assert aspect.matches(288, 360, "4:5")
    assert not aspect.matches(1080, 1920, "4:5")
    assert not aspect.matches(0, 0, "4:5")
