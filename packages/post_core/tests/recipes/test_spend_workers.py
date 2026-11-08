"""T31: real-mode spending workers estimate before calling the provider, refuse (exit 2) with
no estimate, and never record a real call as costing 0. Real mode is exercised in-process
with every Higgsfield entry point replaced by a fake -- nothing here can reach a provider
(the module-level `subprocess.run`s are also booby-trapped)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from post_core.graph.types import Cost
from post_core.recipes import models
from post_core.recipes.workers import _common, endframe_generate, higgsfield_cli, still_generate, video_generate
from post_core.workers.contract import parse_line


def _boom(*_a, **_k):
    raise AssertionError("a real provider call was attempted")


@pytest.fixture
def real_mode(monkeypatch):
    monkeypatch.delenv("POST3_FAKE_PROVIDERS", raising=False)
    # Swap the modules' own `subprocess` binding (not the global one ffmpeg helpers use).
    monkeypatch.setattr(higgsfield_cli, "subprocess", SimpleNamespace(run=_boom))
    monkeypatch.setattr(models, "subprocess", SimpleNamespace(run=_boom))
    monkeypatch.setattr(higgsfield_cli, "upload_image", lambda path: "upload-id")
    calls: list = []

    def fake_generate(model, args):
        calls.append((model, args))
        return {"id": "job-1"}

    def fake_download(job, dest):
        if dest.suffix == ".mp4":
            _common.placeholder_video(dest, label="fake", seconds=1.0)  # local ffmpeg, not a provider
        else:
            dest.write_bytes(b"png")

    monkeypatch.setattr(higgsfield_cli, "generate", fake_generate)
    monkeypatch.setattr(higgsfield_cli, "download", fake_download)
    return calls


def _events(capsys) -> list[dict]:
    return [e for e in (parse_line(line) for line in capsys.readouterr().out.splitlines()) if e]


def _still_argv(tmp_path):
    return ["--node-id", "n1", "--prompt", "a cat", "--out", str(tmp_path / "image.png")]


def test_real_worker_with_no_estimate_exits_2_without_calling_the_provider(tmp_path, monkeypatch, real_mode, capsys):
    monkeypatch.setattr(models, "estimate_still", lambda *a, **k: None)
    assert still_generate.main(_still_argv(tmp_path)) == 2
    assert real_mode == []
    result = [e for e in _events(capsys) if e["kind"] == "result"][-1]
    assert result["ok"] is False
    assert "will not spend blind" in result["detail"]
    assert not any(e["kind"] == "cost" for e in _events(capsys))


@pytest.mark.parametrize("estimate", [
    lambda *a, **k: Cost(amount=0.0, unit="credits", provider="higgsfield"),
    lambda *a, **k: (_ for _ in ()).throw(RuntimeError("cost endpoint down")),
])
def test_real_worker_refuses_a_zero_or_failed_estimate(tmp_path, monkeypatch, real_mode, capsys, estimate):
    monkeypatch.setattr(models, "estimate_still", estimate)
    argv = ["--node-id", "n1", "--prompt", "p", "--frame", str(tmp_path / "f.png"), "--out", str(tmp_path / "e.png")]
    assert endframe_generate.main(argv) == 2
    assert real_mode == []


def test_real_worker_records_the_estimate_never_zero(tmp_path, monkeypatch, real_mode, capsys):
    monkeypatch.setattr(models, "estimate_still", lambda *a, **k: Cost(amount=2.0, unit="credits", provider="higgsfield"))
    assert still_generate.main(_still_argv(tmp_path)) == 0
    assert len(real_mode) == 1
    costs = [e for e in _events(capsys) if e["kind"] == "cost"]
    assert len(costs) == 1
    assert costs[0]["amount"] == 2.0 and costs[0]["unit"] == "credits" and costs[0]["estimated"] is True


def test_real_worker_records_the_providers_own_amount_when_reported(tmp_path, monkeypatch, real_mode, capsys):
    monkeypatch.setattr(models, "estimate_video", lambda *a, **k: Cost(amount=5.0, unit="credits", provider="higgsfield"))
    monkeypatch.setattr(higgsfield_cli, "generate", lambda model, args: {"id": "j", "credits_spent": 4.5})
    argv = [
        "--node-id", "v1", "--duration", "1", "--motion-prompt", "pan", "--start-image", str(tmp_path / "s.png"),
        "--out", str(tmp_path / "video.mp4"),
    ]
    assert video_generate.main(argv) == 0
    costs = [e for e in _events(capsys) if e["kind"] == "cost"]
    assert [(c["amount"], c["estimated"]) for c in costs] == [(4.5, False)]


def test_cost_is_recorded_even_if_the_download_fails_after_the_paid_call(tmp_path, monkeypatch, real_mode, capsys):
    monkeypatch.setattr(models, "estimate_still", lambda *a, **k: Cost(amount=2.0, unit="credits", provider="higgsfield"))
    monkeypatch.setattr(higgsfield_cli, "download", lambda job, dest: (_ for _ in ()).throw(OSError("network")))
    assert still_generate.main(_still_argv(tmp_path)) == 1
    assert [e["amount"] for e in _events(capsys) if e["kind"] == "cost"] == [2.0]


def test_reported_cost_reads_only_cost_named_fields():
    assert higgsfield_cli.reported_cost({"credits": 900}) is None  # could be a balance: never read
    assert higgsfield_cli.reported_cost({"cost": 0}) is None
    assert higgsfield_cli.reported_cost({"credits_used": 3}) == 3.0
