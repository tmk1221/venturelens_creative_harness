"""`python -m post_core.ingest.transcribe.job_worker ...`: one queued transcription (T35),
speaking the T03 `##POST` contract. Built by `job.build_cmd`; run by the executor only after
`queue.enqueue` accepted an authorised spend for it.

Events: `step` and `progress` (upload %, so a 43-minute episode never looks hung), then the
`cost` the moment Deepgram answers (a paid call counts even if a later step fails), then the
transcript is written atomically into the store, linked to its sync group, and declared as
artifacts (`transcript_ref.json`, plus Deepgram's raw reply so re-mapping never re-spends).
`POST3_FAKE_PROVIDERS=1`: a placeholder transcript, nothing sent anywhere.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from ...cli.config import load_env
from ...graph.types import Cost
from ...model.transcript import Transcript, Word
from ...recipes.models import fake_mode
from ...recipes.workers._spend import cost_event, estimate_or_refuse
from ...store.atomic import atomic_write_bytes
from ...workers.contract import EXIT_FAILED, EXIT_OK, EXIT_USAGE, emit
from . import deepgram
from .job import estimate_usd
from .link import add_transcript

UPLOAD_LABEL = "Uploading the audio to Deepgram"
PLACEHOLDER = "This is a placeholder transcript from fake providers and nothing was sent anywhere".split()


def placeholder_words(duration: float) -> list[dict]:
    """Fake mode: a word every 0.45 s, the speaker switching every 20 s, a pause per sentence."""
    words: list[dict] = []
    t, i = 0.0, 0
    while t + 0.4 <= max(duration, 1.0) and len(words) < 20000:
        words.append({"text": PLACEHOLDER[i % len(PLACEHOLDER)], "start": round(t, 3), "end": round(t + 0.4, 3),
                      "speaker": f"SPEAKER_{int(t // 20) % 2:02d}", "confidence": 1.0})
        i += 1
        t += 0.45 + (1.6 if i % len(PLACEHOLDER) == 0 else 0.0)
    return words


def _write_json(path: Path, payload: dict) -> Path:
    atomic_write_bytes(path, json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"))
    return path


def _artifact(path: Path, role: str) -> None:
    emit("artifact", path=str(path), role=role, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def _fail(message: str) -> int:
    emit("err", text=message)
    emit("result", ok=False, detail=message)
    print(f"Transcription failed: {message}", flush=True)  # the job's summary is the last line
    return EXIT_FAILED


def _upload(args: argparse.Namespace) -> dict:
    emit("step", label=UPLOAD_LABEL)
    last = {"pct": -1}

    def on_progress(sent: int, total: int) -> None:
        pct = int(sent * 100 / total) if total else 100
        if pct >= last["pct"] + 2 or (pct == 100 and last["pct"] != 100):
            last["pct"] = pct
            emit("progress", i=pct, n=100, label=UPLOAD_LABEL)

    data = deepgram.post_audio(args.audio, deepgram.api_key_from({}), content_type=deepgram.content_type_for(args.audio),
                               on_progress=on_progress)
    emit("step", label="Deepgram answered; reading the words")
    return data


def run(args: argparse.Namespace) -> int:
    load_env()  # never overrides a real env var; a worker the API/CLI started already has the keys
    root = Path(args.project_root).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cost = estimate_or_refuse(
        "transcribe", args.provider,
        lambda: Cost(amount=estimate_usd(args.duration_seconds, args.usd_per_minute), unit="usd", provider=args.provider),
    )
    if cost is None:
        return EXIT_USAGE

    artifacts: list[tuple[Path, str]] = []
    if fake_mode():
        emit("step", label="Fake providers: writing a placeholder transcript (nothing is sent)")
        emit("progress", i=100, n=100, label="Placeholder transcript")
        emit("cost", **cost_event(cost))
        word_dicts, provider = placeholder_words(args.duration_seconds), "fake"
    else:
        try:
            data = _upload(args)
        except deepgram.DeepgramError as exc:
            return _fail(str(exc))
        emit("cost", **cost_event(cost))  # Deepgram reports no amount: the shown estimate is recorded
        artifacts.append((_write_json(out_dir / "deepgram.json", data), "provider_response"))
        try:
            word_dicts, provider = deepgram.map_response(data), args.provider
        except ValueError as exc:
            return _fail(f"Deepgram's reply couldn't be read ({exc}); it is kept in deepgram.json")

    emit("step", label="Saving the transcript")
    try:
        transcript = add_transcript(root, args.shoot_id, Transcript(
            sync_group_id=args.sync_group_id, provider=provider, fingerprint=args.fingerprint,
            words=[Word(**w) for w in word_dicts],
        ))
    except Exception as exc:  # noqa: BLE001 - reported through the contract, not raised
        return _fail(f"the transcript couldn't be saved: {exc}")
    speakers = sorted({w.speaker for w in transcript.words if w.speaker})
    ref = {"transcript_id": transcript.id, "sync_group_id": transcript.sync_group_id,
           "words": len(transcript.words), "speakers": speakers, "provider": provider}
    artifacts.append((_write_json(out_dir / "transcript_ref.json", ref), "transcript"))
    for path, role in artifacts:
        _artifact(path, role)
    detail = f"Transcribed {len(transcript.words):,} words, {len(speakers)} speaker{'' if len(speakers) == 1 else 's'}."
    emit("result", ok=True, detail=detail, transcript_id=transcript.id)
    print(detail, flush=True)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m post_core.ingest.transcribe.job_worker")
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--provider", default="deepgram")
    ap.add_argument("--audio", required=True, help="the sync group's audio proxy (.m4a)")
    ap.add_argument("--shoot-id", required=True)
    ap.add_argument("--sync-group-id", required=True)
    ap.add_argument("--fingerprint", required=True)
    ap.add_argument("--duration-seconds", type=float, required=True)
    ap.add_argument("--usd-per-minute", type=float, required=True)
    ap.add_argument("--out-dir", required=True)
    return ap


def main(argv: list[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
