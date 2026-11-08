"""A small on-disk fixture project for export tests: two camera angles + a clean audio
source in one sync group, three reordered passages, and a picture/audio/overlay span plus
one deliberately orphaned span."""
from __future__ import annotations

from pathlib import Path

import pytest

from post_core import store
from post_core.graph.approvals import approve
from post_core.model import Asset, Cut, Passage, Rational, Section, Shoot, Source, Span, SyncGroup, Transcript, Word

FPS = Rational(num=24000, den=1001)


def _words(n: int, gap: float = 0.5, dur: float = 0.4) -> list[Word]:
    return [Word(id=f"w{i}", text=f"word{i}", start=i * gap, end=i * gap + dur) for i in range(n)]


class Fixture:
    def __init__(self, project_root: Path, cut: Cut, ids: dict):
        self.project_root = project_root
        self.cut = cut
        self.ids = ids


@pytest.fixture
def export_project(tmp_path: Path) -> Fixture:
    project_root = tmp_path / "proj"
    store.init_project(project_root)

    cam_a = Source(
        path="/fake/media/cam-a.mov", fps=FPS, start_timecode="01:00:00:00",
        role="a_roll", content_fingerprint="fp-cam-a",
    )
    cam_b = Source(
        path="/fake/media/cam-b.mov", fps=FPS, start_timecode="01:00:00:00",
        role="a_roll", content_fingerprint="fp-cam-b",
    )
    audio_src = Source(
        path="/fake/media/room-audio.wav", fps=FPS, start_timecode="01:00:00:00",
        role="audio", content_fingerprint="fp-audio",
    )
    sync_group = SyncGroup(
        id="sg1",
        source_ids=[cam_a.id, cam_b.id, audio_src.id],
        offsets={cam_a.id: 0.0, cam_b.id: 2.0, audio_src.id: 0.5},
    )
    words = _words(12)
    transcript = Transcript(sync_group_id=sync_group.id, provider="fake", words=words, fingerprint="fp")
    shoot = Shoot(name="shoot1", sources=[cam_a, cam_b, audio_src], sync_groups=[sync_group],
                  transcript_ids=[transcript.id])

    store.write(project_root, "shoot", shoot, expected_rev=0)
    store.write(project_root, "transcript", transcript, expected_rev=0)

    # Reordered: passage 1 plays words[6:9] (angle A), passage 2 plays words[0:3] (angle B),
    # passage 3 plays words[9:12] (angle A again). Words[3:6] are covered by no passage.
    p1 = Passage(sync_group_id=sync_group.id, start_word_id="w6", end_word_id="w8", angle_source_id=cam_a.id)
    p2 = Passage(sync_group_id=sync_group.id, start_word_id="w0", end_word_id="w2", angle_source_id=cam_b.id)
    p3 = Passage(sync_group_id=sync_group.id, start_word_id="w9", end_word_id="w11", angle_source_id=cam_a.id)

    broll_path = tmp_path / "assets" / "broll.mp4"
    title_path = tmp_path / "assets" / "title.mp4"
    broll_path.parent.mkdir(parents=True, exist_ok=True)
    broll_path.write_bytes(b"fake")
    title_path.write_bytes(b"fake")

    span_picture = Span(
        layer="picture", kind="broll", workflow_id="node-broll", provenance="agent",
        start_anchor={"transcript_id": transcript.id, "word_id": "w0"},
        end_anchor={"transcript_id": transcript.id, "word_id": "w1"},
    )
    span_audio_missing = Span(
        layer="audio", kind="sfx", workflow_id="node-sfx-missing", provenance="agent",
        start_anchor={"transcript_id": transcript.id, "word_id": "w9"},
        end_anchor={"transcript_id": transcript.id, "word_id": "w10"},
    )
    span_overlay = Span(
        layer="overlay", kind="title", workflow_id="node-title", provenance="human",
        start_anchor={"transcript_id": transcript.id, "word_id": "w6"},
        end_anchor={"transcript_id": transcript.id, "word_id": "w7"},
    )
    span_orphaned = Span(
        layer="overlay", kind="lower-third", provenance="human", orphaned=True,
        start_anchor={"transcript_id": transcript.id, "word_id": "w3"},
        end_anchor={"transcript_id": transcript.id, "word_id": "w4"},
    )

    section = Section(id="sec1", title="Intro", passage_ids=[p1.id, p2.id])

    cut = Cut(
        aspect=Rational(num=16, den=9), fps=FPS,
        passages=[p1, p2, p3],
        spans=[span_picture, span_audio_missing, span_overlay, span_orphaned],
        sections=[section],
    )
    store.write(project_root, "cut", cut, expected_rev=0)

    asset_broll = Asset(node_id="node-broll", content_hash="hash-broll", path=str(broll_path), role="picture")
    asset_title = Asset(node_id="node-title", content_hash="hash-title", path=str(title_path), role="overlay")
    store.write(project_root, "asset", asset_broll, expected_rev=0)
    store.write(project_root, "asset", asset_title, expected_rev=0)
    approve(project_root, "hash-broll", by="test")
    approve(project_root, "hash-title", by="test")
    # node-sfx-missing deliberately has no Asset at all -> MISSING marker.

    ids = dict(
        cam_a=cam_a.id, cam_b=cam_b.id, audio_src=audio_src.id, sync_group=sync_group.id,
        transcript=transcript.id, p1=p1.id, p2=p2.id, p3=p3.id,
        span_picture=span_picture.id, span_audio_missing=span_audio_missing.id,
        span_overlay=span_overlay.id, span_orphaned=span_orphaned.id,
    )
    return Fixture(project_root, cut, ids)
