#!/usr/bin/env python3
"""T21: open the real 2026-09-09 Acme Automations shoot in v3, read-only on the drive.

HARD RULES (tasks/T21.md): the drive `/Volumes/MediaDrive/Acme Automations` is READ-ONLY
-- this script only ever probes/reads files under it (ffprobe, ffmpeg -i as an input, plain
file reads). Nothing here writes, moves or deletes anything on the drive, opens DaVinci
Resolve, or makes a network/paid call. All output goes under
`~/cc/post3/.demo-acme/` (gitignored).

Resumable: every step reads what's on disk in `.demo-acme/` first and only writes what's
missing, so re-running (or resuming after a partial run) is safe and cheap. `--dry-run`
prints the plan (including probing sources -- ffprobe is read-only) without writing
anything to `.demo-acme/`.

T22: Post is audio-only -- no video proxies. The default (no-flags) run now also builds the
audio proxies (AAC .m4a) + peaks directly (fast, unlike the old video-proxy encode this
replaced), so a single plain invocation is the whole pipeline.

Usage:
    packages/post_core/.venv/bin/python scripts/import_acme_demo.py [--dry-run] [--force]
    packages/post_core/.venv/bin/python scripts/import_acme_demo.py --verify-range
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages" / "post_core"))

from post_core.ingest import audio_proxy as audio_proxy_mod  # noqa: E402
from post_core.ingest import peaks as peaks_mod  # noqa: E402
from post_core.ingest.probe import probe_source  # noqa: E402
from post_core.ingest.transcribe import importer  # noqa: E402
from post_core.model.common import Rational  # noqa: E402
from post_core.model.cut import Cut, Passage  # noqa: E402
from post_core.model.project import Project  # noqa: E402
from post_core.model.shoot import Shoot, Source, SyncGroup, clean_audio_source  # noqa: E402
from post_core.store import store as store_module  # noqa: E402
from post_core.store.paths import store_root  # noqa: E402

DRIVE = Path("/Volumes/MediaDrive/Acme Automations")
SESSION = "2026-09-09"
PROJECT_ROOT = REPO_ROOT / ".demo-acme"
SHOOT_NAME = f"acme-{SESSION}"

# --- inputs (read-only) ---------------------------------------------------------------
VIDEO = {
    "camA_C9102": DRIVE / "Video" / SESSION / "camA-main" / "C9102.MP4",
    "camA_C9103": DRIVE / "Video" / SESSION / "camA-main" / "C9103.MP4",
    "camB_5632": DRIVE / "Video" / SESSION / "camB" / "A_FX30_20260909_5632.MP4",
    "camB_5633": DRIVE / "Video" / SESSION / "camB" / "A_FX30_20260909_5633.MP4",
}
AUDIO = {
    "audio_C9102": DRIVE / "Audio" / SESSION / "synced" / "camA_C9102_Mic2_synced.wav",
    "audio_C9103": DRIVE / "Audio" / SESSION / "synced" / "camA_C9103_Mic2_synced.wav",
}
WORDS = {
    "C9102": DRIVE / "Transcript" / SESSION / "C9102" / "words.json",
    "C9103": DRIVE / "Transcript" / SESSION / "C9103" / "words.json",
}

# --- sync offsets ------------------------------------------------------------------------
# Read from `Audio/2026-09-09/_sync/sync.json` / `sync.md` (the aggregated, documented fit
# -- 10/10 strong anchors per clip, cross-checked against the *_Mic2_synced.wav verify
# files, which report verify_ok=true and drift within a few ms). We do NOT use the raw
# per-clip `_env_sync.json` offset_sec field for the second take of each camera: for C9103
# it reports offset_sec=-716.76 and for 5633 offset_sec=-724.72 (coarse_conf ~8, verify_ok
# false) -- clearly mis-correlated against the wrong window of the multi-hour recorder
# track. sync.md's camA-relative deltas for the same clips (-7.570s for 5633 vs C9103) are
# consistent, high-confidence (10/10 anchors) and durations line up, so those are what we
# use. Group origin = the camA (main a_roll) clip in each group, offset 0.0; the matching
# *_Mic2_synced.wav is already re-synced to that same camA clip (verify_ok=true, offset
# 0.0, duration exactly equal to the camA clip's duration) so its offset is 0.0 too.
GROUPS = [
    {
        "name": "C9102",
        "sources": {"camA_C9102": 0.0, "camB_5632": -2.890, "audio_C9102": 0.0},
        "words": "C9102",
        "angle": "camA_C9102",
    },
    {
        "name": "C9103",
        "sources": {"camA_C9103": 0.0, "camB_5633": -7.570, "audio_C9103": 0.0},
        "words": "C9103",
        "angle": "camA_C9103",
    },
]

def log(*a):
    print(*a, file=sys.stderr)


def _check_drive_readable():
    if not DRIVE.is_dir():
        sys.exit(f"drive not mounted: {DRIVE}")


def probe_all(dry_run: bool) -> dict:
    """Read-only ffprobe of every input file. Safe in --dry-run too (never writes)."""
    probes = {}
    for name, path in {**VIDEO, **AUDIO}.items():
        if not path.is_file():
            sys.exit(f"missing input on drive (read-only check): {path}")
        probes[name] = probe_source(path)
        log(f"probed {name}: {probes[name]['width']}x{probes[name]['height']} "
            f"{probes[name]['fps'].as_float():.3f}fps {probes[name]['duration']:.1f}s "
            f"tc={probes[name]['start_timecode']}")
    return probes


def _find_shoot(root: Path) -> tuple[Shoot, int] | None:
    d = store_root(root) / "shoots"
    if not d.is_dir():
        return None
    for f in sorted(d.glob("*.json")):
        shoot, rev = store_module.read(root, "shoot", f.stem)
        if shoot.name == SHOOT_NAME:
            return shoot, rev
    return None


def build_or_load_shoot(root: Path, probes: dict, dry_run: bool) -> Shoot:
    existing = _find_shoot(root)
    if existing is not None:
        log(f"shoot {existing[0].id!r} already has {len(existing[0].sources)} sources, "
            f"{len(existing[0].sync_groups)} sync groups -- reusing")
        return existing[0]

    sources: dict[str, Source] = {}
    for name, path in {**VIDEO, **AUDIO}.items():
        p = probes[name]
        role = "audio" if name.startswith("audio_") else ("a_roll" if "camA" in name else "b_roll")
        sources[name] = Source(
            path=p["path"], fps=p["fps"], start_timecode=p["start_timecode"],
            role=role, content_fingerprint=p["content_fingerprint"],
        )

    sync_groups: list[SyncGroup] = []
    for g in GROUPS:
        source_ids = {name: sources[name].id for name in g["sources"]}
        offsets = {source_ids[name]: off for name, off in g["sources"].items()}
        sync_groups.append(SyncGroup(source_ids=list(source_ids.values()), offsets=offsets))
        g["_source_ids"] = source_ids  # stash for later steps

    shoot = Shoot(name=SHOOT_NAME, sources=list(sources.values()), sync_groups=sync_groups)
    if dry_run:
        log(f"[dry-run] would write shoot with {len(shoot.sources)} sources, "
            f"{len(shoot.sync_groups)} sync groups")
        shoot._dry_sources = sources  # type: ignore[attr-defined]
        return shoot

    store_module.write(root, "shoot", shoot, expected_rev=0)
    log(f"wrote shoot {shoot.id}")
    return shoot


def _source_by_name(shoot: Shoot, path: Path) -> Source:
    resolved = str(path.resolve())
    for s in shoot.sources:
        if s.path == resolved:
            return s
    raise RuntimeError(f"no Source for {path} in shoot {shoot.id}")


def _group_for(shoot: Shoot, camA_source_id: str) -> SyncGroup:
    for g in shoot.sync_groups:
        if camA_source_id in g.source_ids:
            return g
    raise RuntimeError(f"no sync group covers source {camA_source_id}")


def import_transcripts(root: Path, shoot: Shoot, dry_run: bool) -> dict:
    """One Transcript per SyncGroup, timebase = that group's camA clip (words.json's start/
    end times are already relative to the camA source's own clock, which is the group
    origin at offset 0.0 -- see the offsets comment above)."""
    existing_dir = store_root(root) / "transcripts"
    existing = {}
    if existing_dir.is_dir():
        for f in sorted(existing_dir.glob("*.json")):
            t, _rev = store_module.read(root, "transcript", f.stem)
            existing[t.sync_group_id] = t

    out = {}
    for g in GROUPS:
        camA_name = g["angle"]
        camA_source = _source_by_name(shoot, VIDEO[camA_name])
        sync_group = _group_for(shoot, camA_source.id)
        if sync_group.id in existing:
            t = existing[sync_group.id]
            log(f"transcript for group {g['name']} already imported: {len(t.words)} words")
            out[g["name"]] = t
            continue

        text = WORDS[g["words"]].read_text(encoding="utf-8")
        words = importer.import_words(text, "json")
        fingerprint = f"import:{WORDS[g['words']].name}:{g['words']}"
        transcript = importer.words_to_transcript(
            words, sync_group_id=sync_group.id, provider="import:json", fingerprint=fingerprint,
        )
        log(f"group {g['name']}: {len(transcript.words)} words "
            f"({words[0]['start']:.1f}s - {words[-1]['end']:.1f}s)")
        if dry_run:
            out[g["name"]] = transcript
            continue
        store_module.write(root, "transcript", transcript, expected_rev=0)
        updated = shoot.model_copy(update={"transcript_ids": [*shoot.transcript_ids, transcript.id]})
        store_module.write(root, "shoot", updated, expected_rev=store_module.read(root, "shoot", shoot.id)[1])
        shoot = updated
        out[g["name"]] = transcript
    return out


def _find_cut(root: Path) -> tuple[Cut, int] | None:
    d = store_root(root) / "cuts"
    if not d.is_dir():
        return None
    files = sorted(d.glob("*.json"))
    if not files:
        return None
    cut, rev = store_module.read(root, "cut", files[0].stem)
    return cut, rev


def build_or_load_cut(root: Path, shoot: Shoot, transcripts: dict, probes: dict, dry_run: bool) -> Cut:
    existing = _find_cut(root)
    if existing is not None:
        cut = existing[0]
        log(f"cut {cut.id!r} already has {len(cut.passages)} passages -- reusing")
        return cut

    fps = probes["camA_C9102"]["fps"]
    passages = []
    for g in GROUPS:
        transcript = transcripts[g["name"]]
        if not transcript.words:
            continue
        camA_source = _source_by_name(shoot, VIDEO[g["angle"]])
        passages.append(Passage(
            sync_group_id=transcript.sync_group_id,
            start_word_id=transcript.words[0].id,
            end_word_id=transcript.words[-1].id,
            angle_source_id=camA_source.id,
        ))

    cut = Cut(aspect=Rational(num=16, den=9), fps=fps, passages=passages)
    if dry_run:
        log(f"[dry-run] would write master cut with {len(passages)} passages, "
            f"fps={fps.as_float():.3f}, aspect=16:9")
        return cut
    store_module.write(root, "cut", cut, expected_rev=0)
    log(f"wrote cut {cut.id} with {len(passages)} passages")
    return cut


def do_audio_proxies(root: Path, shoot: Shoot) -> None:
    """T22: Post is audio-only -- no video proxies. One AAC `.m4a` audio proxy per sync
    group, built from that group's `clean_audio_source` (dedicated recorder, falling back to
    the a_roll camera), plus peaks for every dedicated audio-recorder source (unchanged from
    T21)."""
    proxies_dir = store_root(root) / "proxies"
    peaks_dir = store_root(root) / "peaks"
    audio_sources = [s for s in shoot.sources if s.role == "audio"]

    # De-duplicate: two groups could in principle share a clean-audio source.
    audio_proxy_source_ids = {clean_audio_source(shoot, g).id for g in shoot.sync_groups}
    audio_proxy_sources = [s for s in shoot.sources if s.id in audio_proxy_source_ids]

    total_start = time.monotonic()
    total_source_seconds = 0.0
    for source in audio_proxy_sources:
        t0 = time.monotonic()
        out = audio_proxy_mod.build_audio_proxy(source.path, proxies_dir, source.content_fingerprint)
        dt = time.monotonic() - t0
        total_source_seconds += probe_source(source.path)["duration"]
        log(f"audio proxy [{dt:.1f}s]: {source.path} -> {out}")
        _update_source(root, shoot, source.id, audio_proxy_path=str(out))
        shoot, _rev = store_module.read(root, "shoot", shoot.id)

    for source in audio_sources:
        t0 = time.monotonic()
        out_path = peaks_dir / f"{source.content_fingerprint}.peaks"
        out = peaks_mod.build_peaks(source.path, out_path)
        dt = time.monotonic() - t0
        log(f"peaks [{dt:.1f}s]: {source.path} -> {out}")
        _update_source(root, shoot, source.id, peaks_path=str(out))
        shoot, _rev = store_module.read(root, "shoot", shoot.id)

    total = time.monotonic() - total_start
    rate_per_hour = (total / total_source_seconds) * 3600 if total_source_seconds else 0.0
    log(f"audio proxies total: {total:.1f}s for {len(audio_proxy_sources)} audio proxies "
        f"+ {len(audio_sources)} peaks -- {rate_per_hour:.1f}s of wall-clock per hour of audio")


def _update_source(root: Path, shoot: Shoot, source_id: str, **fields) -> None:
    current, rev = store_module.read(root, "shoot", shoot.id)
    new_sources = [s.model_copy(update=fields) if s.id == source_id else s for s in current.sources]
    updated = current.model_copy(update={"sources": new_sources})
    store_module.write(root, "shoot", updated, expected_rev=rev)


def verify_range_serving(root: Path) -> None:
    """In-process FastAPI TestClient (no socket, no server left running) hitting the real
    media route with a Range header, against whatever audio proxy is currently on disk."""
    sys.path.insert(0, str(REPO_ROOT / "packages" / "post_api"))
    from fastapi.testclient import TestClient  # local import: only needed for this step

    from post_api.app import create_app

    registry_path = PROJECT_ROOT / "_verify_registry.json"
    registry_path.unlink(missing_ok=True)
    app = create_app(registry_path)
    with TestClient(app) as client:
        reg = client.post("/api/projects", json={"root": str(root), "name": "acme-demo"})
        reg.raise_for_status()
        pid = reg.json()["id"]
        shoot, _rev = _find_shoot(root)  # type: ignore[misc]
        for source in shoot.sources:
            if not source.audio_proxy_path:
                continue
            resp = client.get(
                f"/api/projects/{pid}/media/{source.id}/audio", headers={"Range": "bytes=0-1023"},
            )
            ok = resp.status_code == 206 and "Content-Range" in resp.headers
            log(f"range check {source.path}: status={resp.status_code} "
                f"content-range={resp.headers.get('content-range')} -> {'OK' if ok else 'FAIL'}")
    registry_path.unlink(missing_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="not used to touch the drive; reserved for future re-imports")
    ap.add_argument("--verify-range", action="store_true", help="just verify the API serves the audio proxy with Range")
    args = ap.parse_args()

    _check_drive_readable()

    if args.verify_range:
        if not (store_root(PROJECT_ROOT) / "project.json").is_file():
            sys.exit(f"{PROJECT_ROOT} has no project yet -- run the base import first")
        verify_range_serving(PROJECT_ROOT)
        return

    probes = probe_all(args.dry_run)

    if args.dry_run:
        log("[dry-run] plan:")
        log(f"  project at {PROJECT_ROOT}")
        for g in GROUPS:
            log(f"  group {g['name']}: sources={list(g['sources'])} angle={g['angle']}")
        shoot = build_or_load_shoot(PROJECT_ROOT, probes, dry_run=True)
        # dry-run transcripts/cut need real Source ids to build passages against; since
        # nothing was written, fabricate an in-memory shoot with the same shape so the rest
        # of the plan can still be printed without touching disk.
        log("  (transcripts + cut skipped in dry-run beyond word counts below)")
        for g in GROUPS:
            words = importer.import_words(WORDS[g["words"]].read_text(encoding="utf-8"), "json")
            log(f"    {g['name']}: {len(words)} words")
        log("dry-run OK -- nothing written")
        return

    if not (store_root(PROJECT_ROOT) / "project.json").is_file():
        store_module.init_project(PROJECT_ROOT)
        project = Project(name="Acme 2026-09-09", root=str(PROJECT_ROOT))
        store_module.write(PROJECT_ROOT, "project", project, expected_rev=0)
        log(f"initialised project {project.id} at {PROJECT_ROOT}")
    else:
        log(f"project already initialised at {PROJECT_ROOT}")

    shoot = build_or_load_shoot(PROJECT_ROOT, probes, dry_run=False)
    transcripts = import_transcripts(PROJECT_ROOT, shoot, dry_run=False)
    shoot, _rev = _find_shoot(PROJECT_ROOT)  # reload: import_transcripts may have updated it
    cut = build_or_load_cut(PROJECT_ROOT, shoot, transcripts, probes, dry_run=False)
    shoot, _rev = _find_shoot(PROJECT_ROOT)  # reload: build_or_load_cut doesn't touch it, but be safe
    do_audio_proxies(PROJECT_ROOT, shoot)

    log("\nsummary:")
    log(f"  sources: {len(shoot.sources)}")
    log(f"  sync groups: {len(shoot.sync_groups)}")
    log(f"  words: {sum(len(t.words) for t in transcripts.values())}")
    log(f"  passages: {len(cut.passages)}")
    log(f"  cut: {cut.id}")


if __name__ == "__main__":
    main()
