"""Asset, Approval, Deliverable: build-graph outputs and their sign-off."""
from __future__ import annotations

from typing import Optional

from .base import Entity
from .common import Rational


class Asset(Entity):
    """A content-addressed artifact produced by one build-graph node.

    `fps`/`duration_frames` (T12 carry-over) are the asset's own probed media rate and
    length -- set by `recipes.workers.asset_verify` via ffprobe for produced video, left
    `None` for anything not probed (stills, or assets predating T12). `export._clips` uses
    them, when present, to rescale a clip to its native rate instead of assuming it is
    already conformed to the Cut's fps.
    """

    role: str
    node_id: str
    content_hash: str
    brand_kit_hash: Optional[str] = None
    path: str
    fps: Optional[Rational] = None
    duration_frames: Optional[int] = None


class Approval(Entity):
    """A human (or agent) sign-off naming a specific content hash as accepted."""

    content_hash: str
    by: str
    at: float  # unix timestamp


class Deliverable(Entity):
    """One rendered output of a Cut."""

    cut_id: str
    width: int
    height: int
    captioned: bool = False
