import pytest

from brandkit.house import load_house
from brandkit.merge import MergeError, merge_house


def test_merge_returns_house_unchanged_with_no_overrides():
    house = load_house()
    merged = merge_house(house, None)
    assert merged == house
    assert merged is not house  # deep copy, not the same object


def test_merge_applies_overridable_section():
    house = load_house()
    merged = merge_house(house, {"motion_design": {"ease": "power1.out"}})
    assert merged["motion_design"]["ease"] == "power1.out"
    assert merged["motion_design"]["durations"] == house["motion_design"]["durations"]
    # original house dict is untouched
    assert house["motion_design"]["ease"] == "power2.out"


def test_merge_rejects_non_overridable_section():
    house = load_house()
    with pytest.raises(MergeError, match="not overridable"):
        merge_house(house, {"qa_checklist": {"items": []}})


def test_merge_rejects_unknown_section():
    house = load_house()
    with pytest.raises(MergeError, match="unknown house section"):
        merge_house(house, {"nope": {}})


def test_house_negatives_caps_present():
    house = load_house()
    assert house["negatives"]["stills_max_terms"] == 8
    assert house["negatives"]["video_max_terms"] == 6
    assert house["safe_areas"]["16:9"]["title_safe"] == 0.80
