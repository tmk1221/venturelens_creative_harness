"""A-roll regen consent record (T30b stub, HTTP surface added T30e): whether *this project*
has a recorded consent to regenerate the presenter's voice/likeness at all. Deliberately tiny
and project-wide (not per-span) -- T15 owns the real A-roll regen providers and whatever
richer consent shape they need; this only has to be enough for `aroll.regenerate`'s
`consent.gate` node to have something concrete to gate on (spec: "needs_human until the
project has a consent record") and for `GET/POST .../consent` (T30e spec: "{presenter,
release_path, date}") to read/write a release record a human can point at."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict

from ..store.atomic import locked, read_envelope, write_envelope
from ..store.paths import store_root


class ConsentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    presenter: str
    release_path: str
    date: str


def _path(project_root: str | Path) -> Path:
    return store_root(project_root) / "consent.json"


def read_consent(project_root: str | Path) -> Optional[ConsentRecord]:
    _revision, data = read_envelope(_path(project_root))
    if data is None:
        return None
    return ConsentRecord.model_validate(data)


def has_consent(project_root: str | Path) -> bool:
    return read_consent(project_root) is not None


def record_consent(project_root: str | Path, presenter: str, release_path: str, date: str) -> ConsentRecord:
    record = ConsentRecord(presenter=presenter, release_path=release_path, date=date)
    path = _path(project_root)
    with locked(path):
        revision, _data = read_envelope(path)
        write_envelope(path, revision + 1, record.model_dump(mode="json"))
    return record


__all__ = ["ConsentRecord", "read_consent", "has_consent", "record_consent"]
