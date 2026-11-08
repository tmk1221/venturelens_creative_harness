"""T36: real-mode "Suggest visuals" through a terminal agent. The prompt is a snapshot per
picture mode (`snapshots/suggest_prompt_selection*.txt`; regenerate with `UPDATE_SNAPSHOTS=1`)
carrying the brand writer context, the picture mode (T42; no editorial rules), the cut's words
by section and the neighbouring beats. Real-mode runs use the `fake_agent` script on PATH -- never a real `claude`/`codex`."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from post_core import store
from post_core.agents import AgentBadJSON
from post_core.edit.suggest import Scope, generate_suggestions, suggest_visuals
from post_core.edit.suggest_models import Suggestion
from post_core.edit.suggest_provider import AgentSuggestProvider
from post_core.edit.suggest_store import read_suggestions, update_suggestions
from post_core.model import Brief, Cut, Passage, Rational, Section, Span, Transcript, Word, WordAnchor

SNAPSHOTS = {"presenter": Path(__file__).parent / "snapshots" / "suggest_prompt_selection.txt",
             "audio_only": Path(__file__).parent / "snapshots" / "suggest_prompt_selection_audio_only.txt"}
TEXTS = ["So", "this", "week", "AI", "is", "becoming", "permanent.", "Um,", "every", "company", "now",
         "runs", "on", "it.", "She's", "searching", "for", "answers", "with", "AEO.", "Right.", "Thanks."]
WRITER = {"identity": "Weekly tech news. Serves founders.", "personality": "Is: sharp, warm.",
          "world": "places: studio", "accents": "", "camera_personality": "locked off"}
RULE_PHRASES = ("EDITORIAL RULES", "second half of a thought", "visualisation test", "Montage cuts on the beat",
                "which rule")


def _scene(root: Path) -> tuple[Transcript, Cut]:
    """Three sections (Hook / Point / Close); "Um," is cut; a human beat before the Point, a
    pending proposal inside it, a human beat after it."""
    store.init_project(root)
    words = [Word(id=f"w{i}", text=text, start=i * 0.5, end=i * 0.5 + 0.4,
                  speaker="SPEAKER_01" if i >= 20 else "SPEAKER_00") for i, text in enumerate(TEXTS)]
    t = Transcript(sync_group_id="sg1", provider="fake", words=words, fingerprint="fp",
                   speakers={"SPEAKER_00": "a podcast host", "SPEAKER_01": "Andrew Keen"})
    store.write(root, "transcript", t, expected_rev=0)
    passages = [Passage(sync_group_id="sg1", start_word_id=s, end_word_id=e, angle_source_id="cam-a")
                for s, e in (("w0", "w6"), ("w8", "w19"), ("w20", "w21"))]

    def anchor(word_id: str) -> WordAnchor:
        return WordAnchor(transcript_id=t.id, word_id=word_id)

    spans = [
        Span(layer="picture", kind="live_action", start_anchor=anchor("w3"), end_anchor=anchor("w6"),
             brief=Brief(text="Server racks humming in a dark hall")),
        Span(layer="picture", kind="motion_graphic", start_anchor=anchor("w20"), end_anchor=anchor("w21"),
             brief=Brief(text="End card")),
    ]
    sections = [Section(id=f"s{i}", title=title, passage_ids=[p.id])
                for i, (title, p) in enumerate(zip(("Hook", "Point", "Close"), passages))]
    cut = Cut(aspect=Rational(num=9, den=16), passages=passages, sections=sections, spans=spans)
    store.write(root, "cut", cut, expected_rev=0)
    pending = Suggestion(start_anchor=anchor("w14"), end_anchor=anchor("w17"), medium="live_action",
                         brief="A woman searching on her phone", rationale="The words say she is searching, so show her searching.")
    update_suggestions(root, cut.id, lambda f: f.model_copy(update={"items": [pending]}))
    return t, cut


def _whole(t: Transcript) -> Scope:
    return Scope(kind="cut", sync_group_id="sg1", start_word_id="w0", end_word_id="w21")


def _capture(seen: dict, reply: dict | None = None):
    def ask(prompt, operation, **kwargs):
        seen.update(prompt=prompt, operation=operation, **kwargs)
        return reply or {"proposals": []}
    return ask


@pytest.mark.parametrize("mode", ["presenter", "audio_only"])
def test_prompt_snapshot_has_brand_mode_sections_and_sequence_context(tmp_path, mode):
    t, cut = _scene(tmp_path)
    seen: dict = {}
    scope = Scope(kind="selection", sync_group_id="sg1", start_word_id="w8", end_word_id="w19")
    generate_suggestions(tmp_path, cut, [t], scope, AgentSuggestProvider(tmp_path, ask=_capture(seen)), WRITER,
                         picture_mode=mode)
    prompt = seen["prompt"]
    assert seen["operation"] == "suggest_visuals" and seen["project_root"] == tmp_path
    for phrase in RULE_PHRASES:  # T42: no editorial rules, in either mode
        assert phrase not in prompt
    assert "why this picture fits these words" in prompt
    assert "Identity: Weekly tech news. Serves founders." in prompt
    assert "## Section: Point" in prompt and "## Section: Hook" not in prompt
    assert '- before the scope "AI is becoming permanent.": live_action; brief: Server racks humming' in prompt
    # T42: the pending proposal inside the scope is about to be replaced, so it is not context
    assert "A woman searching on her phone" not in prompt
    assert '- after the scope "Right. Thanks.": motion_graphic; brief: End card (placed by human)' in prompt
    if mode == "audio_only":
        assert "PICTURE MODE: audio only" in prompt and "every second of the cut needs a picture" in prompt
        assert "aroll" not in prompt.replace("Never use medium aroll", "") and "behind (" not in prompt
        assert "presenter_stays_on_camera" not in prompt
    else:
        assert "PICTURE MODE: presenter on camera" in prompt and '"aroll"' in prompt
    snapshot = SNAPSHOTS[mode]
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        snapshot.parent.mkdir(exist_ok=True)
        snapshot.write_text(prompt, encoding="utf-8")
    assert prompt == snapshot.read_text(encoding="utf-8")


def test_whole_cut_prompt_sends_kept_words_by_section_with_speakers(tmp_path):
    t, cut = _scene(tmp_path)
    seen: dict = {}
    generate_suggestions(tmp_path, cut, [t], _whole(t), AgentSuggestProvider(tmp_path, ask=_capture(seen)), WRITER)
    transcript = seen["prompt"].split("TRANSCRIPT OF THE CUT")[1].split("NEIGHBOURING BEATS")[0]
    assert [line for line in transcript.splitlines() if line.startswith("## ")] == [
        "## Section: Hook", "## Section: Point", "## Section: Close"]
    assert "Um," not in transcript  # cut words are never offered
    assert "(a podcast host, 3.4 s) [1]So" in transcript and "(Andrew Keen, 0.4 s) [20]Right." in transcript


def test_writer_context_defaults_to_the_project_kit(tmp_path, monkeypatch):
    from post_core import brand

    monkeypatch.setattr(brand, "project_writer_context", lambda root: {"identity": "From the project kit"})
    t, cut = _scene(tmp_path)
    seen: dict = {}
    generate_suggestions(tmp_path, cut, [t], _whole(t), AgentSuggestProvider(tmp_path, ask=_capture(seen)))
    assert "Identity: From the project kit" in seen["prompt"]


def test_real_mode_runs_the_agent_and_keeps_proposals_as_proposals(tmp_path, fake_agent, monkeypatch):
    monkeypatch.delenv("POST3_FAKE_PROVIDERS", raising=False)
    t, cut = _scene(tmp_path)
    fake_agent.reply({"proposals": [
        {"start": 9, "end": 13, "medium": "motion_graphic", "brief": "Title card: AI everywhere", "rationale": "6"},
        {"start": 5, "end": 7, "medium": "live_action", "brief": "Over the human beat", "rationale": "x"},
        {"start": 998, "end": 999, "medium": "aroll", "brief": "Nowhere", "rationale": "x"},
    ]})
    items = suggest_visuals(tmp_path, cut.id, [t], _whole(t), cut=cut, writer_context=WRITER)
    assert [c["name"] for c in fake_agent.calls()] == ["claude"]
    # T42: the whole-cut run replaced the pending proposal it covered
    assert [(s.start_anchor.word_id, s.end_anchor.word_id, s.brief) for s in items] == [
        ("w9", "w13", "Title card: AI everywhere"),
    ]
    on_disk, _rev = store.read(tmp_path, "cut", cut.id)
    assert on_disk.spans == cut.spans  # proposals never become spans until a human accepts


def test_fake_mode_never_calls_the_agent(tmp_path, fake_agent, monkeypatch):
    monkeypatch.setenv("POST3_FAKE_PROVIDERS", "1")
    t, cut = _scene(tmp_path)
    suggest_visuals(tmp_path, cut.id, [t], _whole(t), cut=cut, writer_context=WRITER)
    assert fake_agent.calls() == []


@pytest.mark.parametrize("reply", ["Add some B-roll here.", '{"nope": 1}'])
def test_bad_agent_reply_applies_nothing(tmp_path, fake_agent, monkeypatch, reply):
    monkeypatch.delenv("POST3_FAKE_PROVIDERS", raising=False)
    t, cut = _scene(tmp_path)
    fake_agent.reply(reply)
    with pytest.raises(AgentBadJSON):
        suggest_visuals(tmp_path, cut.id, [t], _whole(t), cut=cut, writer_context=WRITER)
    assert [s.brief for s in read_suggestions(tmp_path, cut.id).items] == ["A woman searching on her phone"]
