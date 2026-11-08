"""Track builders: V1 (chosen angle) + V1-alt (other angles, disabled), A1 (clean audio),
and the lowest-free-track-packed V2+ / overlay / A2+ span tracks.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import opentimelineio as otio

from ..model.common import Rational
from ..model.cut import Cut, Span
from . import _clips
from ._context import ExportContext, asset_done_and_approved, find_asset_for_node
from ._placement import PlacedItem, pack_lowest_free_track
from ._spans import span_frame_range


@dataclass
class ManifestClip:
    kind: str  # "passage" | "span_picture" | "span_overlay" | "span_audio" | "audio_clean"
    id: str
    content_hash: Optional[str]
    start_frame: int
    duration_frames: int
    track: str


def _clean_audio_source(ctx: ExportContext, sync_group_id: str):
    sync_group = ctx.sync_group_of(sync_group_id)
    for source_id in sync_group.source_ids:
        source = ctx.source(source_id)
        if source.role == "audio":
            return source
    return None


def build_v1_and_a1(
    ctx: ExportContext, segments, fps: Rational
) -> tuple[
    otio.schema.Track, list[otio.schema.Track], otio.schema.Track, dict[str, tuple[int, int]], list[ManifestClip]
]:
    """Returns (V1, [V1-alt...], A1, {passage_id: (start_frame, duration_frames)}, manifest)."""
    fps_f = fps.as_float()
    v1 = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)
    a1 = otio.schema.Track(name="A1", kind=otio.schema.TrackKind.Audio)
    passage_frames: dict[str, tuple[int, int]] = {}
    manifest: list[ManifestClip] = []
    # Every passage's (start_frame, duration_frames), in order -- used to backfill Gaps on
    # an alt row that's created partway through (an earlier passage had fewer "other"
    # angles than this one).
    passage_order: list[tuple[int, int]] = []
    # alt_rows[i] holds, for every passage in order, either (start,dur,clip) or (start,dur,None)
    alt_rows: list[list[tuple[int, int, Optional[otio.schema.Clip]]]] = []

    for seg, passage in zip(segments, ctx.cut.passages):
        sync_group = ctx.sync_group_of(passage.sync_group_id)
        chosen = ctx.source(passage.angle_source_id)
        offset = sync_group.offsets.get(chosen.id, 0.0)
        start_f, end_f = _clips.source_frame_range(
            seg.source_start, offset, seg.duration_frames, fps, chosen
        )
        clip = _clips.make_camera_clip(
            f"passage-{passage.id}",
            chosen,
            start_f,
            end_f,
            {
                "passage_id": passage.id,
                "span_id": None,
                "asset_content_hash": None,
                "sync_group_id": sync_group.id,
                "source_id": chosen.id,
            },
        )
        v1.append(clip)
        passage_frames[passage.id] = (seg.start_frame, seg.duration_frames)
        passage_order.append((seg.start_frame, seg.duration_frames))
        manifest.append(
            ManifestClip("passage", passage.id, None, seg.start_frame, seg.duration_frames, "V1")
        )

        audio_source = _clean_audio_source(ctx, passage.sync_group_id)
        if audio_source is not None:
            a_offset = sync_group.offsets.get(audio_source.id, 0.0)
            a_start, a_end = _clips.source_frame_range(
                seg.source_start, a_offset, seg.duration_frames, fps, audio_source
            )
            a_clip = _clips.make_camera_clip(
                f"audio-{passage.id}",
                audio_source,
                a_start,
                a_end,
                {
                    "passage_id": passage.id,
                    "span_id": None,
                    "asset_content_hash": None,
                    "sync_group_id": sync_group.id,
                    "source_id": audio_source.id,
                },
            )
            a1.append(a_clip)
        else:
            a1.append(_clips.gap(seg.duration_frames, fps_f))

        others = [
            sid for sid in sync_group.source_ids
            if sid != chosen.id and ctx.source(sid).role != "audio"
        ]
        for i, other_id in enumerate(others):
            while len(alt_rows) <= i:
                # New row, later than passage 0: backfill Gaps for every earlier passage.
                alt_rows.append([(s, d, None) for s, d in passage_order])
            other_source = ctx.source(other_id)
            o_offset = sync_group.offsets.get(other_id, 0.0)
            o_start, o_end = _clips.source_frame_range(
                seg.source_start, o_offset, seg.duration_frames, fps, other_source
            )
            alt_clip = _clips.make_camera_clip(
                f"passage-{passage.id}-alt-{other_source.id}",
                other_source,
                o_start,
                o_end,
                {
                    "passage_id": passage.id,
                    "span_id": None,
                    "asset_content_hash": None,
                    "sync_group_id": sync_group.id,
                    "source_id": other_source.id,
                },
            )
            alt_rows[i].append((seg.start_frame, seg.duration_frames, alt_clip))
        for i in range(len(others), len(alt_rows)):
            alt_rows[i].append((seg.start_frame, seg.duration_frames, None))

    alt_tracks: list[otio.schema.Track] = []
    for i, row in enumerate(alt_rows):
        name = "V1-alt" if len(alt_rows) == 1 else f"V1-alt{i + 1}"
        track = otio.schema.Track(name=name, kind=otio.schema.TrackKind.Video)
        track.enabled = False
        cursor = 0
        for start_frame, duration_frames, clip in row:
            if start_frame > cursor:
                track.append(_clips.gap(start_frame - cursor, fps_f))
            track.append(clip if clip is not None else _clips.gap(duration_frames, fps_f))
            cursor = start_frame + duration_frames
        alt_tracks.append(track)

    return v1, alt_tracks, a1, passage_frames, manifest


@dataclass
class SpanPlacementResult:
    tracks: list[otio.schema.Track]
    manifest: list[ManifestClip]
    missing: list[tuple[int, str]]  # (start_frame, kind) for spans with no approved asset
    orphaned: list[str]  # kinds of spans that no longer resolve to any surviving word


def build_span_tracks(
    ctx: ExportContext,
    spans: list[Span],
    fps: Rational,
    layer: str,
    name_prefix: str,
    manifest_kind: str,
    start_index: int = 1,
) -> SpanPlacementResult:
    fps_f = fps.as_float()
    items: list[PlacedItem[tuple[Span, int, int, object]]] = []
    missing: list[tuple[int, str]] = []
    orphaned: list[str] = []

    for span in spans:
        if span.layer != layer:
            continue
        if span.orphaned:
            orphaned.append(span.kind)
            continue
        frame_range = span_frame_range(ctx.cut, ctx.index, fps, span)
        if frame_range is None:
            orphaned.append(span.kind)
            continue
        start_frame, duration_frames = frame_range

        asset = find_asset_for_node(ctx.project_root, span.workflow_id) if span.workflow_id else None
        if not asset_done_and_approved(ctx.project_root, asset):
            missing.append((start_frame, span.kind))
            clip = _clips.missing_clip(
                f"missing-{span.id}",
                duration_frames,
                fps_f,
                {"passage_id": None, "span_id": span.id, "asset_content_hash": None},
            )
        else:
            clip = _clips.make_asset_clip(
                f"{name_prefix}-{span.id}",
                asset.path,  # type: ignore[union-attr]
                duration_frames,
                fps_f,
                {"passage_id": None, "span_id": span.id, "asset_content_hash": asset.content_hash},  # type: ignore[union-attr]
                asset_fps=asset.fps,  # type: ignore[union-attr]
                asset_duration_frames=asset.duration_frames,  # type: ignore[union-attr]
                timeline_fps=fps,
            )

        items.append(PlacedItem(start_frame, duration_frames, span.id, (span, start_frame, duration_frames, clip)))

    packed = pack_lowest_free_track(items)
    tracks: list[otio.schema.Track] = []
    manifest: list[ManifestClip] = []
    kind_str = otio.schema.TrackKind.Audio if layer == "audio" else otio.schema.TrackKind.Video
    for i, row in enumerate(packed):
        track_name = f"{name_prefix}{start_index + i}"
        track = otio.schema.Track(name=track_name, kind=kind_str)
        cursor = 0
        for placed in row:
            span, start_frame, duration_frames, clip = placed.payload
            if start_frame > cursor:
                track.append(_clips.gap(start_frame - cursor, fps_f))
            track.append(clip)
            cursor = start_frame + duration_frames
            content_hash = clip.metadata.get("post3", {}).get("asset_content_hash")
            manifest.append(
                ManifestClip(manifest_kind, span.id, content_hash, start_frame, duration_frames, track_name)
            )
        tracks.append(track)

    return SpanPlacementResult(tracks=tracks, manifest=manifest, missing=missing, orphaned=orphaned)
