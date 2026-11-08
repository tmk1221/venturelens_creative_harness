"""T37 render contract for generated video, checked by `asset.verify` before a clip can be
approved: it has a video stream, runs at the project's frame rate, lasts at least the span,
does not end on a frozen frame (unless the brief asks for a hold), and is the cut's aspect.

Lessons from the old app (`post-animation-recovery-2026-09-16`, `animate` skill §4): wrong
geometry, frame rate or length, and a tail that silently stops moving, all shipped past
checks that only looked at readability. Every failure here is one plain sentence -- it is
what the beat's card shows. Local ffprobe/ffmpeg only: never networked, never paid.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Optional

from .. import aspect as aspect_mod

TAIL_SECONDS = 0.5  # the stretch at the end that must still move
_FREEZE_RE = re.compile(r"lavfi\.freezedetect\.freeze_(start|end):\s*([0-9.]+)")


@dataclass(frozen=True)
class MediaProbe:
    has_video: bool
    width: int = 0
    height: int = 0
    fps: Optional[Fraction] = None
    frames: Optional[int] = None
    seconds: Optional[float] = None


def _fraction(raw) -> Optional[Fraction]:
    try:
        f = Fraction(str(raw))
    except (ValueError, ZeroDivisionError):
        return None
    return f if f > 0 else None


def probe(path: Path) -> MediaProbe:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height,r_frame_rate,nb_frames,duration:format=duration",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    data = json.loads(out.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        return MediaProbe(has_video=False)
    fps = _fraction(video.get("r_frame_rate"))
    nb = video.get("nb_frames")
    frames = int(nb) if nb not in (None, "N/A") else None
    if frames is not None and fps is not None:
        seconds: Optional[float] = float(frames / fps)
    else:
        raw = video.get("duration") or (data.get("format") or {}).get("duration")
        seconds = float(raw) if raw not in (None, "N/A") else None
    return MediaProbe(True, int(video.get("width") or 0), int(video.get("height") or 0), fps, frames, seconds)


def frozen_tail_seconds(path: Path, seconds: float) -> float:
    """How long the clip's end has been one unchanging frame (0.0 when it still moves at the
    end). ffmpeg's `freezedetect` reports a freeze only once it has lasted `TAIL_SECONDS`;
    one still open at the end of the file (no `freeze_end` after its `freeze_start`) is a
    frozen tail, measured from the frame it duplicates to the clip's end."""
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:v:0",
         "-vf", f"freezedetect=n=-60dB:d={TAIL_SECONDS}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    events = [(kind, float(value)) for kind, value in _FREEZE_RE.findall(out.stderr)]
    if not events:
        return 0.0
    kind, at = events[-1]
    if kind == "start":
        return max(0.0, seconds - at)
    starts = [t for k, t in events if k == "start"]
    # Some ffmpeg builds close a freeze at end of file; one that ends at the end still counts.
    if starts and at >= seconds - 0.05:
        return max(0.0, at - starts[-1])
    return 0.0


def fps_text(fps: Fraction) -> str:
    if fps.denominator == 1:
        return f"{fps.numerator} fps"
    return f"{float(fps):.3f}".rstrip("0").rstrip(".") + " fps"


def check(
    media: MediaProbe, *, expect_fps: Optional[str] = None, min_seconds: Optional[float] = None,
    expect_aspect: Optional[str] = None, frozen_tail: float = 0.0,
) -> list[str]:
    """Every broken rule as one sentence; empty when the clip passes. Unset expectations are
    skipped. `frozen_tail` is `frozen_tail_seconds`' result (0.0 when a hold is allowed)."""
    if not media.has_video:
        return ["The file has no video stream."]
    problems: list[str] = []
    want_fps = _fraction(expect_fps) if expect_fps else None
    if want_fps is not None and media.fps != want_fps:
        got = fps_text(media.fps) if media.fps else "an unknown frame rate"
        problems.append(f"The clip is {got} but the project is {fps_text(want_fps)}.")
    if min_seconds is not None:
        slack = float(1 / media.fps) if media.fps else 0.01
        if media.seconds is None:
            problems.append("The clip's length could not be read.")
        elif media.seconds + slack < min_seconds:
            problems.append(
                f"The clip is {media.seconds:.2f} s long but the beat needs at least {min_seconds:.2f} s."
            )
    if frozen_tail >= TAIL_SECONDS:
        problems.append(
            f"The last {frozen_tail:.1f} s is a frozen copy of an earlier frame and the brief does not ask for a hold."
        )
    if expect_aspect and not aspect_mod.matches(media.width, media.height, expect_aspect):
        problems.append(f"The clip is {media.width}x{media.height}, not {aspect_mod.label(expect_aspect)}.")
    return problems


__all__ = ["TAIL_SECONDS", "MediaProbe", "probe", "frozen_tail_seconds", "fps_text", "check"]
