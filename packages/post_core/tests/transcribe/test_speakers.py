"""T35: speaker names live on the transcript (never in word text), refuse unknown labels,
survive a re-import of the same recording, and are reachable from the CLI
(`post transcript speakers <id> --map SPEAKER_00="a podcast host"`). The CLI transcription path
runs end to end against the local fake Deepgram."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from post_core.ingest.transcribe import speakers as speakers_mod
from post_core.ingest.transcribe.importer import words_to_transcript
from post_core.ingest.transcribe.link import add_transcript, latest_for_group
from post_core.store import store as store_module

WORDS = [  # SPEAKER_01's second turn (3 words, 1.5 s) is longer than its first (1 word)
    ("so", 0.0, 0.3, "SPEAKER_00"), ("is", 0.3, 0.6, "SPEAKER_00"), ("AI", 0.6, 0.9, "SPEAKER_01"),
    ("becoming", 1.0, 1.4, "SPEAKER_00"), ("I", 2.0, 2.3, "SPEAKER_01"), ("think", 2.3, 2.9, "SPEAKER_01"),
    ("so", 3.0, 3.5, "SPEAKER_01"),
]


def _words(rows=WORDS) -> list[dict]:
    return [{"text": t, "start": s, "end": e, "speaker": spk, "confidence": 1.0} for t, s, e, spk in rows]


def _transcribed(project_factory):
    root, shoot, group = project_factory(seconds=1.0)
    transcript = add_transcript(root, shoot.id, words_to_transcript(_words(), group.id, "import:json", "fp"))
    return root, shoot, group, transcript


def test_summary_lists_speakers_with_their_longest_utterance(project_factory):
    _root, _shoot, _group, transcript = _transcribed(project_factory)
    summary = speakers_mod.summary(transcript)
    assert [(s["label"], s["name"], s["words"]) for s in summary] == [("SPEAKER_00", None, 3), ("SPEAKER_01", None, 4)]
    assert summary[1]["sample"] == {"start": 2.0, "end": 3.5, "text": "I think so"}
    assert summary[0]["sample"] == {"start": 0.0, "end": 0.6, "text": "so is"}


def test_names_persist_on_the_transcript_not_in_word_text(project_factory):
    root, _shoot, _group, transcript = _transcribed(project_factory)
    speakers_mod.set_names(root, transcript.id, {"SPEAKER_00": " a podcast host ", "SPEAKER_01": "Andrew Keen"})
    stored, _rev = store_module.read(root, "transcript", transcript.id)
    assert stored.speakers == {"SPEAKER_00": "a podcast host", "SPEAKER_01": "Andrew Keen"}
    assert {w.speaker for w in stored.words} == {"SPEAKER_00", "SPEAKER_01"}
    assert [w.text for w in stored.words] == [w[0] for w in WORDS]

    with pytest.raises(speakers_mod.UnknownSpeaker, match="no speaker SPEAKER_07; its speakers are SPEAKER_00, SPEAKER_01"):
        speakers_mod.set_names(root, transcript.id, {"SPEAKER_07": "Nobody"})
    speakers_mod.set_names(root, transcript.id, {"SPEAKER_01": ""})  # an empty name un-names
    assert store_module.read(root, "transcript", transcript.id)[0].speakers == {"SPEAKER_00": "a podcast host"}


def test_names_survive_a_reimport_of_the_same_recording(project_factory):
    root, shoot, group, transcript = _transcribed(project_factory)
    speakers_mod.set_names(root, transcript.id, {"SPEAKER_00": "a podcast host", "SPEAKER_01": "Andrew Keen"})
    again = add_transcript(root, shoot.id, words_to_transcript(_words(WORDS[:4]), group.id, "import:json", "fp2"))
    assert again.id != transcript.id
    stored, _rev = store_module.read(root, "transcript", again.id)
    assert stored.speakers == {"SPEAKER_00": "a podcast host", "SPEAKER_01": "Andrew Keen"}
    shoot_now, _rev = store_module.read(root, "shoot", shoot.id)
    assert shoot_now.transcript_ids == [transcript.id, again.id]
    assert latest_for_group(root, shoot_now, group.id).id == again.id


def test_parse_map_reads_cli_pairs():
    assert speakers_mod.parse_map(['SPEAKER_00=a podcast host', 'SPEAKER_01="Andrew Keen"']) == {
        "SPEAKER_00": "a podcast host", "SPEAKER_01": "Andrew Keen"}
    with pytest.raises(ValueError, match="LABEL=NAME"):
        speakers_mod.parse_map(["Sample"])


def _cli(*args: str) -> dict:
    proc = subprocess.run([sys.executable, "-m", "post_core.cli.main", *args], capture_output=True, text=True,
                          timeout=120)
    return {"exit_code": proc.returncode, **json.loads(proc.stdout.strip().splitlines()[-1])}


def test_cli_names_speakers(project_factory, fake_deepgram):
    root, _shoot, _group, transcript = _transcribed(project_factory)
    out = _cli("transcript", "speakers", "--root", str(root), transcript.id,
               "--map", "SPEAKER_00=a podcast host", "--map", 'SPEAKER_01="Andrew Keen"')
    assert out["exit_code"] == 0, out
    assert [(s["label"], s["name"]) for s in out["speakers"]] == [("SPEAKER_00", "a podcast host"), ("SPEAKER_01", "Andrew Keen")]
    bad = _cli("transcript", "speakers", "--root", str(root), transcript.id, "--map", "SPEAKER_09=X")
    assert bad["exit_code"] == 1 and "no speaker SPEAKER_09" in bad["error"]


def test_cli_transcribe_prices_refuses_then_runs_with_a_budget(project_factory, fake_deepgram):
    root, shoot, group = project_factory(seconds=3.0)
    source = shoot.sources[0].id
    base = ("ingest", "transcribe", "--root", str(root), "--shoot", shoot.id, "--source-id", source)
    priced = _cli("ingest", "transcribe", "--root", str(root), "--sync-group", group.id, "--estimate")
    assert (priced["amount"], priced["unit"], priced["audio_path"]) == (0.01, "usd", shoot.sources[0].audio_proxy_path)
    refused = _cli(*base)
    assert refused["exit_code"] == 1 and "post budget set --id transcribe-1 --cap 0.01 --unit usd" in refused["error"]
    assert _cli("budget", "set", "--root", str(root), "--id", "t1", "--cap", "0.01", "--unit", "usd")["exit_code"] == 0

    done = _cli(*base, "--budget", "t1", "--by", "travis")
    assert done["exit_code"] == 0, done
    assert (done["state"], done["words"], done["speakers"]) == ("ok", 6, ["SPEAKER_00", "SPEAKER_01"])
    assert len(fake_deepgram.requests) == 1
    assert Path(shoot.sources[0].audio_proxy_path).stat().st_size == int(fake_deepgram.requests[0]["headers"]["Content-Length"])
