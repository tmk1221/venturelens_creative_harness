"""T34: `new_project` -- one call from a local recording to a project the editor can open:
check the folder, create the store, set the brand kit, add each recording (read-only,
fingerprinted, one sync group per file), build its audio proxy + waveform peaks, import any
transcript given, and make the first cut once there is a transcript. T39: with `company`, the
project is `<library>/<company>/<name>/` with the house subfolders, its kit defaults to the
company's own (`<company>/brand/`), and `copy=True` copies outside recordings into
`Video/source/` (otherwise they are referenced where they are, read-only).

Every step reports through `emit(event)` with the worker contract's own vocabulary
(`workers.contract`): `step` events (`status`: pending -> running -> done | skipped | failed)
and `progress` events (`i`/`n` percent) for the long ffmpeg step. The CLI prints one JSON
line per finished step; the API records the same events as an in-process job so the web
page can follow them over SSE. A failure stops the run with `NewProjectError`, whose message
is a plain sentence a person can act on; re-running skips every finished step.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Sequence

from .. import brand as brand_mod
from .. import library
from ..ingest.audio_proxy import AudioProxyError
from ..ingest.peaks import PeaksError
from ..ingest.probe import ProbeError, probe_source
from . import steps
from .placement import RootPlacementError, check_root_placement, normalise

Emit = Callable[[dict], None]


class NewProjectError(RuntimeError):
    """A step failed. `step` is its id; the message is meant for a person, not a log."""

    def __init__(self, step: str, message: str) -> None:
        self.step = step
        super().__init__(message)


@dataclass
class _Run:
    emit: Emit
    plan: list[tuple[str, str]]  # (step id, label)
    results: list[dict] = field(default_factory=list)

    def announce(self) -> None:
        for step_id, label in self.plan:
            self.emit({"kind": "step", "step": step_id, "label": label, "status": "pending"})

    def do(self, step_id: str, fn: Callable[[], tuple[bool, dict]]) -> dict:
        label = dict(self.plan)[step_id]
        self.emit({"kind": "step", "step": step_id, "label": label, "status": "running"})
        try:
            did_work, detail = fn()
        except NewProjectError as exc:
            self._fail(step_id, label, str(exc))
        except Exception as exc:  # noqa: BLE001 - every failure becomes a plain sentence
            self._fail(step_id, label, _plain(label, exc))
        event = {"kind": "step", "step": step_id, "label": label,
                 "status": "done" if did_work else "skipped", **detail}
        self.emit(event)
        self.results.append(event)
        return detail

    def progress(self, step_id: str) -> Callable[[float], None]:
        label, last = dict(self.plan)[step_id], [-1]

        def report(fraction: float) -> None:
            pct = int(max(0.0, min(1.0, fraction)) * 100)
            if pct != last[0]:
                last[0] = pct
                self.emit({"kind": "progress", "step": step_id, "label": label, "i": pct, "n": 100})
        return report

    def _fail(self, step_id: str, label: str, message: str) -> None:
        self.emit({"kind": "step", "step": step_id, "label": label, "status": "failed", "error": message})
        raise NewProjectError(step_id, message)


def _plain(label: str, exc: Exception) -> str:
    if isinstance(exc, (RootPlacementError, brand_mod.UnknownKit, steps.NoTranscript, library.LibraryError)):
        return str(exc)
    if isinstance(exc, (ProbeError, AudioProxyError, PeaksError)):
        detail = str(exc).strip().splitlines()[-1] if str(exc).strip() else type(exc).__name__
        return f"{label}: ffmpeg could not read the file ({detail})."
    return f"{label} failed: {exc}"


def _check(root: Path, sources: Sequence[Path], transcripts: Sequence[Path], kit: Optional[str],
           company: Optional[str] = None) -> dict:
    if not sources:
        raise NewProjectError("check", "Add at least one recording.")
    check_root_placement(root, sources)
    for src in sources:
        if not src.is_file():
            raise NewProjectError("check", f"Can't find the recording {src}.")
    if len(transcripts) > len(sources):
        raise NewProjectError("check", "There are more transcripts than recordings; give one per recording, in order.")
    for t in transcripts:
        if not t.is_file():
            raise NewProjectError("check", f"Can't find the transcript {t}.")
    if kit is not None:
        brand_mod.kit_dir(kit, root, company)  # UnknownKit lists the ones there are
    return {"root": str(root)}


def resolve_root(root: Optional[str | Path], name: Optional[str], company: Optional[str] = None,
                 library_dir: Optional[Path] = None) -> Path:
    """The project folder: `root` as given, or (T39, with `company` and no root)
    `<library>/<company>/<name>/`. Raises `LibraryError` for a name that is no folder name."""
    if company is not None:
        library.check_name(company, "Company")
        if root is None:
            return normalise(library.project_dir(company, name or "", library_dir))
    if root is None:
        raise NewProjectError("check", "Give a project folder, or a company and project name.")
    return normalise(root)


def validate_request(root: Optional[str | Path], sources: Sequence[str | Path], transcripts: Sequence[str | Path] = (),
                     kit: Optional[str] = None, *, name: Optional[str] = None, company: Optional[str] = None) -> Path:
    """The `check` step on its own, for a caller (the API) that must refuse before starting
    a job. Raises `NewProjectError` / `RootPlacementError` / `UnknownKit` / `LibraryError`."""
    r = resolve_root(root, name, company)
    _check(r, [normalise(s) for s in sources], [normalise(t) for t in transcripts], kit, company)
    return r


def plan_steps(sources: Sequence[Path], transcripts: Sequence[Path], kit: Optional[str], *,
               company: Optional[str] = None, copy: bool = False) -> list[tuple[str, str]]:
    plan = [("check", "Check the project folder"), ("init", "Create the project")]
    if company is not None:
        plan.append(("layout", f"Make the {company} project folders"))
    if kit is not None:
        plan.append(("kit", f"Use the {kit} brand kit"))
    for i, src in enumerate(sources):
        if copy:
            plan.append((f"copy:{i}", f"Copy {src.name} into Video/source"))
        plan += [(f"source:{i}", f"Add {src.name}"), (f"audio:{i}", f"Audio for {src.name}"),
                 (f"peaks:{i}", f"Waveform for {src.name}")]
    for i, t in enumerate(transcripts):
        plan.append((f"transcript:{i}", f"Import transcript {t.name}"))
    if transcripts:
        plan.append(("cut", "Create the first cut"))
    return plan


def new_project(
    root: Optional[str | Path], name: Optional[str] = None, sources: Sequence[str | Path] = (), *,
    transcripts: Sequence[str | Path] = (), kit: Optional[str] = None, emit: Optional[Emit] = None,
    company: Optional[str] = None, copy: bool = False, library_dir: Optional[Path] = None,
) -> dict:
    r = resolve_root(root, name, company, library_dir)
    srcs = [normalise(s) for s in sources]
    trs = [normalise(t) for t in transcripts]
    if kit is None and company is not None and brand_mod.default_kit_id(r, company) == company:
        kit = company  # the company's own kit, `<company>/brand/`
    run = _Run(emit or (lambda _event: None), plan_steps(srcs, trs, kit, company=company, copy=copy))
    run.announce()

    run.do("check", lambda: (True, _check(r, srcs, trs, kit, company)))

    def _init() -> tuple[bool, dict]:
        project, created = steps.ensure_project(r, name or r.name, company)
        return created, {"project_id": project.id, "name": project.name}
    project = run.do("init", _init)

    if company is not None:
        def _layout() -> tuple[bool, dict]:
            made = library.ensure_project_layout(r)
            return bool(made), {"folders": list(library.HOUSE_FOLDERS)}
        run.do("layout", _layout)

    if copy:
        for i, src in enumerate(list(srcs)):
            def _copy(i: int = i, src: Path = src) -> tuple[bool, dict]:
                dest, copied = steps.copy_source(r, src)
                srcs[i] = dest
                return copied, {"path": str(dest)}
            run.do(f"copy:{i}", _copy)

    if kit is not None:
        def _kit() -> tuple[bool, dict]:
            if brand_mod.project_kit_id(r) == kit:
                return False, {"brand_kit": kit}
            brand_mod.set_project_kit(r, kit)
            return True, {"brand_kit": kit}
        run.do("kit", _kit)

    added: list[dict] = []
    for i, src in enumerate(srcs):
        added.append(_ingest_source(run, r, i, src))

    transcript_ids: list[str] = []
    for i, t in enumerate(trs):
        transcript_ids.append(_import(run, r, i, t, added[i]))

    cut_id = None
    if trs:
        def _cut() -> tuple[bool, dict]:
            cid, created = steps.ensure_first_cut(r)
            return created, {"cut_id": cid}
        cut_id = run.do("cut", _cut)["cut_id"]

    return {
        "root": str(r), "project_id": project["project_id"], "name": project["name"], "company": company,
        "brand_kit": brand_mod.project_kit_id(r), "sources": added, "transcript_ids": transcript_ids,
        "cut_id": cut_id, "steps": [{"step": e["step"], "status": e["status"]} for e in run.results],
    }


def _ingest_source(run: _Run, root: Path, i: int, src: Path) -> dict:
    state: dict = {}

    def _add() -> tuple[bool, dict]:
        probe = probe_source(src)
        if not probe["audio_streams"]:
            raise NewProjectError(f"source:{i}", f"{src.name} has no audio track. Post edits by sound, so it needs one.")
        shoot, source, added = steps.add_source(root, probe)
        state.update(shoot_id=shoot.id, source=source, duration=probe["duration"])
        return added, {"source_id": source.id, "shoot_id": shoot.id,
                       "sync_group_id": steps.group_of(shoot, source.id).id, "duration": probe["duration"]}
    detail = run.do(f"source:{i}", _add)

    def _audio() -> tuple[bool, dict]:
        path, built = steps.ensure_audio_proxy(root, state["shoot_id"], state["source"], state["duration"],
                                               run.progress(f"audio:{i}"))
        state["source"] = state["source"].model_copy(update={"audio_proxy_path": path})
        return built, {"audio_proxy_path": path}
    audio = run.do(f"audio:{i}", _audio)

    def _peaks() -> tuple[bool, dict]:
        path, built = steps.ensure_peaks(root, state["shoot_id"], state["source"])
        return built, {"peaks_path": path}
    peaks = run.do(f"peaks:{i}", _peaks)
    return {"path": str(src), **detail, **audio, **peaks}


def _import(run: _Run, root: Path, i: int, path: Path, source: dict) -> str:
    def _do() -> tuple[bool, dict]:
        existing = steps.transcripts_by_group(root).get(source["sync_group_id"])
        if existing is not None:
            return False, {"transcript_id": existing.id, "words": len(existing.words)}
        try:
            transcript = steps.import_transcript(root, source["shoot_id"], source["sync_group_id"], path)
        except (ValueError, KeyError) as exc:
            raise NewProjectError(f"transcript:{i}", f"Couldn't read the transcript {path.name}: {exc}") from exc
        return True, {"transcript_id": transcript.id, "words": len(transcript.words)}
    return run.do(f"transcript:{i}", _do)["transcript_id"]


__all__ = ["Emit", "NewProjectError", "new_project", "plan_steps", "resolve_root", "validate_request"]
