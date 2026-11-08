"""Cast: project-level registry of characters/locations that need visual continuity.

A cast entry's `anchor_content_hash` names an *approved* asset hash (the same content
hashes `graph.approvals` tracks) -- the still that was picked and approved as "this is
Dave". `still.generate` nodes take approved cast anchors as continuity inputs (T12 spec);
a beat that uses "Dave" before Dave has an approved anchor is blocked on that beat's pick.
No anchor recorded (or an anchor whose hash isn't approved) means "not ready yet", not an
error -- a cast entry can exist before it has a picture.
"""
from __future__ import annotations

from typing import Literal, Optional

from .base import Entity

CastKind = Literal["character", "location"]


class CastEntry(Entity):
    name: str
    kind: CastKind = "character"
    description: str = ""
    anchor_content_hash: Optional[str] = None
    anchor_asset_path: Optional[str] = None


__all__ = ["CastEntry", "CastKind"]
