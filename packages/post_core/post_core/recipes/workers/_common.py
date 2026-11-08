"""Shared plumbing for recipe workers: the T03 `##POST` contract, `POST3_FAKE_PROVIDERS=1`
placeholder media (ffmpeg -- local, offline, never paid or networked), and ffprobe.

Every worker in this package is a `python -m post_core.recipes.workers.<name>` subprocess
(argv built by `recipes.cmd.build_cmd`), so each is import-safe (no top-level side effects)
and independently runnable for debugging.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Optional, Sequence, Union

from ... import aspect as aspect_mod
from ...workers.contract import emit

FAKE_PROVIDERS_ENV = "POST3_FAKE_PROVIDERS"


def fake_mode() -> bool:
    return os.environ.get(FAKE_PROVIDERS_ENV) == "1"


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--project-root", default=".")


def _drawtext_safe(label: str) -> str:
    """`drawtext`'s filter-option syntax treats `:` as the key=value separator and `'`/`\\`
    specially -- node ids like `beat1-still0` are safe, but labels built from them
    (`f"still:{node_id}"`) are not. Strip everything that would break the filtergraph
    parser rather than trying to escape it correctly for every ffmpeg version."""
    return "".join(c for c in label if c not in ":'\\")


def placeholder_image(out_path: Path, label: str, size: str = "640x360") -> None:
    """A tiny, real (ffmpeg-decodable) PNG standing in for a generated still. Local,
    offline, free -- not a call to any image-generation provider."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
            "-i", f"color=c=gray:s={size}:d=1",
            "-vf", f"drawtext=text='{_drawtext_safe(label)}':x=10:y=10:fontcolor=white:fontsize=24",
            "-frames:v", "1", str(out_path),
        ],
        check=True,
    )


def placeholder_size(aspect: str, short_side: int = 360) -> str:
    """T37: a small placeholder frame at `aspect` ("9:16" -> "360x640"), even on both sides."""
    f = aspect_mod.to_fraction(aspect)
    long_side = int(round(short_side * (f if f >= 1 else 1 / f) / 2)) * 2
    return f"{long_side}x{short_side}" if f >= 1 else f"{short_side}x{long_side}"


def placeholder_video(
    out_path: Path, label: str, seconds: float, fps: Union[int, str] = 24, size: str = "640x360",
) -> None:
    """A tiny, real (ffprobe-inspectable) MP4 standing in for a generated video -- local,
    offline ffmpeg synthesis, never a call to any video-generation provider. `fps` may be a
    rational string ("24000/1001"). T37: a moving test pattern, not a flat colour, so it
    passes `asset.verify`'s frozen-tail check the way a real generated clip should."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(seconds, float(1 / Fraction(str(fps))))
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
            "-i", f"testsrc2=s={size}:d={duration}:r={fps}",
            "-vf", f"drawtext=text='{_drawtext_safe(label)}':x=10:y=10:fontcolor=white:fontsize=24",
            "-pix_fmt", "yuv420p", str(out_path),
        ],
        check=True,
    )


def probe_video(path: Path) -> dict:
    """ffprobe's frame rate + frame count for `path`. Local media inspection only -- never
    a networked or paid call, so this is safe to run even outside fake mode."""
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate,nb_frames,width,height",
            "-of", "json", str(path),
        ],
        check=True, capture_output=True, text=True,
    )
    data = json.loads(out.stdout)
    streams = data.get("streams") or [{}]
    stream = streams[0]
    rate = str(stream.get("r_frame_rate", "24/1"))
    num_s, _, den_s = rate.partition("/")
    fps_num, fps_den = int(num_s or 24), int(den_s or 1) or 1
    nb_frames = stream.get("nb_frames")
    return {
        "fps_num": fps_num,
        "fps_den": fps_den,
        "duration_frames": int(nb_frames) if nb_frames not in (None, "N/A") else None,
        "width": stream.get("width"),
        "height": stream.get("height"),
    }


def crop_video_to_aspect(src: Path, dest: Path, aspect: str) -> None:
    """T37: centre-crop `src` to `aspect` (the cut's) into `dest`, keeping its frame rate and
    any audio -- local ffmpeg, the `crop_to` half of "generated 9:16, cropped to 4:5"."""
    probe = probe_video(src)
    width, height = int(probe.get("width") or 0), int(probe.get("height") or 0)
    if not width or not height:
        raise ValueError(f"cannot crop {src}: no frame size probed")
    f = aspect_mod.to_fraction(aspect)
    if Fraction(width, height) > f:
        crop_w, crop_h = int(height * f) // 2 * 2, height
    else:
        crop_w, crop_h = width, int(width / f) // 2 * 2
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-map", "0:v:0", "-map", "0:a?",
            "-vf", f"crop={crop_w}:{crop_h}", "-pix_fmt", "yuv420p", "-c:a", "copy", str(dest),
        ],
        check=True,
    )


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def emit_artifact_ok(
    path: Path, role: str, cost: Optional[dict] = None, also: Sequence[tuple[Path, str]] = (), **extra,
) -> None:
    """The success tail: cost, the primary artifact (first, so it is `outputs[0]`), any `also`
    artifacts as (path, role), then the result."""
    if cost:
        emit("cost", **cost)
    emit("artifact", path=str(path), role=role, sha256=_sha256(path), **extra)
    for other, other_role in also:
        emit("artifact", path=str(other), role=other_role, sha256=_sha256(other))
    emit("result", ok=True, detail="done")


__all__ = [
    "fake_mode", "add_common_args", "placeholder_image", "placeholder_size", "placeholder_video",
    "crop_video_to_aspect", "probe_video", "emit_artifact_ok", "FAKE_PROVIDERS_ENV",
]
