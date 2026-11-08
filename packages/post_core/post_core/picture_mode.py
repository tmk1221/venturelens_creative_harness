"""T42: the project's picture mode -- `presenter` (someone on camera; B-roll cuts away and comes
back) or `audio_only` (a voice only; every second of the cut needs a picture). Read by Suggest
visuals (`edit.suggest`), set by `PATCH /api/projects/{pid}` and `post project set
--picture-mode`."""
from __future__ import annotations

from pathlib import Path

from .model.project import PICTURE_MODES
from .store import store as store_module


class UnknownPictureMode(ValueError):
    pass


def project_picture_mode(project_root: str | Path) -> str:
    """The project's mode; `presenter` when there is no project record yet."""
    project, _rev = store_module.try_read(project_root, "project")
    return project.picture_mode if project is not None else "presenter"


def set_picture_mode(project_root: str | Path, mode: str) -> dict:
    """Write `mode` to `.post3/project.json` (nothing else changes; pending suggestions stay
    until the next Suggest run over them). Refuses an unknown mode before touching anything."""
    if mode not in PICTURE_MODES:
        raise UnknownPictureMode(f"unknown picture mode {mode!r}; one of: {', '.join(PICTURE_MODES)}")
    project, revision = store_module.read(project_root, "project")
    previous = project.picture_mode
    if previous != mode:
        store_module.write(project_root, "project", project.model_copy(update={"picture_mode": mode}),
                           expected_rev=revision)
    return {"picture_mode": mode, "previous": previous}


__all__ = ["UnknownPictureMode", "project_picture_mode", "set_picture_mode"]
