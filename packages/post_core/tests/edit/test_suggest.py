"""T13b/T30b: the automated "Suggest visuals" pass -- generation/validation, persistence,
accept/dismiss/accept-all lifecycle, and the `POST3_FAKE_PROVIDERS=1` deterministic demo
suggester. Every test here uses `FakeTextProvider` or `DeterministicSuggester`; nothing ever
shells out. T30b: proposals carry the full beat model (`medium` + optional overlay), so
"kind": "video"/"anim"/"overlay" is gone -- see `suggest_models.Suggestion`."""
from __future__ import annotations

import json

import pytest
from conftest import make_transcript

from post_core import store
from post_core.edit import ops
from post_core.edit.suggest import (
    Scope,
    SuggestError,
    accept_all,
    accept_suggestion,
    dismiss_suggestion,
    generate_suggestions,
    suggest_visuals,
)
from post_core.edit.suggest_provider import DeterministicSuggester, FakeTextProvider
from post_core.edit.suggest_store import read_suggestions
from post_core.model import Rational, Span, WordAnchor

ASPECT = Rational(num=16, den=9)


def _setup(tmp_path, n=12):
    store.init_project(tmp_path)
    t = make_transcript("sg1", n=n)
    store.write(tmp_path, "transcript", t, expected_rev=0)
    cut = ops.cut_from_transcript(t, "cam-a", ASPECT)
    store.write(tmp_path, "cut", cut, expected_rev=0)
    return t, cut


def _scope_whole(t):
    return Scope(kind="cut", sync_group_id=t.sync_group_id, start_word_id=t.words[0].id, end_word_id=t.words[-1].id)


def _canned(proposals: list[dict]) -> FakeTextProvider:
    return FakeTextProvider(json.dumps(proposals))


def _video_proposal(start="w1", end="w2", brief="Show it.", rationale="because") -> dict:
    return {"start_word_id": start, "end_word_id": end, "medium": "live_action", "brief": brief, "rationale": rationale}


def _overlay_proposal(start="w1", end="w2", depth="in_front", position="lower-band") -> dict:
    return {
        "start_word_id": start, "end_word_id": end, "overlay": {"depth": depth, "position": position},
        "brief": "x", "rationale": "y",
    }


# --- generation / validation --------------------------------------------------------------

def test_generate_suggestions_builds_from_valid_proposals(tmp_path):
    t, cut = _setup(tmp_path)
    provider = _canned([_video_proposal()])
    result = generate_suggestions(tmp_path, cut, [t], _scope_whole(t), provider)
    assert len(result) == 1
    assert result[0].medium == "live_action"
    assert result[0].overlay_depth is None
    assert result[0].start_anchor == WordAnchor(transcript_id=t.id, word_id="w1")
    assert provider.calls[0]["scope"] == "cut"
    assert provider.calls[0]["cast"] == []


def test_generate_suggestions_builds_combined_medium_and_overlay_proposal(tmp_path):
    t, cut = _setup(tmp_path)
    proposal = {
        "start_word_id": "w1", "end_word_id": "w2", "medium": "aroll",
        "overlay": {"depth": "behind", "position": "full-frame"}, "brief": "x", "rationale": "y",
    }
    result = generate_suggestions(tmp_path, cut, [t], _scope_whole(t), _canned([proposal]))
    assert len(result) == 1
    assert result[0].medium == "aroll"
    assert result[0].overlay_depth == "behind"
    assert result[0].overlay_position == "full-frame"


def test_generate_suggestions_drops_proposal_with_invalid_overlay_for_its_medium(tmp_path):
    t, cut = _setup(tmp_path)
    proposal = {
        "start_word_id": "w1", "end_word_id": "w2", "medium": "provided",
        "overlay": {"depth": "behind", "position": "full-frame"}, "brief": "x", "rationale": "y",
    }
    result = generate_suggestions(tmp_path, cut, [t], _scope_whole(t), _canned([proposal]))
    assert result == []


def test_generate_suggestions_drops_proposal_with_neither_medium_nor_overlay(tmp_path):
    t, cut = _setup(tmp_path)
    proposal = {"start_word_id": "w1", "end_word_id": "w2", "brief": "x", "rationale": "y"}
    result = generate_suggestions(tmp_path, cut, [t], _scope_whole(t), _canned([proposal]))
    assert result == []


def test_generate_suggestions_drops_unknown_anchor(tmp_path):
    t, cut = _setup(tmp_path)
    provider = _canned([_video_proposal(start="not-a-word")])
    result = generate_suggestions(tmp_path, cut, [t], _scope_whole(t), provider)
    assert result == []


def test_generate_suggestions_drops_out_of_scope_proposal(tmp_path):
    t, cut = _setup(tmp_path)
    scope = Scope(kind="selection", sync_group_id=t.sync_group_id, start_word_id="w0", end_word_id="w3")
    provider = _canned([_video_proposal(start="w8", end="w9")])
    result = generate_suggestions(tmp_path, cut, [t], scope, provider)
    assert result == []


def test_generate_suggestions_drops_same_layer_overlap_with_existing_span(tmp_path):
    t, cut = _setup(tmp_path)
    existing = Span(
        layer="picture", kind="live_action",
        start_anchor=WordAnchor(transcript_id=t.id, word_id="w1"),
        end_anchor=WordAnchor(transcript_id=t.id, word_id="w3"),
    )
    cut = cut.model_copy(update={"spans": [existing]})
    provider = _canned([
        _video_proposal(start="w2", end="w2"),  # picture, overlaps
        _overlay_proposal(start="w2", end="w2"),  # different layer, ok
    ])
    result = generate_suggestions(tmp_path, cut, [t], _scope_whole(t), provider)
    assert len(result) == 1
    assert result[0].overlay_depth == "in_front"


def test_generate_suggestions_drops_dismissed_range(tmp_path):
    t, cut = _setup(tmp_path)
    provider = _canned([_video_proposal()])
    first = suggest_visuals(tmp_path, cut.id, [t], _scope_whole(t), cut=cut, provider=provider)
    assert len(first) == 1
    dismiss_suggestion(tmp_path, cut.id, first[0].id)

    second = generate_suggestions(tmp_path, cut, [t], _scope_whole(t), provider)
    assert second == []


def test_deterministic_suggester_under_fake_providers_env(tmp_path, monkeypatch):
    monkeypatch.setenv("POST3_FAKE_PROVIDERS", "1")
    words = (
        "We reviewed one thousand automation case studies about scheduling systems "
        "carefully before writing anything down today."
    ).split()
    t = make_transcript("sg1", words=[{"id": f"w{i}", "text": w, "start": i * 0.4, "end": i * 0.4 + 0.3} for i, w in enumerate(words)])
    store.init_project(tmp_path)
    store.write(tmp_path, "transcript", t, expected_rev=0)
    cut = ops.cut_from_transcript(t, "cam-a", ASPECT)
    store.write(tmp_path, "cut", cut, expected_rev=0)

    result = generate_suggestions(tmp_path, cut, [t], _scope_whole(t))  # no provider given
    assert len(result) == 1
    assert result[0].brief.startswith("Show ")
    assert result[0].medium == "live_action"


def test_deterministic_suggester_covers_every_medium_and_both_overlay_depths():
    """T30b acceptance: "deterministic fake covers every medium and both overlay depths
    across a long transcript." A long, plain sentence per beat (period-terminated so each is
    its own chunk) drives the cycle through all four mediums plus both overlay depths."""
    sentences = [
        "We carefully reviewed the entire automation roadmap document together.",
        "The dashboard displays every scheduling metric our operations team tracks.",
        "Someone brought fresh donuts into the crowded conference room yesterday.",
        "Our presenter explained the onboarding process directly to camera.",
        "The engineering department rebuilt the deployment pipeline from scratch.",
        "Marketing published seventeen new case studies about customer retention.",
        "A courier delivered replacement hardware to the downtown warehouse quickly.",
        "Our presenter closed the segment speaking plainly into the lens.",
    ]
    words = []
    wid = 0
    for sentence in sentences:
        for tok in sentence.split():
            words.append({"id": f"w{wid}", "text": tok, "start": wid * 0.4, "end": wid * 0.4 + 0.3})
            wid += 1
    suggester = DeterministicSuggester(cap=8, min_words=6)
    from post_core.edit.suggest import _sentences_in_range
    from post_core.edit.ranges import TranscriptIndex

    t = make_transcript("sg1", words=words)
    index = TranscriptIndex([t])
    chunked = _sentences_in_range(index, "sg1", 0, len(words) - 1)
    raw = suggester.draft({"sentences": chunked})
    proposals = json.loads(raw)

    mediums = {p.get("medium") for p in proposals}
    assert {"aroll", "provided", "live_action", "motion_graphic"} <= mediums
    depths = {p["overlay"]["depth"] for p in proposals if "overlay" in p}
    assert {"in_front", "behind"} <= depths
    # every overlay proposal is legal for its own beat's medium+depth (or has none)
    from post_core.model.cut import valid_overlay_positions

    for p in proposals:
        if "overlay" in p:
            allowed = valid_overlay_positions(p.get("medium", "aroll"), p["overlay"]["depth"])
            assert p["overlay"]["position"] in allowed


def test_deterministic_suggester_directly_caps_and_skips_short_sentences():
    suggester = DeterministicSuggester(cap=1, min_words=3)
    sentences = [
        {"words": [{"id": "a", "text": "Hi"}, {"id": "b", "text": "there."}]},  # too short
        {"words": [{"id": "c", "text": "We"}, {"id": "d", "text": "reviewed"}, {"id": "e", "text": "automations."}]},
        {"words": [{"id": "f", "text": "We"}, {"id": "g", "text": "reviewed"}, {"id": "h", "text": "workflows."}]},
    ]
    proposals = json.loads(suggester.draft({"sentences": sentences}))
    assert len(proposals) == 1  # capped at 1 even though two sentences qualify


# --- persistence / re-run dedupe ------------------------------------------------------------

def test_suggest_visuals_rerun_does_not_duplicate(tmp_path):
    t, cut = _setup(tmp_path)
    provider = _canned([_video_proposal()])
    first = suggest_visuals(tmp_path, cut.id, [t], _scope_whole(t), cut=cut, provider=provider)
    assert len(first) == 1
    second = suggest_visuals(tmp_path, cut.id, [t], _scope_whole(t), cut=cut, provider=provider)
    assert len(second) == 1  # re-running with the same proposal doesn't add a duplicate


# --- accept / dismiss / accept-all -----------------------------------------------------------

def test_accept_suggestion_creates_span_marked_agent_and_drops_suggestion(tmp_path):
    t, cut = _setup(tmp_path)
    provider = _canned([_video_proposal(brief="Show the dashboard.")])
    pending = suggest_visuals(tmp_path, cut.id, [t], _scope_whole(t), cut=cut, provider=provider)
    suggestion_id = pending[0].id

    new_cut, accepted = accept_suggestion(tmp_path, cut.id, suggestion_id)
    assert accepted.id == suggestion_id
    matching = [s for s in new_cut.spans if s.brief.text == "Show the dashboard."]
    assert len(matching) == 1
    assert matching[0].provenance == "agent"
    assert matching[0].kind == "live_action"
    assert matching[0].layer == "picture"

    remaining = read_suggestions(tmp_path, cut.id)
    assert remaining.items == []


def test_accept_suggestion_with_overlay_creates_both_layers(tmp_path):
    t, cut = _setup(tmp_path)
    proposal = {
        "start_word_id": "w1", "end_word_id": "w2", "medium": "aroll",
        "overlay": {"depth": "behind", "position": "full-frame"}, "brief": "Show the chart.", "rationale": "y",
    }
    pending = suggest_visuals(tmp_path, cut.id, [t], _scope_whole(t), cut=cut, provider=_canned([proposal]))
    new_cut, _accepted = accept_suggestion(tmp_path, cut.id, pending[0].id)

    picture = [s for s in new_cut.spans if s.layer == "picture"]
    overlay = [s for s in new_cut.spans if s.layer == "overlay"]
    assert len(picture) == 1 and picture[0].kind == "aroll"
    assert len(overlay) == 1 and overlay[0].overlay_depth == "behind" and overlay[0].overlay_position == "full-frame"
    assert picture[0].start_anchor == overlay[0].start_anchor


def test_accept_suggestion_unknown_id_raises(tmp_path):
    _t, cut = _setup(tmp_path)
    with pytest.raises(SuggestError):
        accept_suggestion(tmp_path, cut.id, "not-an-id")


def test_dismiss_suggestion_unknown_id_raises(tmp_path):
    _t, cut = _setup(tmp_path)
    with pytest.raises(SuggestError):
        dismiss_suggestion(tmp_path, cut.id, "not-an-id")


def test_dismiss_suggestion_removes_it_and_records_key(tmp_path):
    t, cut = _setup(tmp_path)
    provider = _canned([_video_proposal()])
    pending = suggest_visuals(tmp_path, cut.id, [t], _scope_whole(t), cut=cut, provider=provider)

    dismissed = dismiss_suggestion(tmp_path, cut.id, pending[0].id)
    assert dismissed.id == pending[0].id

    remaining = read_suggestions(tmp_path, cut.id)
    assert remaining.items == []
    assert remaining.dismissed_keys == ["w1:w2"]


def test_accept_all_accepts_unblocked_and_blocks_conflicting(tmp_path):
    from post_core.edit.suggest_models import Suggestion
    from post_core.edit.suggest_store import update_suggestions

    t, cut = _setup(tmp_path)

    def _seed(file):
        return file.model_copy(update={"items": [
            Suggestion(
                start_anchor=WordAnchor(transcript_id=t.id, word_id="w1"),
                end_anchor=WordAnchor(transcript_id=t.id, word_id="w2"),
                medium="live_action", brief="first", rationale="r",
            ),
            # Deliberately overlaps the first on the same (picture) layer -- generate_suggestions
            # would never produce this pair together, but two independent "suggest" calls (whole
            # cut, then a selection) racing against each other could; accept_all must not crash,
            # just skip the one that no longer validates once the first has landed.
            Suggestion(
                start_anchor=WordAnchor(transcript_id=t.id, word_id="w2"),
                end_anchor=WordAnchor(transcript_id=t.id, word_id="w3"),
                medium="motion_graphic", brief="second", rationale="r",
            ),
        ]})

    update_suggestions(tmp_path, cut.id, _seed)
    result = accept_all(tmp_path, cut.id)
    assert len(result.accepted) == 1
    assert len(result.blocked) == 1

    remaining = read_suggestions(tmp_path, cut.id)
    assert len(remaining.items) == 1  # the blocked one is left pending, not silently dropped
    assert remaining.items[0].id == result.blocked[0]
