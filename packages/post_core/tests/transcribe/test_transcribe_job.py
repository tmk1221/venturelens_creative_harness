"""T35: transcription as a queued, authorised spend -- against a local fake Deepgram only
(`fake_deepgram`), never the network. Streaming upload of the audio proxy as `audio/mp4`,
the refusals (no proxy, no/unknown/too-small budget), the 43-minute estimate, the job through
the real executor + worker subprocess, a failed attempt retried, and fake mode."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from post_core.ingest.transcribe import base, deepgram, job as transcribe_job
from post_core.ingest.transcribe.link import latest_for_group
from post_core.queue import budget as budget_mod, db as db_mod
from post_core.queue.budget import BudgetUnitMismatch, OverBudget, SpendNotAuthorized, UnknownBudget
from post_core.store import store as store_module
from post_core.store.paths import store_root


def _jobs(root: Path) -> list[dict]:
    with db_mod.open_db(root) as con:
        return [dict(r) for r in con.execute("SELECT * FROM job").fetchall()]


def _events(root: Path, job_id: str) -> list[dict]:
    with db_mod.open_db(root) as con:
        rows = con.execute("SELECT json FROM event WHERE job_id=? ORDER BY seq", (job_id,)).fetchall()
    return [json.loads(r["json"]) for r in rows]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def transcribe_api_key() -> str:
    return os.environ["DEEPGRAM_API_KEY"]  # the fixture's fake key, never the real one


def test_upload_streams_from_disk_with_content_length(fake_deepgram, tmp_path, monkeypatch):
    audio = tmp_path / "x.audio.m4a"
    audio.write_bytes(os.urandom(1_000_000))
    reads: list[int] = []
    original = deepgram.StreamedBody.read

    def spy(self, size=-1):
        data = original(self, size)
        reads.append(len(data))
        return data

    monkeypatch.setattr(deepgram.StreamedBody, "read", spy)
    progress: list[tuple[int, int]] = []
    reply = deepgram.post_audio(audio, transcribe_api_key(), on_progress=lambda s, t: progress.append((s, t)))

    assert reply["results"]["channels"][0]["alternatives"][0]["transcript"] == "hello world this is a test"
    (req,) = fake_deepgram.requests
    assert req["headers"]["Content-Type"] == "audio/mp4"
    assert req["headers"]["Content-Length"] == str(1_000_000)
    assert "Transfer-Encoding" not in req["headers"]
    assert req["path"].startswith("/v1/listen?model=nova-3&") and "diarize=true" in req["path"]
    assert req["headers"]["Authorization"] == f"Token {transcribe_api_key()}"
    assert _sha(req["body"]) == _sha(audio.read_bytes())
    # Streamed: many bounded reads straight from the file, never one whole-file read.
    assert len(reads) > 10 and max(reads) <= deepgram.CHUNK
    assert progress[-1] == (1_000_000, 1_000_000) and len(progress) > 10


def test_queued_job_uploads_the_audio_proxy_and_links_the_transcript(fake_deepgram, project_factory):
    root, shoot, group = project_factory(seconds=3.0)
    estimate = transcribe_job.estimate(root, group.id)
    assert estimate["amount"] == 0.01 and estimate["unit"] == "usd"
    budget_mod.set_budget(root, "click-1", estimate["amount"], "usd")

    queued = transcribe_job.enqueue_transcription(root, group.id, budget_id="click-1", by="test")
    (row,) = _jobs(root)
    assert (row["lane"], row["state"], row["budget_id"], row["estimate"]) == ("remote", "queued", "click-1", 0.01)
    row = transcribe_job.run_job(root, group.id, queued["job_id"], poll=0.05)
    assert row["state"] == "ok", row["summary"]

    (req,) = fake_deepgram.requests
    proxy = Path(shoot.sources[0].audio_proxy_path)
    assert _sha(req["body"]) == _sha(proxy.read_bytes())  # the proxy, not the camera file
    assert req["headers"]["Content-Type"] == "audio/mp4"
    assert req["headers"]["Content-Length"] == str(proxy.stat().st_size)

    shoot_now, _rev = store_module.read(root, "shoot", shoot.id)
    transcript = latest_for_group(root, shoot_now, group.id)
    assert transcript is not None and shoot_now.transcript_ids == [transcript.id]
    assert [w.speaker for w in transcript.words] == ["SPEAKER_00"] * 2 + ["SPEAKER_01"] * 4
    assert budget_mod.get_budget(root, "click-1")["spent"] == pytest.approx(0.01)

    events = _events(root, queued["job_id"])
    kinds = [e["kind"] for e in events]
    assert "progress" in kinds and kinds[-1] == "result" and events[-1]["ok"] is True
    assert any(e["kind"] == "progress" and e["i"] == 100 and e["n"] == 100 for e in events)
    (cost,) = [e for e in events if e["kind"] == "cost"]
    assert (cost["amount"], cost["unit"], cost["estimated"]) == (0.01, "usd", True)
    manifests = list((store_root(root) / "artifacts" / transcribe_job.TYPE_ID).glob("*/manifest.json"))
    (manifest,) = [json.loads(m.read_text()) for m in manifests]
    assert sorted(o["path"] for o in manifest["outputs"]) == ["deepgram.json", "transcript_ref.json"]

    with pytest.raises(transcribe_job.AlreadyTranscribed):
        transcribe_job.enqueue_transcription(root, group.id, budget_id="click-1", by="test")


def test_missing_audio_proxy_is_refused_before_anything_is_written(fake_deepgram, project_factory):
    root, _shoot, group = project_factory(with_proxy=False)
    budget_mod.set_budget(root, "b", 1.0, "usd")
    for call in (lambda: transcribe_job.estimate(root, group.id),
                 lambda: transcribe_job.enqueue_transcription(root, group.id, budget_id="b", by="t")):
        with pytest.raises(transcribe_job.NoAudioProxy, match="run ingest audio first"):
            call()
    assert _jobs(root) == [] and fake_deepgram.requests == []
    assert not (store_root(root) / "workflows" / f"transcribe-{group.id}.json").exists()


def test_unauthorised_spend_is_refused_and_queues_nothing(fake_deepgram, project_factory):
    root, _shoot, group = project_factory(seconds=3.0)
    budget_mod.set_budget(root, "too-small", 0.005, "usd")
    budget_mod.set_budget(root, "credits", 100, "credits")
    cases = [(None, SpendNotAuthorized), ("never-made", UnknownBudget), ("too-small", OverBudget),
             ("credits", BudgetUnitMismatch)]
    for budget_id, error in cases:
        with pytest.raises(error):
            transcribe_job.enqueue_transcription(root, group.id, budget_id=budget_id, by="t")
    assert _jobs(root) == [] and fake_deepgram.requests == []
    assert not (store_root(root) / "workflows" / f"transcribe-{group.id}.json").exists()
    with db_mod.open_db(root) as con:
        assert con.execute("SELECT COUNT(*) AS c FROM authorisation").fetchone()["c"] == 0


def test_estimate_for_a_43_minute_episode(project_factory, tmp_path, m4a):
    root, shoot, group = project_factory(seconds=1.0)
    long_proxy = m4a(store_root(root) / "proxies" / "ep37.audio.m4a", 43 * 60)
    shoot, revision = store_module.read(root, "shoot", shoot.id)
    sources = [s.model_copy(update={"audio_proxy_path": str(long_proxy)}) for s in shoot.sources]
    store_module.write(root, "shoot", shoot.model_copy(update={"sources": sources}), expected_rev=revision)

    estimate = transcribe_job.estimate(root, group.id)
    assert estimate["minutes"] == pytest.approx(43.0, abs=0.02)
    assert estimate["usd_per_minute"] == transcribe_job.DEFAULT_USD_PER_MINUTE == 0.0063
    assert (estimate["amount"], estimate["unit"]) == (0.28, "usd")  # 43 x 0.0063 = 0.2709, up to the cent
    assert estimate["audio_path"] == str(long_proxy)

    (store_root(root) / "config.json").write_text(json.dumps({"deepgram_usd_per_minute": 0.01}))
    assert transcribe_job.estimate(root, group.id)["amount"] == 0.43


def test_local_provider_points_at_the_free_import_path(project_factory):
    root, _shoot, group = project_factory(seconds=1.0)
    with pytest.raises(transcribe_job.TranscribeError, match="post ingest import-transcript"):
        transcribe_job.estimate(root, group.id, provider="local")
    with pytest.raises(NotImplementedError, match="import-transcript"):
        base.get("local").transcribe("/tmp/whatever.m4a", {})


def test_a_failed_attempt_is_reported_and_a_new_click_retries(fake_deepgram, project_factory):
    root, _shoot, group = project_factory(seconds=3.0)
    fake_deepgram.status = 500
    budget_mod.set_budget(root, "click-1", 0.01, "usd")
    first = transcribe_job.enqueue_transcription(root, group.id, budget_id="click-1", by="t")
    row = transcribe_job.run_job(root, group.id, first["job_id"], poll=0.05)
    assert row["state"] == "failed" and "Deepgram answered HTTP 500" in row["summary"]
    assert budget_mod.get_budget(root, "click-1")["spent"] == 0  # Deepgram refused: nothing was spent

    fake_deepgram.status = 200
    budget_mod.set_budget(root, "click-2", 0.01, "usd")
    second = transcribe_job.enqueue_transcription(root, group.id, budget_id="click-2", by="t")
    assert transcribe_job.run_job(root, group.id, second["job_id"], poll=0.05)["state"] == "ok"
    assert len(fake_deepgram.requests) == 2


def test_fake_mode_writes_a_placeholder_and_sends_nothing(fake_deepgram, project_factory, monkeypatch):
    monkeypatch.setenv("POST3_FAKE_PROVIDERS", "1")
    root, shoot, group = project_factory(seconds=3.0)
    budget_mod.set_budget(root, "b", 0.01, "usd")
    queued = transcribe_job.enqueue_transcription(root, group.id, budget_id="b", by="t")
    assert transcribe_job.run_job(root, group.id, queued["job_id"], poll=0.05)["state"] == "ok"
    assert fake_deepgram.requests == []
    shoot_now, _rev = store_module.read(root, "shoot", shoot.id)
    transcript = latest_for_group(root, shoot_now, group.id)
    assert transcript.provider == "fake" and transcript.words and transcript.words[0].text == "This"
