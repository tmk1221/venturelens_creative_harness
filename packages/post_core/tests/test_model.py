"""Model validation: construction, id/schema_version defaults, and field-level invariants."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from post_core.model import (
    Cut,
    Passage,
    Rational,
    Section,
    Shoot,
    Source,
    SyncGroup,
    Trim,
    Word,
    WordAnchor,
    clean_audio_source,
)


def test_every_entity_has_id_and_schema_version():
    source = Source(path="/a/b.mov", fps=Rational(num=30, den=1), start_timecode="00:00:00:00",
                     content_fingerprint="abc")
    assert source.id
    assert source.schema_version == 1


def test_rational_rejects_zero_denominator():
    with pytest.raises(ValidationError):
        Rational(num=30, den=0)


def test_word_requires_ordered_positive_range():
    Word(id="w1", text="hi", start=0.0, end=0.5)
    with pytest.raises(ValidationError):
        Word(id="w1", text="hi", start=1.0, end=0.5)
    with pytest.raises(ValidationError):
        Word(id="w1", text="  ", start=0.0, end=0.5)


def test_sync_group_offsets_must_match_source_ids():
    with pytest.raises(ValidationError):
        SyncGroup(source_ids=["s1", "s2"], offsets={"s1": 0.0})
    SyncGroup(source_ids=["s1", "s2"], offsets={"s1": 0.0, "s2": 1.2})


def test_source_path_must_be_absolute():
    with pytest.raises(ValidationError):
        Source(path="relative/path.mov", fps=Rational(num=30), start_timecode="00:00:00:00",
               content_fingerprint="abc")


def test_clean_audio_source_prefers_dedicated_recorder():
    camA = Source(path="/a/camA.mov", fps=Rational(num=30), start_timecode="00:00:00:00",
                   role="a_roll", content_fingerprint="camA")
    mic = Source(path="/a/mic.wav", fps=Rational(num=30), start_timecode="00:00:00:00",
                 role="audio", content_fingerprint="mic")
    group = SyncGroup(source_ids=[camA.id, mic.id], offsets={camA.id: 0.0, mic.id: 0.0})
    shoot = Shoot(name="s", sources=[camA, mic], sync_groups=[group])
    assert clean_audio_source(shoot, group).id == mic.id


def test_clean_audio_source_falls_back_to_a_roll_camera():
    camA = Source(path="/a/camA.mov", fps=Rational(num=30), start_timecode="00:00:00:00",
                   role="a_roll", content_fingerprint="camA")
    camB = Source(path="/a/camB.mov", fps=Rational(num=30), start_timecode="00:00:00:00",
                   role="b_roll", content_fingerprint="camB")
    group = SyncGroup(source_ids=[camA.id, camB.id], offsets={camA.id: 0.0, camB.id: 0.0})
    shoot = Shoot(name="s", sources=[camA, camB], sync_groups=[group])
    assert clean_audio_source(shoot, group).id == camA.id


def test_cut_section_rejects_unknown_passage_id():
    passage = Passage(sync_group_id="sg1", start_word_id="w1", end_word_id="w2", angle_source_id="s1")
    with pytest.raises(ValidationError):
        Cut(aspect=Rational(num=16, den=9), passages=[passage],
            sections=[Section(id="sec1", title="Intro", passage_ids=["nope"])])
    # A section that only references known passages is fine.
    Cut(aspect=Rational(num=16, den=9), passages=[passage],
        sections=[Section(id="sec1", title="Intro", passage_ids=[passage.id])])


def test_cut_rejects_duplicate_passage_ids():
    passage = Passage(id="p1", sync_group_id="sg1", start_word_id="w1", end_word_id="w2", angle_source_id="s1")
    with pytest.raises(ValidationError):
        Cut(aspect=Rational(num=1, den=1), passages=[passage, passage.model_copy()])


def test_trim_defaults_zero():
    assert Trim().head == 0.0
    assert Trim().tail == 0.0


def test_word_anchor_is_plain_pair():
    anchor = WordAnchor(transcript_id="t1", word_id="w1")
    assert anchor.transcript_id == "t1"
    assert anchor.word_id == "w1"
