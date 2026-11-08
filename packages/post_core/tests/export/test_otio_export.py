"""Cut -> OTIO export: track layout, frame-accurate clip placement, versioning, and the
patch-export diff. All exercised through the real `otio.adapters` round trip."""
from __future__ import annotations

import opentimelineio as otio
import pytest

from post_core import store
from post_core.export import ExportError, export_cut, patch_export
from post_core.graph.approvals import approve
from post_core.model import Asset

FPS_F = 24000 / 1001
TC_FRAMES = 86400  # "01:00:00:00" at 23.976


def _read(path):
    return otio.adapters.read_from_file(str(path))


def _track(timeline, name):
    return next(t for t in timeline.tracks if t.name == name)


def test_round_trip_and_track_layout(export_project):
    path = export_cut(export_project.project_root, export_project.cut.id)
    tl = _read(path)  # otio.adapters.read_from_file round trip

    names = [t.name for t in tl.tracks]
    assert names == ["V1", "V2", "OVERLAY1", "A1", "A2", "V1-alt"]
    assert _track(tl, "V1").kind == otio.schema.TrackKind.Video
    assert _track(tl, "A1").kind == otio.schema.TrackKind.Audio
    assert len(_track(tl, "V1")) == 3  # three passages, no gaps in the picture spine


def test_v1_clip_source_ranges_to_the_frame(export_project):
    path = export_cut(export_project.project_root, export_project.cut.id)
    tl = _read(path)
    v1 = _track(tl, "V1")
    clips = list(v1)

    # passage 1: words[6:9] (source seconds 3.0-4.4), angle cam-a, offset 0.0
    assert clips[0].source_range.start_time.value == TC_FRAMES + 72
    assert clips[0].source_range.duration.value == 34
    # passage 2: words[0:3] (source seconds 0.0-1.4), angle cam-b, offset 2.0
    assert clips[1].source_range.start_time.value == TC_FRAMES + 48
    assert clips[1].source_range.duration.value == 33
    # passage 3: words[9:12] (source seconds 4.5-5.9), angle cam-a, offset 0.0
    assert clips[2].source_range.start_time.value == TC_FRAMES + 108
    assert clips[2].source_range.duration.value == 34

    # V1 durations sum exactly like ranges.timeline()'s cumulative-rounded frame count.
    assert sum(c.source_range.duration.value for c in clips) == 101

    for clip in clips:
        assert clip.metadata["post3"]["passage_id"] is not None
        assert clip.metadata["post3"]["span_id"] is None


def test_v1_alt_track_is_disabled_and_holds_the_other_angle(export_project):
    path = export_cut(export_project.project_root, export_project.cut.id)
    tl = _read(path)
    alt = _track(tl, "V1-alt")
    assert alt.enabled is False

    alt_clips = [c for c in alt if isinstance(c, otio.schema.Clip)]
    assert len(alt_clips) == 3
    # passage 1 chose cam-a -> alt clip is cam-b at the same source seconds + cam-b's offset.
    assert alt_clips[0].source_range.start_time.value == TC_FRAMES + 120
    assert alt_clips[0].source_range.duration.value == 34
    # passage 2 chose cam-b -> alt clip is cam-a.
    assert alt_clips[1].source_range.start_time.value == TC_FRAMES + 0
    assert alt_clips[1].source_range.duration.value == 33


def test_picture_and_overlay_spans_and_missing_marker(export_project):
    path = export_cut(export_project.project_root, export_project.cut.id)
    tl = _read(path)

    v2 = _track(tl, "V2")
    v2_clips = [c for c in v2 if isinstance(c, otio.schema.Clip)]
    assert len(v2_clips) == 1
    assert v2_clips[0].metadata["post3"]["asset_content_hash"] == "hash-broll"

    overlay1 = _track(tl, "OVERLAY1")
    overlay_clips = [c for c in overlay1 if isinstance(c, otio.schema.Clip)]
    assert overlay_clips[0].metadata["post3"]["asset_content_hash"] == "hash-title"

    # A2's sfx span has no Asset at all yet -> no Clip anywhere on A2, and a MISSING marker.
    a2 = _track(tl, "A2")
    assert not any(isinstance(c, otio.schema.Clip) for c in a2)
    v1 = _track(tl, "V1")
    marker_names = [m.name for m in v1.markers]
    assert "MISSING: sfx" in marker_names
    assert "ORPHANED: lower-third" in marker_names
    assert "Intro" in marker_names


def test_version_increments_without_overwrite(export_project):
    p1 = export_cut(export_project.project_root, export_project.cut.id)
    p2 = export_cut(export_project.project_root, export_project.cut.id)
    assert p1 != p2
    assert p1.name.endswith("_16x9_v001.otio")
    assert p2.name.endswith("_16x9_v002.otio")
    assert p1.is_file() and p2.is_file()

    with pytest.raises(ExportError):
        export_cut(export_project.project_root, export_project.cut.id, version=1)


def test_patch_export_contains_only_changed_clips(export_project):
    export_cut(export_project.project_root, export_project.cut.id)  # v1

    sfx_path = export_project.project_root / "sfx.mp4"
    sfx_path.write_bytes(b"sfx")
    asset_sfx = Asset(node_id="node-sfx-missing", content_hash="hash-sfx", path=str(sfx_path), role="audio")
    store.write(export_project.project_root, "asset", asset_sfx, expected_rev=0)
    approve(export_project.project_root, "hash-sfx", by="test")

    patch_path = patch_export(export_project.project_root, export_project.cut.id, since_version=1)
    assert patch_path.name.endswith("_16x9_v002.otio")
    tl = _read(patch_path)

    v1 = _track(tl, "V1")
    assert not any(isinstance(c, otio.schema.Clip) for c in v1)  # unchanged -> blanked to Gap
    a2 = _track(tl, "A2")
    a2_clips = [c for c in a2 if isinstance(c, otio.schema.Clip)]
    assert len(a2_clips) == 1
    assert a2_clips[0].metadata["post3"]["asset_content_hash"] == "hash-sfx"
