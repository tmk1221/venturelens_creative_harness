"""Shoot: a recording session, and the Source/SyncGroup it groups.

Shoot -> Source[] / SyncGroup[] / Transcript, per docs/ARCHITECTURE.md §data model.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import field_validator, model_validator

from .base import Entity
from .common import Rational

SourceRole = Literal["a_roll", "b_roll", "audio", "screen", "other"]


SourceKind = Literal["real", "virtual"]


class Source(Entity):
    """One recorded media file (video or audio) belonging to a shoot -- or (T23) a
    `kind="virtual"` source with no underlying media at all, standing in for a locked cut
    that Post never plays back (script-as-transcript demos)."""

    path: Optional[str] = None  # absolute path on disk; None only for kind="virtual"
    fps: Rational
    start_timecode: str = "00:00:00:00"  # e.g. "01:00:00:00"
    role: SourceRole = "other"
    kind: SourceKind = "real"
    proxy_path: Optional[str] = None
    peaks_path: Optional[str] = None
    audio_proxy_path: Optional[str] = None
    content_fingerprint: str

    @field_validator("path")
    @classmethod
    def _path_absolute(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.startswith("/"):
            raise ValueError("Source.path must be an absolute path")
        return v

    @model_validator(mode="after")
    def _virtual_has_no_path(self) -> "Source":
        if self.kind == "virtual" and self.path is not None:
            raise ValueError("Source.path must be None when kind='virtual'")
        if self.kind == "real" and self.path is None:
            raise ValueError("Source.path is required when kind='real'")
        return self


class SyncGroup(Entity):
    """A set of Sources locked to a shared timeline (e.g. multicam + external audio)."""

    source_ids: list[str]
    offsets: dict[str, float]  # source_id -> offset in seconds from the group origin

    @field_validator("offsets")
    @classmethod
    def _offsets_match_sources(cls, v: dict[str, float], info) -> dict[str, float]:
        source_ids = info.data.get("source_ids")
        if source_ids is not None and set(v.keys()) != set(source_ids):
            raise ValueError("SyncGroup.offsets must have exactly one entry per source_id")
        return v


class Shoot(Entity):
    """A recording session grouping sources, sync groups and transcripts.

    Source and SyncGroup are small and embedded directly (there is no `sources/` or
    `sync_groups/` directory in the store layout). Transcript is large (word lists) and
    lives in its own file under `transcripts/`, referenced here by id only.
    """

    name: str
    sources: list[Source] = []
    sync_groups: list[SyncGroup] = []
    transcript_ids: list[str] = []

    @field_validator("sync_groups")
    @classmethod
    def _sync_groups_reference_known_sources(cls, v: list[SyncGroup], info) -> list[SyncGroup]:
        sources = info.data.get("sources") or []
        source_ids = {s.id for s in sources}
        for group in v:
            unknown = [sid for sid in group.source_ids if sid not in source_ids]
            if unknown:
                raise ValueError(f"SyncGroup {group.id!r} references unknown source ids: {unknown}")
        return v


def clean_audio_source(shoot: "Shoot", group: SyncGroup) -> Source:
    """T22: the audio proxy source for a sync group -- its dedicated audio recorder Source
    (`role == "audio"`), falling back to the group's `a_roll` camera (camA) when there is no
    separate recorder. Post plays only audio; picture/angle judgement happens in Resolve."""
    members = [s for s in shoot.sources if s.id in group.source_ids]
    audio = next((s for s in members if s.role == "audio"), None)
    if audio is not None:
        return audio
    a_roll = next((s for s in members if s.role == "a_roll"), None)
    if a_roll is not None:
        return a_roll
    if members:
        return members[0]
    raise ValueError(f"sync group {group.id!r} has no member sources in shoot {shoot.id!r}")
