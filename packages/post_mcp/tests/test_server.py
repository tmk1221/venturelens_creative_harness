"""Every tool end to end on the synthetic eval fixture (ffmpeg lavfi; no network, no paid calls)."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest
from mcp.server.fastmcp.exceptions import ToolError

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "evals"))

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("post") is None,
                                reason="needs ffmpeg and the post CLI on PATH")


@pytest.fixture()
def project(tmp_path):
    import make_fixture
    from post_mcp import server as s

    root = str(make_fixture.build(tmp_path / "fx"))
    tid = s.get_project(root)["transcripts"][0]["transcript_id"]
    return s, root, tid


def _reason(exc: ToolError) -> str:
    return json.loads(str(exc))["reason"]


def test_discover_and_read(project):
    s, root, tid = project
    p = s.get_project(root)
    assert p["transcripts"][0]["speakers"] == ["Guest (MSP owner)", "Host"]
    tr = s.read_transcript(root, tid, include_word_ids=True)
    assert tr["sentences"][0]["text"] == "Thanks for joining."
    assert tr["sentences"][0]["words"][0][1] == "Thanks"


def test_create_cut_is_idempotent_by_label(project):
    s, root, tid = project
    a = s.create_cut(root, tid, label="main")
    b = s.create_cut(root, tid, label="main")
    assert a["created"] and not b["created"] and a["cut_id"] == b["cut_id"]
    assert len(s.get_project(root)["cuts"]) == 1


def test_remove_then_undo(project):
    s, root, tid = project
    cut = s.create_cut(root, tid, label="main")
    sent = next(x for x in s.read_transcript(root, tid)["sentences"] if "Cancun" in x["text"])
    after = s.remove_words(root, cut["cut_id"], sent["first_word_id"], sent["last_word_id"])
    assert "Cancun" not in " ".join(p["text"] for p in after["passages"])
    assert len(after["passages"]) == 2
    back = s.undo_edit(root, cut["cut_id"])
    assert "Cancun" in " ".join(p["text"] for p in back["passages"])


def test_short_visual_and_export(project):
    s, root, tid = project
    cut = s.create_cut(root, tid, label="main")
    pending = s.suggest_visuals(root, cut["cut_id"])["pending"]
    assert pending
    with_visual = s.accept_visual(root, cut["cut_id"], pending[0]["suggestion_id"])
    assert len(with_visual["visuals"]) == 1  # picture + overlay of one beat count once
    sents = s.read_transcript(root, tid)["sentences"]
    pick = [[x["first_word_id"], x["last_word_id"]] for x in sents if "CFO" in x["text"] or "wire" in x["text"]]
    short = s.make_short(root, cut["cut_id"], pick, label="s1")
    assert short["aspect"] == "9:16" and short["parent_cut_id"] == cut["cut_id"]
    assert "CFO" in short["passages"][0]["text"] and "Cancun" not in str(short["passages"])
    assert Path(s.export_timeline(root, cut["cut_id"])["path"]).is_file()


def test_move_words_makes_an_opening_line(project):
    s, root, tid = project
    cut = s.create_cut(root, tid, label="main")
    sents = s.read_transcript(root, tid)["sentences"]
    hook = next(x for x in sents if x["text"].startswith("Honestly"))
    out = s.move_words(root, cut["cut_id"], hook["first_word_id"], hook["last_word_id"], sents[0]["first_word_id"])
    assert out["passages"][0]["text"].startswith("Honestly")
    assert s.undo_edit(root, cut["cut_id"])["passages"][0]["text"].startswith("Thanks")


def test_errors_name_a_fix(project):
    s, root, tid = project
    cut = s.create_cut(root, tid, label="main")
    cases = {
        "unknown_word_id": lambda: s.remove_words(root, cut["cut_id"], "x", "y"),
        "not_found": lambda: s.read_cut(root, "missing"),
        "unknown_passage_id": lambda: s.move_passage(root, cut["cut_id"], "stale", 0),
        "unknown_suggestion_id": lambda: s.accept_visual(root, cut["cut_id"], "nope"),
        "not_a_project": lambda: s.get_project("/"),
        "bad_aspect": lambda: s.create_cut(root, tid, aspect="tall", label="x"),
    }
    for reason, call in cases.items():
        with pytest.raises(ToolError) as info:
            call()
        assert _reason(info.value) == reason
        assert json.loads(str(info.value))["fix"]
