"""Cut -> OpenTimelineIO, one-way, versioned. Never touches DaVinci Resolve (plan §6).

Track layout: V1 = chosen angle per passage; V1-alt* = the sync group's other angle(s) at
the same offsets, disabled; V2+ = picture spans with a `done`+approved asset, packed onto
the fewest tracks (gaps elsewhere); overlay tracks stacked above those; A1 = the sync
group's clean audio source per passage; A2+ = asset audio spans, packed the same way as
picture spans. Every clip carries passage/span id + asset content hash as `post3`
metadata. Markers flag sections, orphaned spans, and spans with no approved asset.

Versioning (T37 naming): `<root>/exports/<cut name>_<aspect>_v<NNN>.otio` (e.g.
`keith-short_4x5_v003.otio`), N = next free for that name + aspect, never overwritten, with
`.manifest.json` and `.README.txt` beside it -- the manifest lists every clip placed (id,
content hash, frame range, track); the README says the timeline's format and that the A-roll
is reframed in Resolve (`_format.py`). The timeline is named after the file and carries the
aspect + intended resolution as `post3` metadata. `patch_export` builds a new version
containing only the clips whose content hash or frame range changed since an earlier
manifest -- everything else is a Gap at its original position, so the file only ever needs
re-conforming the differences.
"""
from __future__ import annotations

import json
import re
from glob import escape as glob_escape
from pathlib import Path
from typing import Optional

import opentimelineio as otio

from ..edit.ranges import timeline as compute_timeline
from ..library import exports_dir as library_exports_dir
from ..model.cut import Cut
from ._context import ExportContext, load_context
from ._format import ExportFormat, export_format, readme_text
from ._tracks import ManifestClip, build_span_tracks, build_v1_and_a1

_VERSION_RE_TMPL = r"^{name}_{token}_v(\d+)\.otio$"


class ExportError(RuntimeError):
    pass


def _cut_name(cut: Cut) -> str:
    name = (cut.variant_label or "").strip() or f"cut-{cut.id[:8]}"
    return re.sub(r'[\\/:*?"<>|]', "-", name)


def _exports_dir(project_root: str | Path) -> Path:
    d = library_exports_dir(project_root)  # T39: `Exports/` in a library project, else `exports/`
    d.mkdir(parents=True, exist_ok=True)
    return d


def _stem(cut_name: str, token: str, version: int) -> str:
    return f"{cut_name}_{token}_v{version:03d}"


def _otio_path(exports_dir: Path, cut_name: str, token: str, version: int) -> Path:
    return exports_dir / f"{_stem(cut_name, token, version)}.otio"


def _manifest_path(exports_dir: Path, cut_name: str, token: str, version: int) -> Path:
    path = exports_dir / f"{_stem(cut_name, token, version)}.manifest.json"
    legacy = exports_dir / f"{cut_name} v{version}.manifest.json"  # pre-T37 name
    return legacy if not path.is_file() and legacy.is_file() else path


def _next_version(exports_dir: Path, cut_name: str, token: str) -> int:
    pattern = re.compile(_VERSION_RE_TMPL.format(name=re.escape(cut_name), token=re.escape(token)))
    max_v = 0
    for f in exports_dir.glob(f"{glob_escape(cut_name)}_{token}_v*.otio"):
        m = pattern.match(f.name)
        if m:
            max_v = max(max_v, int(m.group(1)))
    return max_v + 1


def _add_section_markers(v1: otio.schema.Track, cut: Cut, passage_frames: dict, fps_f: float) -> None:
    for section in cut.sections:
        frames = [passage_frames[pid] for pid in section.passage_ids if pid in passage_frames]
        if not frames:
            continue
        start_frame = min(f[0] for f in frames)
        end_frame = max(f[0] + f[1] for f in frames)
        v1.markers.append(
            otio.schema.Marker(
                name=section.title,
                marked_range=otio.opentime.TimeRange(
                    start_time=otio.opentime.RationalTime(start_frame, fps_f),
                    duration=otio.opentime.RationalTime(max(0, end_frame - start_frame), fps_f),
                ),
                color=otio.schema.MarkerColor.GREEN,
            )
        )


def _add_span_markers(
    v1: otio.schema.Track, fps_f: float, missing: list[tuple[int, str]], orphaned: list[str]
) -> None:
    for start_frame, kind in missing:
        v1.markers.append(
            otio.schema.Marker(
                name=f"MISSING: {kind}",
                marked_range=otio.opentime.TimeRange(
                    start_time=otio.opentime.RationalTime(start_frame, fps_f),
                    duration=otio.opentime.RationalTime(0, fps_f),
                ),
                color=otio.schema.MarkerColor.RED,
            )
        )
    for kind in orphaned:
        # Orphaned spans no longer resolve to any surviving word, so there is no real
        # timeline position for them -- flagged at frame 0 instead of dropped silently.
        v1.markers.append(
            otio.schema.Marker(
                name=f"ORPHANED: {kind}",
                marked_range=otio.opentime.TimeRange(
                    start_time=otio.opentime.RationalTime(0, fps_f),
                    duration=otio.opentime.RationalTime(0, fps_f),
                ),
                color=otio.schema.MarkerColor.RED,
            )
        )


def _build_timeline(ctx: ExportContext) -> tuple[otio.schema.Timeline, list[ManifestClip]]:
    cut = ctx.cut
    fps = cut.fps
    fps_f = fps.as_float()
    segments = compute_timeline(cut, ctx.index, fps)

    v1, alt_tracks, a1, passage_frames, manifest = build_v1_and_a1(ctx, segments, fps)
    _add_section_markers(v1, cut, passage_frames, fps_f)

    # V1 = passages, so picture spans (V2+) and asset audio (A2+) number from 2.
    picture = build_span_tracks(ctx, cut.spans, fps, "picture", "V", "span_picture", start_index=2)
    overlay = build_span_tracks(ctx, cut.spans, fps, "overlay", "OVERLAY", "span_overlay")
    audio = build_span_tracks(ctx, cut.spans, fps, "audio", "A", "span_audio", start_index=2)

    missing = picture.missing + overlay.missing + audio.missing
    orphaned = picture.orphaned + overlay.orphaned + audio.orphaned
    _add_span_markers(v1, fps_f, missing, orphaned)

    manifest += picture.manifest + overlay.manifest + audio.manifest

    otio_timeline = otio.schema.Timeline(name=_cut_name(cut))
    otio_timeline.tracks.append(v1)
    otio_timeline.tracks.extend(picture.tracks)
    otio_timeline.tracks.extend(overlay.tracks)  # overlay tracks stack above picture spans
    otio_timeline.tracks.append(a1)
    otio_timeline.tracks.extend(audio.tracks)
    otio_timeline.tracks.extend(alt_tracks)

    return otio_timeline, manifest


def _write_manifest(
    path: Path, cut: Cut, version: int, manifest: list[ManifestClip], patch_since: Optional[int], fmt: ExportFormat,
) -> None:
    data = {
        "version": version,
        "cut_id": cut.id,
        "cut_name": _cut_name(cut),
        "fps": {"num": cut.fps.num, "den": cut.fps.den},
        "aspect": fmt.aspect,
        "resolution": {"width": fmt.width, "height": fmt.height},
        "patch_since": patch_since,
        "clips": [
            {
                "kind": c.kind,
                "id": c.id,
                "content_hash": c.content_hash,
                "start_frame": c.start_frame,
                "duration_frames": c.duration_frames,
                "track": c.track,
            }
            for c in manifest
        ],
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _read_manifest(path: Path) -> dict:
    if not path.is_file():
        raise ExportError(f"no manifest at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_export(
    ctx: ExportContext, exports_dir: Path, cut_name: str, fmt: ExportFormat, version: int,
    otio_timeline: otio.schema.Timeline, manifest: list[ManifestClip], patch_since: Optional[int],
) -> Path:
    """Name the timeline after its file, stamp the format metadata, and write the .otio,
    manifest and README side by side -- refusing to overwrite an existing version."""
    otio_path = _otio_path(exports_dir, cut_name, fmt.token, version)
    if otio_path.exists():
        raise ExportError(f"export version already exists, refusing to overwrite: {otio_path}")
    otio_timeline.name = otio_path.stem
    otio_timeline.metadata["post3"] = {**fmt.metadata(ctx.cut), "version": version, "patch_since": patch_since}
    otio.adapters.write_to_file(otio_timeline, str(otio_path))
    manifest_path = exports_dir / f"{otio_path.stem}.manifest.json"
    _write_manifest(manifest_path, ctx.cut, version, manifest, patch_since, fmt)
    (exports_dir / f"{otio_path.stem}.README.txt").write_text(readme_text(fmt, otio_path.name, ctx.cut), encoding="utf-8")
    return otio_path


def export_cut(project_root: str | Path, cut_id: str, version: Optional[int] = None) -> Path:
    """Build a fresh OTIO export of `cut_id`'s current state. Never overwrites a version."""
    ctx = load_context(project_root, cut_id)
    exports_dir = _exports_dir(project_root)
    cut_name = _cut_name(ctx.cut)
    fmt = export_format(project_root, ctx.cut)
    otio_timeline, manifest = _build_timeline(ctx)
    if version is None:
        version = _next_version(exports_dir, cut_name, fmt.token)
    return _write_export(ctx, exports_dir, cut_name, fmt, version, otio_timeline, manifest, None)


def patch_export(project_root: str | Path, cut_id: str, since_version: int) -> Path:
    """A new version containing only the clips that changed (content hash or frame range)
    since `since_version`'s manifest; everything else is a Gap at its original position.
    """
    ctx = load_context(project_root, cut_id)
    exports_dir = _exports_dir(project_root)
    cut_name = _cut_name(ctx.cut)
    fmt = export_format(project_root, ctx.cut)
    since_manifest = _read_manifest(_manifest_path(exports_dir, cut_name, fmt.token, since_version))
    previous: dict[str, dict] = {c["id"]: c for c in since_manifest["clips"]}

    otio_timeline, manifest = _build_timeline(ctx)

    changed_ids: set[str] = set()
    for entry in manifest:
        prior = previous.get(entry.id)
        if (
            prior is None
            or prior["content_hash"] != entry.content_hash
            or prior["start_frame"] != entry.start_frame
            or prior["duration_frames"] != entry.duration_frames
        ):
            changed_ids.add(entry.id)

    _blank_unchanged_clips(otio_timeline, changed_ids, ctx.cut.fps.as_float())

    version = _next_version(exports_dir, cut_name, fmt.token)
    return _write_export(ctx, exports_dir, cut_name, fmt, version, otio_timeline, manifest, since_version)


def _blank_unchanged_clips(otio_timeline: otio.schema.Timeline, changed_ids: set, fps_f: float) -> None:
    for track in otio_timeline.tracks:
        children = list(track)
        for i, child in enumerate(children):
            if not isinstance(child, otio.schema.Clip):
                continue
            meta = child.metadata.get("post3", {})
            item_id = meta.get("span_id") or meta.get("passage_id")
            if item_id in changed_ids:
                continue
            replacement = otio.schema.Gap(duration=child.duration())
            replacement.metadata["post3"] = dict(meta)
            track[i] = replacement
