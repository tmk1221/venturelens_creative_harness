"""Lowest-free-track packing: place time-ordered timeline items on the fewest parallel
tracks, filling the leftover frames on each track with Gaps.

Generic over the payload so it can pack picture spans, overlay spans, or audio spans with
the same greedy interval-scheduling algorithm.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class PlacedItem(Generic[T]):
    start_frame: int
    duration_frames: int
    sort_key: str  # tie-breaker for a deterministic pack when start frames collide
    payload: T


def pack_lowest_free_track(items: list[PlacedItem[T]]) -> list[list[PlacedItem[T]]]:
    """Greedy interval packing, deterministic given `items`.

    Each item goes on the first (lowest-index) track whose most recently placed item ends
    at or before this item's start. Assumes items on the same conceptual layer do not
    overlap (Cut's store-write invariants already enforce that for spans on one layer), so
    packing is lossless -- it only ever affects *how many* tracks are used, never content.
    """
    ordered = sorted(items, key=lambda it: (it.start_frame, it.sort_key))
    tracks: list[list[PlacedItem[T]]] = []
    track_end: list[int] = []
    for item in ordered:
        placed = False
        for i, end in enumerate(track_end):
            if item.start_frame >= end:
                tracks[i].append(item)
                track_end[i] = item.start_frame + item.duration_frames
                placed = True
                break
        if not placed:
            tracks.append([item])
            track_end.append(item.start_frame + item.duration_frames)
    return tracks
