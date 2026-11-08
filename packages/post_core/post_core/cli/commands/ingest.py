"""`post ingest proxy|peaks|transcribe|import-transcript`, `post transcript speakers`.

Thin calls into `post_core.ingest`'s existing functions (AGENTS.md: "if a core function is
missing, add it to the owning package, not the CLI" -- nothing here does new work, it just
finds the `Source`/`Shoot` on disk, calls the core function, and writes the result path (or
a new `Transcript`) back). T35: `transcribe` is a queued, authorised spend (Deepgram, `usd`):
`--estimate` prices it, `--budget` (made with `post budget set`) pays for it, and the job runs
here until it ends. `import-transcript` never spends -- it is the free path.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from ...ingest import audio_proxy as audio_proxy_mod, peaks as peaks_mod, proxy as proxy_mod
from ...ingest.transcribe import importer, job as transcribe_job, speakers as speakers_mod
from ...ingest.transcribe.link import add_transcript, latest_for_group
from ...queue.budget import SpendNotAuthorized
from ...model.shoot import Shoot
from ...store import store as store_module
from ...store.paths import store_root
from ..output import CLIError
from ..context import resolve_project_root


def _load_shoot_and_source(root: Path, shoot_id: str, source_id: str):
    shoot, revision = store_module.read(root, "shoot", shoot_id)
    source = next((s for s in shoot.sources if s.id == source_id), None)
    if source is None:
        raise CLIError(f"shoot {shoot_id!r} has no source {source_id!r}")
    return shoot, revision, source


def _write_source_update(root: Path, shoot: Shoot, revision: int, source_id: str, **fields) -> Shoot:
    new_sources = [
        s.model_copy(update=fields) if s.id == source_id else s for s in shoot.sources
    ]
    updated = shoot.model_copy(update={"sources": new_sources})
    store_module.write(root, "shoot", updated, expected_rev=revision)
    return updated


def ingest_proxy(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    shoot, revision, source = _load_shoot_and_source(root, args.shoot, args.source_id)
    out_dir = store_root(root) / "proxies"
    start = getattr(args, "start", None)
    duration = getattr(args, "duration", None)
    try:
        out = proxy_mod.build_proxy(
            source.path, out_dir, source.content_fingerprint, height=args.height, force=args.force,
            start=start, duration=duration,
        )
    except proxy_mod.ProxyError as exc:
        raise CLIError(str(exc)) from exc
    partial = start is not None or duration is not None
    # Even a partial (smoke) proxy is a real, playable proxy file -- record it as the
    # source's current proxy so the API can serve it. A later full-proxy build (no
    # --start/--duration) naturally overwrites this with the complete file.
    _write_source_update(root, shoot, revision, source.id, proxy_path=str(out))
    return {"source_id": source.id, "proxy_path": str(out), "partial": partial}


def ingest_audio(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    shoot, revision, source = _load_shoot_and_source(root, args.shoot, args.source_id)
    out_dir = store_root(root) / "proxies"
    try:
        out = audio_proxy_mod.build_audio_proxy(
            source.path, out_dir, source.content_fingerprint, force=args.force,
        )
    except audio_proxy_mod.AudioProxyError as exc:
        raise CLIError(str(exc)) from exc
    _write_source_update(root, shoot, revision, source.id, audio_proxy_path=str(out))
    return {"source_id": source.id, "audio_proxy_path": str(out)}


def ingest_peaks(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    shoot, revision, source = _load_shoot_and_source(root, args.shoot, args.source_id)
    out_path = store_root(root) / "peaks" / f"{source.content_fingerprint}.peaks"
    try:
        out = peaks_mod.build_peaks(source.path, out_path, samples_per_sec=args.rate)
    except peaks_mod.PeaksError as exc:
        raise CLIError(str(exc)) from exc
    _write_source_update(root, shoot, revision, source.id, peaks_path=str(out))
    return {"source_id": source.id, "peaks_path": str(out)}


def _sync_group_id(root: Path, args: argparse.Namespace) -> str:
    if getattr(args, "sync_group", None):
        return args.sync_group
    if not (args.shoot and args.source_id):
        raise CLIError("name the recording: --sync-group <id>, or --shoot <id> --source-id <id>")
    shoot, _revision, source = _load_shoot_and_source(root, args.shoot, args.source_id)
    group = next((g for g in shoot.sync_groups if source.id in g.source_ids), None)
    if group is None:
        raise CLIError(f"source {source.id!r} is not in any sync group of shoot {shoot.id!r}")
    return group.id


def ingest_transcribe(args: argparse.Namespace) -> dict:
    """T35: price (`--estimate`) or queue + run a paid transcription of the group's audio
    proxy. Never call this from a test without `$DEEPGRAM_API_URL` on a local fake server."""
    root = resolve_project_root(args.root)
    sync_group_id = _sync_group_id(root, args)
    try:
        if args.estimate or not args.budget:
            estimate = transcribe_job.estimate(root, sync_group_id, args.provider)
            if args.estimate:
                return estimate
            raise CLIError(
                f"Transcribing costs about ${estimate['amount']} ({estimate['minutes']} min x "
                f"${estimate['usd_per_minute']}/min, Deepgram), so it needs a budget: `post budget set --id "
                f"transcribe-1 --cap {estimate['amount']} --unit usd`, then add `--budget transcribe-1`."
            )
        queued = transcribe_job.enqueue_transcription(root, sync_group_id, budget_id=args.budget,
                                                      by=args.by or "cli", provider=args.provider)
    except (transcribe_job.TranscribeError, SpendNotAuthorized) as exc:
        raise CLIError(str(exc)) from exc
    row = transcribe_job.run_job(root, sync_group_id, queued["job_id"])
    if row.get("state") != "ok":
        raise CLIError(f"transcription {row.get('state')}: {row.get('summary')} (job {queued['job_id']})")
    shoot, _group = transcribe_job.find_group(root, sync_group_id)
    transcript = latest_for_group(root, shoot, sync_group_id)
    return {**queued, "state": row["state"], "summary": row["summary"], "transcript_id": transcript.id,
            "words": len(transcript.words), "speakers": speakers_mod.labels(transcript)}


def transcript_speakers(args: argparse.Namespace) -> dict:
    """`post transcript speakers <id> [--map SPEAKER_00="a podcast host" ...]`: name speakers
    (stored on the transcript), then list each one with a sample to identify them by."""
    root = resolve_project_root(args.root)
    try:
        if args.map:
            transcript = speakers_mod.set_names(root, args.transcript_id, speakers_mod.parse_map(args.map))
        else:
            transcript, _revision = store_module.read(root, "transcript", args.transcript_id)
    except ValueError as exc:
        raise CLIError(str(exc)) from exc
    return {"transcript_id": transcript.id, "speakers": speakers_mod.summary(transcript)}


def ingest_import_transcript(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    shoot, _revision = store_module.read(root, "shoot", args.shoot)
    if not any(args.sync_group == g.id for g in shoot.sync_groups):
        raise CLIError(f"shoot {args.shoot!r} has no sync group {args.sync_group!r}")

    text = Path(args.path).read_text(encoding="utf-8")
    fmt = args.format or importer.guess_format(args.path)
    try:
        words = importer.import_words(text, fmt)
    except (ValueError, KeyError) as exc:
        raise CLIError(str(exc)) from exc
    transcript = add_transcript(root, shoot.id, importer.words_to_transcript(
        words, sync_group_id=args.sync_group, provider=f"import:{fmt}",
        fingerprint=args.fingerprint or f"import:{Path(args.path).name}",
    ))
    return {"transcript_id": transcript.id, "sync_group_id": args.sync_group, "words": len(transcript.words),
            "speakers": transcript.speakers}


__all__ = [
    "ingest_proxy", "ingest_audio", "ingest_peaks", "ingest_transcribe", "ingest_import_transcript",
    "transcript_speakers",
]
