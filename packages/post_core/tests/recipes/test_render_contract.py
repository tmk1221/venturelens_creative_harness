"""T37 acceptance: `asset.verify`'s render contract against ffmpeg-generated fixtures -- a clip
that is too short, at the wrong fps, ends frozen, has no picture, or is the wrong aspect each
fails with one plain sentence, and that sentence becomes the node's failure summary (what
the card shows)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from post_core.queue.executor import Executor
from post_core.recipes import render_contract
from post_core.recipes.workers import asset_verify
from post_core.workers.contract import PREFIX
from post_core.workers.runner import FAILED, RunResult

NTSC = "24000/1001"


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def _clip(out: Path, seconds: float, rate: str = NTSC, size: str = "160x200", hold: float = 0.0) -> Path:
    vf = ["-vf", f"tpad=stop_mode=clone:stop_duration={hold}"] if hold else []
    _ffmpeg("-f", "lavfi", "-i", f"testsrc2=s={size}:r={rate}:d={seconds}", *vf, "-pix_fmt", "yuv420p", str(out))
    return out


@pytest.fixture(scope="module")
def clips(tmp_path_factory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("contract")
    audio = d / "audio_only.m4a"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=3", str(audio))
    return {
        "good": _clip(d / "good.mp4", 3.0),
        "short": _clip(d / "short.mp4", 1.0),
        "wrong_fps": _clip(d / "wrong_fps.mp4", 3.0, rate="30"),
        "frozen_tail": _clip(d / "frozen_tail.mp4", 2.0, hold=1.0),
        "wrong_aspect": _clip(d / "wrong_aspect.mp4", 3.0, size="320x180"),
        "audio_only": audio,
    }


def _verify(project_root: Path, media: Path, *extra: str) -> int:
    argv = [
        "--node-id", "b1-verify", "--project-root", str(project_root), "--media", str(media),
        "--record-as-node", "b1-approve", "--record-as-hash", "h" * 64,
        "--expect-fps", NTSC, "--min-seconds", "2.5", "--expect-aspect", "4:5", *extra,
    ]
    return asset_verify.main(argv)


def _result(capsys) -> dict:
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith(PREFIX)]
    events = [json.loads(ln[len(PREFIX):]) for ln in lines]
    return next(e for e in reversed(events) if e["kind"] == "result")


@pytest.fixture
def in_tmp(tmp_path, monkeypatch, project_root):
    monkeypatch.chdir(tmp_path)  # the worker writes verify.json into its cwd
    return project_root


def test_good_clip_passes_and_is_recorded(in_tmp, clips, capsys):
    code = _verify(in_tmp, clips["good"], "--reject-frozen-tail")
    result = _result(capsys)
    assert code == 0 and result["ok"] is True, result
    from post_core import store

    asset, _rev = store.read(in_tmp, "asset", "h" * 64)
    assert (asset.fps.num, asset.fps.den) == (24000, 1001)


@pytest.mark.parametrize("name,sentence", [
    ("short", "The clip is 1.00 s long but the beat needs at least 2.50 s."),
    ("wrong_fps", "The clip is 30 fps but the project is 23.976 fps."),
    ("frozen_tail", "is a frozen copy of an earlier frame and the brief does not ask for a hold."),
    ("wrong_aspect", "The clip is 320x180, not 4:5."),
    ("audio_only", "The file has no video stream."),
])
def test_each_broken_rule_fails_with_one_sentence(in_tmp, clips, capsys, name, sentence):
    code = _verify(in_tmp, clips[name], "--reject-frozen-tail")
    result = _result(capsys)
    assert code == 1 and result["ok"] is False
    verify = json.loads(Path("verify.json").read_text())
    assert verify["ok"] is False and len(verify["problems"]) == 1  # just the broken rule
    assert result["detail"] == verify["problems"][0]
    assert sentence in result["detail"]


def test_frozen_tail_is_measured(clips):
    media = render_contract.probe(clips["frozen_tail"])
    assert render_contract.frozen_tail_seconds(clips["frozen_tail"], media.seconds) == pytest.approx(1.0, abs=0.1)
    good = render_contract.probe(clips["good"])
    assert render_contract.frozen_tail_seconds(clips["good"], good.seconds) == 0.0


def test_a_hold_the_brief_asked_for_passes(in_tmp, clips, capsys):
    code = _verify(in_tmp, clips["frozen_tail"])  # no --reject-frozen-tail: hold allowed
    assert code == 0 and _result(capsys)["ok"] is True


def test_failure_summary_is_the_workers_sentence():
    sentence = "The clip is 30 fps but the project is 23.976 fps."
    result = RunResult(
        exit_code=1, outcome=FAILED, artifacts=[], cost_total={}, tail="##POST {...}",
        events=[{"kind": "result", "ok": False, "detail": sentence}],
    )
    assert Executor._failure_summary(result) == sentence
    silent = RunResult(exit_code=1, outcome=FAILED, events=[], artifacts=[], cost_total={}, tail="boom")
    assert Executor._failure_summary(silent) == "the worker failed (cause: exit-1): boom"
