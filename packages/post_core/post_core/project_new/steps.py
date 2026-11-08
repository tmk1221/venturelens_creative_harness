"""T34: the idempotent building blocks `post project new` (and the API's ingest job) runs.
Each one reads what is already on disk first and only does the work that is missing, so a
re-run after a crash or a failed step skips everything that finished.

Same store calls the separate `post init` / `source add` / `ingest audio|peaks` /
`import-transcript` / `cut new` commands make; this module just strings them together.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from ..edit import ops as ops_mod
from ..ingest import audio_proxy as audio_proxy_mod, peaks as peaks_mod
from ..ingest.audio_proxy import ProgressFn
from ..ingest.transcribe import importer
from ..ingest.transcribe.link import add_transcript
from ..library import SOURCE_FOLDER
from ..model.common import Rational
from ..model.cut import Cut
from ..model.project import Project
from ..model.shoot import Shoot, Source, SyncGroup
from ..model.transcript import Transcript
from ..store import store as store_module
from ..store.paths import store_root

DEFAULT_SHOOT_NAME = "default"
DEFAULT_ASPECT = Rational(num=16, den=9)


class NoTranscript(ValueError):
    """Opening the editor needs a transcript; there is none yet."""


def ensure_project(root: Path, name: str, company: Optional[str] = None) -> tuple[Project, bool]:
    """`(project, created)`. An existing project keeps its own name (T39: and gains its
    company if it had none)."""
    store_module.init_project(root)
    project, rev = store_module.try_read(root, "project")
    if project is not None:
        if company and not project.company:
            project = project.model_copy(update={"company": company})
            store_module.write(root, "project", project, expected_rev=rev)
        return project, False
    project = Project(name=name or root.name, root=str(root), company=company)
    store_module.write(root, "project", project, expected_rev=0)
    return project, True


def copy_source(root: Path, src: Path) -> tuple[Path, bool]:
    """T39 `--copy`: `(path in Video/source, copied)`. A source already inside the project is
    used where it is; an existing copy of the same size is reused. Copies, never moves:
    temp file then rename, so a half-copied file never looks finished."""
    if root in src.parents:
        return src, False
    dest_dir = root / SOURCE_FOLDER
    dest = dest_dir / src.name
    if dest.is_file() and dest.stat().st_size == src.stat().st_size:
        return dest, False
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest_dir / f".{src.name}.part"
    shutil.copyfile(src, tmp)
    os.replace(tmp, dest)
    return dest, True


def _ids(root: Path, subdir: str) -> list[str]:
    d = store_root(root) / subdir
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.json") if not p.name.endswith(".undo.json"))


def find_or_create_shoot(root: Path) -> Shoot:
    for shoot_id in _ids(root, "shoots"):
        shoot, _rev = store_module.read(root, "shoot", shoot_id)
        if shoot.name == DEFAULT_SHOOT_NAME:
            return shoot
    shoot = Shoot(name=DEFAULT_SHOOT_NAME)
    store_module.write(root, "shoot", shoot, expected_rev=0)
    return shoot


def find_source(shoot: Shoot, path: str, fingerprint: str) -> Optional[Source]:
    return next((s for s in shoot.sources if s.path == path and s.content_fingerprint == fingerprint), None)


def group_of(shoot: Shoot, source_id: str) -> SyncGroup:
    group = next((g for g in shoot.sync_groups if source_id in g.source_ids), None)
    if group is None:
        raise ValueError(f"source {source_id!r} is in no sync group of shoot {shoot.id!r}")
    return group


def add_source(root: Path, probe: dict) -> tuple[Shoot, Source, bool]:
    """Add one recording (read-only, fingerprinted) in its own sync group, unless the same
    file (path + fingerprint) is already in the shoot. `(shoot, source, added)`."""
    shoot = find_or_create_shoot(root)
    existing = find_source(shoot, probe["path"], probe["content_fingerprint"])
    if existing is not None:
        return shoot, existing, False
    source = Source(
        path=probe["path"], fps=probe["fps"], start_timecode=probe["start_timecode"],
        role="a_roll" if probe.get("width") else "audio", content_fingerprint=probe["content_fingerprint"],
    )
    group = SyncGroup(source_ids=[source.id], offsets={source.id: 0.0})
    shoot, revision = store_module.read(root, "shoot", shoot.id)
    updated = shoot.model_copy(update={"sources": [*shoot.sources, source], "sync_groups": [*shoot.sync_groups, group]})
    store_module.write(root, "shoot", updated, expected_rev=revision)
    return updated, source, True


def update_source(root: Path, shoot_id: str, source_id: str, **fields) -> Source:
    """Re-read the shoot at its latest revision and patch one source's fields."""
    shoot, revision = store_module.read(root, "shoot", shoot_id)
    sources = [s.model_copy(update=fields) if s.id == source_id else s for s in shoot.sources]
    store_module.write(root, "shoot", shoot.model_copy(update={"sources": sources}), expected_rev=revision)
    return next(s for s in sources if s.id == source_id)


def ensure_audio_proxy(
    root: Path, shoot_id: str, source: Source, duration: float = 0.0, on_progress: Optional[ProgressFn] = None,
) -> tuple[str, bool]:
    """`(audio_proxy_path, built)`: the editor's AAC `.m4a`, inside the project."""
    if source.audio_proxy_path and audio_proxy_mod.is_valid_audio_proxy(source.audio_proxy_path):
        return source.audio_proxy_path, False
    out = audio_proxy_mod.build_audio_proxy(
        source.path, store_root(root) / "proxies", source.content_fingerprint,
        duration=duration, on_progress=on_progress,
    )
    update_source(root, shoot_id, source.id, audio_proxy_path=str(out))
    return str(out), True


def ensure_peaks(root: Path, shoot_id: str, source: Source, rate: int = 100) -> tuple[str, bool]:
    """`(peaks_path, built)`, decoded from the (small, local) audio proxy when there is one
    rather than re-reading the camera file."""
    if source.peaks_path and Path(source.peaks_path).is_file() and Path(source.peaks_path).stat().st_size > 0:
        return source.peaks_path, False
    out_path = store_root(root) / "peaks" / f"{source.content_fingerprint}.peaks"
    audio = source.audio_proxy_path if source.audio_proxy_path and Path(source.audio_proxy_path).is_file() else source.path
    out = peaks_mod.build_peaks(audio, out_path, samples_per_sec=rate)
    update_source(root, shoot_id, source.id, peaks_path=str(out))
    return str(out), True


def transcripts_by_group(root: Path) -> dict[str, Transcript]:
    """The first transcript (by id) for each sync group."""
    out: dict[str, Transcript] = {}
    for tid in _ids(root, "transcripts"):
        transcript, _rev = store_module.read(root, "transcript", tid)
        out.setdefault(transcript.sync_group_id, transcript)
    return out


def import_transcript(root: Path, shoot_id: str, sync_group_id: str, path: str | Path,
                      fmt: Optional[str] = None) -> Transcript:
    """Read a finished transcript file (JSON/SRT/VTT) and link it to the sync group (T35: keeping
    any speaker names the group's previous transcript had)."""
    text = Path(path).read_text(encoding="utf-8")
    fmt = fmt or importer.guess_format(str(path))
    words = importer.import_words(text, fmt)
    return add_transcript(root, shoot_id, importer.words_to_transcript(
        words, sync_group_id=sync_group_id, provider=f"import:{fmt}", fingerprint=f"import:{Path(path).name}",
    ))


def ensure_first_cut(root: Path) -> tuple[str, bool]:
    """`(cut_id, created)`. The project's first cut (the one the editor opens), or a new one:
    every transcribed sync group in source order, each played through its own camera (or
    its recording, for an audio-only file)."""
    existing = _ids(root, "cuts")
    if existing:
        return existing[0], False
    transcripts = transcripts_by_group(root)
    passages, fps = [], None
    for shoot_id in _ids(root, "shoots"):
        shoot, _rev = store_module.read(root, "shoot", shoot_id)
        for group in shoot.sync_groups:
            transcript = transcripts.get(group.id)
            if transcript is None or not transcript.words:
                continue
            members = [s for s in shoot.sources if s.id in group.source_ids]
            angle = next((s for s in members if s.role == "a_roll"), members[0])
            fps = fps or angle.fps
            passages += ops_mod.cut_from_transcript(transcript, angle.id, DEFAULT_ASPECT).passages
    if not passages:
        raise NoTranscript("There is no transcript yet. Import one (or transcribe) before opening the editor.")
    cut = Cut(aspect=DEFAULT_ASPECT, passages=passages, **({"fps": fps} if fps else {}))
    store_module.write(root, "cut", cut, expected_rev=0)
    return cut.id, True


__all__ = [
    "DEFAULT_SHOOT_NAME", "NoTranscript", "add_source", "ensure_audio_proxy", "ensure_first_cut", "ensure_peaks",
    "ensure_project", "find_or_create_shoot", "find_source", "group_of", "import_transcript",
    "transcripts_by_group", "update_source",
]
