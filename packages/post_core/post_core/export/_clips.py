"""Frame math and OTIO clip construction, in rational arithmetic.

Camera sources (V1 / V1-alt / A1) carry their own probed fps and a burned-in start
timecode, so their clips are built at the *source's* native rate: `ranges.timeline()`
already gives exact, cumulative-rounded frame positions at the Cut's fps (the one place
timeline time is computed) -- each clip's own duration is re-derived from that same
`duration_frames` via exact `Fraction` rescaling to the source's rate, never by
independently re-rounding the passage's source seconds, so a passage's placement on the
timeline can never drift from a clip's own length even when a source's fps differs from
the Cut's.

Workflow-produced assets (V2+ picture spans, overlay spans, A2+ audio spans): T09 treated
every one as already conformed to the Cut's fps and played it from its own frame zero for
the span's duration ("at its own frames"), because `Asset` had no fps field and probing a
generated file here would require ffprobe, which export must never shell out to for a
deterministic, offline operation. T12 carry-over: `recipes.workers.asset_verify` now probes
produced video with ffprobe *once, at generation time* and records `Asset.fps` /
`Asset.duration_frames`, so export itself still never shells out, but `make_asset_clip` can
rescale to the asset's own native rate exactly like a camera clip does when that data is
present. An asset with no fps recorded (a still image, audio, or anything predating T12)
keeps the old assumed-conformed behaviour -- this is additive, not a breaking change.
"""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Optional

import opentimelineio as otio

from ..model.common import Rational
from ..model.shoot import Source


def timecode_frames(timecode: str, rate: float) -> int:
    return round(otio.opentime.RationalTime.from_timecode(timecode, rate).value)


def rescale_frames(frames: int, from_fps: Rational, to_fps: Rational) -> int:
    """Exact rational rescale of a frame count from one rate to another (identity, and
    exact, when the rates are equal -- the common case)."""
    if from_fps.num == to_fps.num and from_fps.den == to_fps.den:
        return frames
    ratio = to_fps.as_fraction() / from_fps.as_fraction()
    return round(Fraction(frames) * ratio)


def source_frame_range(
    source_start: float, offset: float, timeline_duration_frames: int, timeline_fps: Rational, source: Source
) -> tuple[int, int]:
    """The absolute media-frame range (on `source`'s own file, timecode included) that
    covers source seconds starting at `source_start` of the sync group (`offset` seconds
    from the sync group's origin to this source's own file), for
    `timeline_duration_frames` (at `timeline_fps`).

    The duration is rescaled from the Cut's already-exact `ranges.timeline()` frame count
    (`Fraction`, not re-derived by independently rounding `source_end`), so a clip's own
    length can never drift from where `ranges.timeline()` -- the one place timeline time is
    computed -- placed it, even when a source's fps differs from the Cut's.
    """
    rate = source.fps.as_float()
    tc_frames = timecode_frames(source.start_timecode, rate)
    start_frame = tc_frames + round((source_start + offset) * rate)
    duration_frames = rescale_frames(timeline_duration_frames, timeline_fps, source.fps)
    return start_frame, start_frame + max(0, duration_frames)


def make_camera_clip(
    name: str, source: Source, start_frame: int, end_frame: int, metadata: dict
) -> otio.schema.Clip:
    rate = source.fps.as_float()
    tc_frames = timecode_frames(source.start_timecode, rate)
    duration = max(0, end_frame - start_frame)
    media_ref = otio.schema.ExternalReference(
        target_url=Path(source.path).resolve().as_uri(),
        available_range=otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(tc_frames, rate),
            # Source carries no total-duration field (T02); the available range's lower
            # bound is only guaranteed to cover what this clip actually uses.
            duration=otio.opentime.RationalTime(max(duration, end_frame - tc_frames), rate),
        ),
    )
    clip = otio.schema.Clip(
        name=name,
        media_reference=media_ref,
        source_range=otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(start_frame, rate),
            duration=otio.opentime.RationalTime(duration, rate),
        ),
    )
    clip.metadata["post3"] = metadata
    return clip


def make_asset_clip(
    name: str,
    asset_path: str,
    duration_frames: int,
    fps_f: float,
    metadata: dict,
    asset_fps: Optional[Rational] = None,
    asset_duration_frames: Optional[int] = None,
    timeline_fps: Optional[Rational] = None,
) -> otio.schema.Clip:
    """A workflow-asset clip, played from its own frame zero for `duration_frames` (at the
    Cut's `fps_f`, the timeline rate) -- unless `asset_fps` is given (T12 carry-over: an
    Asset probed by `recipes.workers.asset_verify`), in which case the clip is built at the
    asset's own native rate, exactly like `make_camera_clip`: `duration_frames` (at
    `timeline_fps`, the Cut's exact Rational rate -- required whenever `asset_fps` is given)
    is rescaled to the asset's rate so the clip's placement on the timeline still matches
    `ranges.timeline()`'s frame count, and it is capped to `asset_duration_frames` (the
    asset's own probed length) when that would otherwise ask for more media than exists.
    """
    if asset_fps is not None:
        if timeline_fps is None:
            raise ValueError("make_asset_clip: timeline_fps is required when asset_fps is given")
        rate = asset_fps.as_float()
        native_duration = rescale_frames(duration_frames, timeline_fps, asset_fps)
        if asset_duration_frames is not None:
            native_duration = min(native_duration, max(asset_duration_frames, 1))
    else:
        rate = fps_f
        native_duration = duration_frames

    media_ref = otio.schema.ExternalReference(
        target_url=Path(asset_path).resolve().as_uri(),
        available_range=otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(0, rate),
            duration=otio.opentime.RationalTime(max(native_duration, 1), rate),
        ),
    )
    clip = otio.schema.Clip(
        name=name,
        media_reference=media_ref,
        source_range=otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(0, rate),
            duration=otio.opentime.RationalTime(max(native_duration, 1), rate),
        ),
    )
    clip.metadata["post3"] = metadata
    return clip


def gap(duration_frames: int, fps_f: float) -> otio.schema.Gap:
    return otio.schema.Gap(duration=otio.opentime.RationalTime(max(0, duration_frames), fps_f))


def missing_clip(name: str, duration_frames: int, fps_f: float, metadata: dict) -> otio.schema.Gap:
    """A gap standing in for a span with no `done`+approved asset, still tagged so a human
    (or a marker cross-referencing it) can find it -- OTIO Gaps carry metadata too."""
    g = gap(duration_frames, fps_f)
    g.metadata["post3"] = metadata
    return g
