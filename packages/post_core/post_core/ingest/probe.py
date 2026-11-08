"""ffprobe -> the Source fields T02's model needs.

Everything here is read-only subprocess + parsing; nothing writes to disk. The content
fingerprint is size + mtime + a sha256 of the first and last 1MB (AGENTS.md: cheap and
stable enough to key proxies/peaks/transcripts by, without hashing a multi-GB file).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

from post_core.model.common import Rational

_FINGERPRINT_CHUNK = 1 << 20  # 1MB


class ProbeError(RuntimeError):
    """ffprobe failed or returned something this module cannot parse."""


def content_fingerprint(path: str | Path) -> str:
    """size + mtime + sha256(first 1MB) + sha256(last 1MB), stable across re-probing a
    file that hasn't changed, cheap even for multi-GB sources."""
    p = Path(path)
    st = p.stat()
    h = hashlib.sha256()
    h.update(str(st.st_size).encode())
    h.update(str(int(st.st_mtime)).encode())
    size = st.st_size
    with p.open("rb") as f:
        h.update(f.read(min(_FINGERPRINT_CHUNK, size)))
        if size > _FINGERPRINT_CHUNK:
            f.seek(max(0, size - _FINGERPRINT_CHUNK))
            h.update(f.read(_FINGERPRINT_CHUNK))
    return h.hexdigest()


def ffprobe_json(path: str | Path) -> dict[str, Any]:
    cmd = ["ffprobe", "-v", "error", "-print_format", "json",
           "-show_format", "-show_streams", str(path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        raise ProbeError("ffprobe not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise ProbeError(f"ffprobe failed for {path}: {exc.stderr.strip()}") from exc
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"ffprobe produced non-JSON output for {path}") from exc


def _parse_rate(rate: str) -> Rational:
    """ffprobe gives frame rates as 'num/den' (e.g. '30000/1001'); fall back to a plain
    number for the rare stream that reports one."""
    if "/" in rate:
        num_s, den_s = rate.split("/", 1)
        num, den = int(num_s), int(den_s)
        if den == 0:
            return Rational(num=0, den=1)
        return Rational(num=num, den=den)
    frac = Fraction(rate).limit_denominator(1001)
    return Rational(num=frac.numerator, den=frac.denominator)


def probe_source(path: str | Path) -> dict[str, Any]:
    """Return a dict of Source-shaped fields for `path` (caller builds the Source)."""
    p = Path(path).resolve()
    data = ffprobe_json(p)
    fmt = data.get("format", {}) or {}
    streams = data.get("streams", []) or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    duration_raw = fmt.get("duration") or (video or {}).get("duration")
    try:
        duration = float(duration_raw) if duration_raw is not None else 0.0
    except ValueError:
        duration = 0.0

    fps = Rational(num=30, den=1)
    width = height = 0
    start_timecode = "00:00:00:00"
    if video:
        fps = _parse_rate(video.get("r_frame_rate") or "30/1")
        width = int(video.get("width") or 0)
        height = int(video.get("height") or 0)
        tc = (video.get("tags") or {}).get("timecode") or (fmt.get("tags") or {}).get("timecode")
        if not tc:
            # Some cameras (e.g. Sony) stamp timecode on a separate data stream rather
            # than on the video stream or the container format tags.
            for s in streams:
                cand = (s.get("tags") or {}).get("timecode")
                if cand:
                    tc = cand
                    break
        if tc:
            start_timecode = tc

    return {
        "path": str(p),
        "fps": fps,
        "duration": duration,
        "start_timecode": start_timecode,
        "width": width,
        "height": height,
        "audio_streams": [
            {
                "index": s.get("index"),
                "channels": s.get("channels"),
                "sample_rate": s.get("sample_rate"),
                "codec": s.get("codec_name"),
            }
            for s in audio_streams
        ],
        "content_fingerprint": content_fingerprint(p),
    }
