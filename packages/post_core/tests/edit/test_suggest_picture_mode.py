"""T42: picture mode (`presenter` / `audio_only`), re-running Suggest replaces the pending
proposals in its scope, and two ideas for the same words become one proposal with variants.
Every test uses `FakeTextProvider`; nothing shells out."""
from __future__ import annotations

import json

import pytest
from conftest import make_transcript

from post_core import store
from post_core.edit import ops
from post_core.edit.suggest import (
    Scope, SuggestError, accept_suggestion, generate_suggestions, suggest_visuals, switch_variant, update_suggestion,
)
from post_core.edit.suggest_coverage import FILLER_RATIONALE, is_exact_tiling
from post_core.edit.suggest_provider import FakeTextProvider
from post_core.edit.suggest_store import read_suggestions
from post_core.model import Rational, Span, WordAnchor
from post_core.model.project import Project
from post_core.picture_mode import UnknownPictureMode, project_picture_mode, set_picture_mode

ASPECT = Rational(num=16, den=9)


def _setup(tmp_path, n=20, spans=()):
    store.init_project(tmp_path)
    store.write(tmp_path, "project", Project(name="p", root=str(tmp_path)), expected_rev=0)
    t = make_transcript("sg1", n=n)
    store.write(tmp_path, "transcript", t, expected_rev=0)
    cut = ops.cut_from_transcript(t, "cam-a", ASPECT)
    if spans:
        cut = cut.model_copy(update={"spans": [
            Span(layer="picture", kind="live_action", start_anchor=WordAnchor(transcript_id=t.id, word_id=s),
                 end_anchor=WordAnchor(transcript_id=t.id, word_id=e)) for s, e in spans]})
    store.write(tmp_path, "cut", cut, expected_rev=0)
    return t, cut


def _whole(t):
    return Scope(kind="cut", sync_group_id="sg1", start_word_id=t.words[0].id, end_word_id=t.words[-1].id)


def _p(start, end, medium="live_action", brief="Show it.", **kw) -> dict:
    return {"start_word_id": f"w{start}", "end_word_id": f"w{end}", "medium": medium, "brief": brief,
            "rationale": "fits the words", **kw}


def _canned(*proposals) -> FakeTextProvider:
    return FakeTextProvider(json.dumps(list(proposals)))


def _ranges(items):
    return [(int(s.start_anchor.word_id[1:]), int(s.end_anchor.word_id[1:])) for s in items]


# --- picture mode setting ------------------------------------------------------------------

def test_picture_mode_defaults_to_presenter_and_refuses_unknown(tmp_path):
    _setup(tmp_path)
    assert project_picture_mode(tmp_path) == "presenter"
    with pytest.raises(UnknownPictureMode):
        set_picture_mode(tmp_path, "radio")
    assert set_picture_mode(tmp_path, "audio_only") == {"picture_mode": "audio_only", "previous": "presenter"}
    assert project_picture_mode(tmp_path) == "audio_only"


def test_run_reads_the_project_picture_mode(tmp_path):
    t, cut = _setup(tmp_path)
    set_picture_mode(tmp_path, "audio_only")
    provider = _canned()
    generate_suggestions(tmp_path, cut, [t], _whole(t), provider, writer_context={})
    assert provider.calls[0]["picture_mode"] == "audio_only"


# --- audio only: validation and the coverage guarantee -------------------------------------

def test_audio_only_reply_with_gaps_overlaps_and_aroll_becomes_an_exact_tiling(tmp_path):
    t, cut = _setup(tmp_path, n=20)
    provider = _canned(
        _p(2, 5, brief="Opening"),             # leading gap w0-w1
        _p(4, 9, brief="Overlaps the first"),  # overlaps w4-w5
        _p(6, 7, brief="Inside the second"),   # wholly inside -> a variant
        _p(12, 14, "aroll", brief="Presenter"),  # aroll: dropped in audio-only
        _p(12, 13, "aroll", overlay={"depth": "behind", "position": "left"}, brief="Cut-out presenter"),
        {"start_word_id": "w10", "end_word_id": "w11", "overlay": {"depth": "in_front", "position": "left"},
         "brief": "Overlay only", "rationale": "x"},  # no picture: dropped in audio-only
        _p(15, 16, overlay={"depth": "in_front", "position": "left"}, brief="With a label"),
        _p(16, 17, brief="Overlaps by one"),   # gap w10-w14 before w15; trailing gap w18-w19
    )
    items = generate_suggestions(tmp_path, cut, [t], _whole(t), provider, writer_context={}, picture_mode="audio_only")
    ranges = _ranges(items)
    assert is_exact_tiling(ranges, 0, 19), ranges
    assert ranges == [(0, 5), (6, 12), (13, 16), (17, 19)]
    assert all(s.medium not in (None, "aroll") for s in items)
    assert all(s.overlay_depth != "behind" for s in items)
    assert items[2].overlay_depth == "in_front"
    second = items[1]
    assert second.brief == "Overlaps the first" and [v.brief for v in second.variants] == [
        "Overlaps the first", "Inside the second"]


def test_audio_only_tiles_around_placed_beats_and_fills_an_empty_reply(tmp_path):
    t, cut = _setup(tmp_path, n=12, spans=[("w4", "w6")])
    items = generate_suggestions(tmp_path, cut, [t], _whole(t), _canned(_p(2, 8)), writer_context={},
                                 picture_mode="audio_only")
    ranges = _ranges(items)
    assert ranges == [(0, 3), (7, 11)]  # split around the editor's beat, one piece each side
    assert len({s.id for s in items}) == 2
    assert is_exact_tiling(ranges, 0, 11, blocked=[(4, 6)])

    t2, cut2 = _setup(tmp_path / "empty", n=6)
    filler = generate_suggestions(tmp_path / "empty", cut2, [t2], _whole(t2), _canned(), writer_context={},
                                  picture_mode="audio_only")
    assert _ranges(filler) == [(0, 5)] and filler[0].rationale == FILLER_RATIONALE and filler[0].medium == "live_action"


def test_audio_only_run_persists_full_coverage(tmp_path):
    t, cut = _setup(tmp_path, n=10)
    set_picture_mode(tmp_path, "audio_only")
    for reply in ([_p(1, 3), _p(6, 7)], [_p(0, 4), _p(3, 9)]):
        items = suggest_visuals(tmp_path, cut.id, [t], _whole(t), cut=cut, provider=_canned(*reply), writer_context={})
        assert is_exact_tiling(_ranges(items), 0, 9)


# --- re-running replaces, never stacks -----------------------------------------------------

def test_two_runs_leave_no_duplicate_ranges(tmp_path):
    t, cut = _setup(tmp_path)
    suggest_visuals(tmp_path, cut.id, [t], _whole(t), cut=cut, provider=_canned(_p(1, 3), _p(6, 8)), writer_context={})
    items = suggest_visuals(tmp_path, cut.id, [t], _whole(t), cut=cut,
                            provider=_canned(_p(1, 3, brief="Again"), _p(10, 12)), writer_context={})
    assert sorted(_ranges(items)) == [(1, 3), (10, 12)]
    assert [s.brief for s in items if _ranges([s]) == [(1, 3)]] == ["Again"]


def test_selection_run_replaces_only_inside_its_scope(tmp_path):
    t, cut = _setup(tmp_path)
    suggest_visuals(tmp_path, cut.id, [t], _whole(t), cut=cut, provider=_canned(_p(1, 3), _p(10, 12)), writer_context={})
    scope = Scope(kind="selection", sync_group_id="sg1", start_word_id="w8", end_word_id="w15")
    items = suggest_visuals(tmp_path, cut.id, [t], scope, cut=cut, provider=_canned(_p(9, 11)), writer_context={})
    assert sorted(_ranges(items)) == [(1, 3), (9, 11)]


def test_accepted_beat_survives_a_rerun(tmp_path):
    t, cut = _setup(tmp_path)
    first = suggest_visuals(tmp_path, cut.id, [t], _whole(t), cut=cut, provider=_canned(_p(1, 3, brief="Keep")),
                            writer_context={})
    new_cut, _ = accept_suggestion(tmp_path, cut.id, first[0].id)
    items = suggest_visuals(tmp_path, cut.id, [t], _whole(t), cut=new_cut,
                            provider=_canned(_p(2, 4, brief="Over it"), _p(8, 9)), writer_context={})
    assert _ranges(items) == [(8, 9)]  # nothing proposed over the accepted beat
    on_disk, _rev = store.read(tmp_path, "cut", cut.id)
    assert [(s.start_anchor.word_id, s.end_anchor.word_id, s.brief.text) for s in on_disk.spans] == [("w1", "w3", "Keep")]


# --- variants ------------------------------------------------------------------------------

def test_two_ideas_for_the_same_words_become_one_card_with_variants(tmp_path):
    t, cut = _setup(tmp_path)
    items = suggest_visuals(tmp_path, cut.id, [t], _whole(t), cut=cut, writer_context={}, provider=_canned(
        _p(1, 3, brief="A city at night"), _p(1, 3, "motion_graphic", brief="A chart rising")))
    assert len(items) == 1
    card = items[0]
    assert card.brief == "A city at night" and card.active_variant == 0
    assert [v.brief for v in card.variants] == ["A city at night", "A chart rising"]

    update_suggestion(tmp_path, cut.id, card.id, {"brief": "A city at night, rain"})
    b = switch_variant(tmp_path, cut.id, card.id, 1)
    assert (b.brief, b.medium, b.active_variant) == ("A chart rising", "motion_graphic", 1)
    a = switch_variant(tmp_path, cut.id, card.id, 0)
    assert (a.brief, a.medium) == ("A city at night, rain", "live_action")  # the edit was kept
    with pytest.raises(SuggestError):
        switch_variant(tmp_path, cut.id, card.id, 5)
    assert len(read_suggestions(tmp_path, cut.id).items) == 1


def test_a_picture_and_an_overlay_on_the_same_words_are_not_variants(tmp_path):
    t, cut = _setup(tmp_path)
    overlay = {"start_word_id": "w1", "end_word_id": "w3", "overlay": {"depth": "in_front", "position": "left"},
               "brief": "Lower third", "rationale": "names the guest"}
    items = generate_suggestions(tmp_path, cut, [t], _whole(t), _canned(_p(1, 3), overlay), writer_context={})
    assert len(items) == 2 and all(not s.variants for s in items)
