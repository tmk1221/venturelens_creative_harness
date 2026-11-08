"""Lowest-free-track packing, tested directly against synthetic intervals (the store's
Cut invariants forbid same-layer spans from overlapping in *source* time, so exercising a
real timeline overlap end-to-end needs multiple sync groups; this is the direct check)."""
from __future__ import annotations

from post_core.export._placement import PlacedItem, pack_lowest_free_track


def test_non_overlapping_items_share_one_track():
    items = [
        PlacedItem(0, 10, "a", "A"),
        PlacedItem(10, 10, "b", "B"),
        PlacedItem(20, 5, "c", "C"),
    ]
    packed = pack_lowest_free_track(items)
    assert len(packed) == 1
    assert [p.payload for p in packed[0]] == ["A", "B", "C"]


def test_overlapping_items_spill_to_a_new_track():
    items = [
        PlacedItem(0, 10, "a", "A"),
        PlacedItem(5, 10, "b", "B"),  # overlaps A -> needs its own track
        PlacedItem(20, 5, "c", "C"),  # fits after A on track 0
    ]
    packed = pack_lowest_free_track(items)
    assert len(packed) == 2
    assert [p.payload for p in packed[0]] == ["A", "C"]
    assert [p.payload for p in packed[1]] == ["B"]


def test_packing_is_deterministic_on_tied_start_frames():
    items = [
        PlacedItem(0, 5, "z", "Z"),
        PlacedItem(0, 5, "a", "A"),
    ]
    packed = pack_lowest_free_track(items)
    # Same start frame: tie-broken by sort_key, so both spill (they overlap [0,5)).
    assert len(packed) == 2
    assert packed[0][0].payload == "A"
    assert packed[1][0].payload == "Z"


def test_three_way_overlap_needs_three_tracks():
    items = [
        PlacedItem(0, 10, "a", "A"),
        PlacedItem(2, 10, "b", "B"),
        PlacedItem(4, 10, "c", "C"),
    ]
    packed = pack_lowest_free_track(items)
    assert len(packed) == 3
