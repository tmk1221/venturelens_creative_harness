"""T30: Span/beat overlay depth-position matrix and the swap rule."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from post_core.model.common import Rational
from post_core.model.cut import Cut, Span, WordAnchor, swap_position_for_depth_change, valid_overlay_positions


def _anchor(word_id: str) -> WordAnchor:
    return WordAnchor(transcript_id="t1", word_id=word_id)


def _picture_span(kind: str, start: str = "w0", end: str = "w5") -> Span:
    return Span(layer="picture", start_anchor=_anchor(start), end_anchor=_anchor(end), kind=kind)


def _overlay_span(depth: str, position: str, start: str = "w0", end: str = "w5") -> Span:
    return Span(
        layer="overlay", start_anchor=_anchor(start), end_anchor=_anchor(end), kind="overlay",
        overlay_depth=depth, overlay_position=position,
    )


def _cut(spans: list[Span]) -> Cut:
    return Cut(aspect=Rational(num=16, den=9), spans=spans)


# ---- valid_overlay_positions / swap_position_for_depth_change (pure functions) ----------


def test_matrix_aroll_in_front():
    assert valid_overlay_positions("aroll", "in_front") == {"right", "left", "lower-band"}


def test_matrix_aroll_behind():
    assert valid_overlay_positions("aroll", "behind") == {"right", "left", "full-frame"}


def test_matrix_broll_in_front():
    for kind in ("provided", "live_action", "motion_graphic"):
        assert valid_overlay_positions(kind, "in_front") == {
            "right", "left", "lower-band", "center", "full-width",
        }


def test_matrix_broll_behind_is_empty():
    """behind is only meaningful over aroll."""
    for kind in ("provided", "live_action", "motion_graphic"):
        assert valid_overlay_positions(kind, "behind") == frozenset()


def test_swap_rule_aroll_lower_band_to_full_frame():
    assert swap_position_for_depth_change("lower-band", "aroll") == "full-frame"
    assert swap_position_for_depth_change("full-frame", "aroll") == "lower-band"


def test_swap_rule_noop_for_non_swapping_positions():
    assert swap_position_for_depth_change("right", "aroll") == "right"


def test_swap_rule_noop_over_broll():
    assert swap_position_for_depth_change("lower-band", "provided") == "lower-band"


# ---- Span-level self-consistency ---------------------------------------------------------


def test_span_overlay_fields_must_be_paired():
    with pytest.raises(ValidationError):
        Span(
            layer="overlay", start_anchor=_anchor("w0"), end_anchor=_anchor("w5"), kind="overlay",
            overlay_depth="in_front",
        )


def test_span_overlay_fields_forbidden_off_overlay_layer():
    with pytest.raises(ValidationError):
        Span(
            layer="picture", start_anchor=_anchor("w0"), end_anchor=_anchor("w5"), kind="aroll",
            overlay_depth="in_front", overlay_position="right",
        )


def test_span_overlay_ok():
    span = _overlay_span("in_front", "lower-band")
    assert span.overlay_depth == "in_front"
    assert span.overlay_position == "lower-band"


# ---- Cut-level matrix validation (needs sibling picture span) ---------------------------


def test_cut_accepts_legal_pairing_aroll_behind_full_frame():
    _cut([_picture_span("aroll"), _overlay_span("behind", "full-frame")])


def test_cut_rejects_behind_over_non_aroll():
    with pytest.raises(ValidationError):
        _cut([_picture_span("live_action"), _overlay_span("behind", "full-frame")])


def test_cut_rejects_illegal_position_for_depth():
    with pytest.raises(ValidationError):
        _cut([_picture_span("aroll"), _overlay_span("behind", "lower-band")])


def test_cut_rejects_center_over_aroll():
    """center/full-width only exist in the B-roll position set."""
    with pytest.raises(ValidationError):
        _cut([_picture_span("aroll"), _overlay_span("in_front", "center")])


def test_cut_accepts_center_over_provided():
    _cut([_picture_span("provided"), _overlay_span("in_front", "center")])


def test_cut_skips_check_with_no_sibling_picture_span():
    """No matching picture span yet (e.g. overlay authored standalone) -> unchecked."""
    _cut([_overlay_span("behind", "full-frame")])


# ---- continuity edge ----------------------------------------------------------------------


def test_continuity_requires_known_span_id():
    picture = _picture_span("live_action", "w0", "w5")
    other = Span(
        layer="picture", start_anchor=_anchor("w6"), end_anchor=_anchor("w10"), kind="live_action",
        continuity_of_span_id="does-not-exist",
    )
    with pytest.raises(ValidationError):
        _cut([picture, other])


def test_continuity_requires_both_live_action():
    picture = _picture_span("aroll", "w0", "w5")
    other = Span(
        layer="picture", start_anchor=_anchor("w6"), end_anchor=_anchor("w10"), kind="live_action",
        continuity_of_span_id=picture.id,
    )
    with pytest.raises(ValidationError):
        _cut([picture, other])


def test_continuity_ok_between_two_live_action_spans():
    first = _picture_span("live_action", "w0", "w5")
    second = Span(
        layer="picture", start_anchor=_anchor("w6"), end_anchor=_anchor("w10"), kind="live_action",
        continuity_of_span_id=first.id,
    )
    cut = _cut([first, second])
    assert cut.spans[1].continuity_of_span_id == first.id
