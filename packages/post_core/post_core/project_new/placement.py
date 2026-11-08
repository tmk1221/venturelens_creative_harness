"""T34/T39: where a project may live. The footage is read-only input; the project folder is
where Post writes (`.post3/`, proxies, peaks, `Exports/`, `AI Generations/`), so it must never
be a source's own folder, sit inside one, or sit inside a `Video/source` folder (the library's
read-only footage folder). T39 dropped T34's "never under /Volumes" rule: real projects now
live in the media library on the external drive, Company -> Project. Pure path checks:
nothing here touches the disk beyond resolving symlinks, so a refusal always happens before
anything is written.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


class RootPlacementError(ValueError):
    """The project folder is somewhere Post must not write. The message says why in plain
    words and what to pick instead."""


def normalise(path: str | Path) -> Path:
    """`~` expanded and symlinks resolved, so `~/footage -> /Volumes/T7/footage` is caught."""
    return Path(path).expanduser().resolve()


def _source_folder_of(path: Path) -> Path | None:
    """The `Video/source` folder `path` is in or under, if any."""
    for p in (path, *path.parents):
        if p.name == "source" and p.parent.name == "Video":
            return p
    return None


def check_root_placement(root: str | Path, sources: Iterable[str | Path] = ()) -> Path:
    """Return the normalised project root, or raise `RootPlacementError`."""
    r = normalise(root)
    footage = _source_folder_of(r)
    if footage is not None:
        raise RootPlacementError(
            f"The project folder {r} is inside the footage folder {footage}. Post never writes "
            f"there; use the project folder above it ({footage.parent.parent})."
        )
    for source in sources:
        folder = normalise(source).parent
        if r == folder:
            raise RootPlacementError(
                f"The project folder {r} is the folder {Path(source).name} is in. Pick a separate "
                "folder, so Post never writes next to the footage."
            )
        if folder in r.parents:
            raise RootPlacementError(
                f"The project folder {r} is inside the footage folder {folder}. Pick a folder "
                "outside it, so Post never writes next to the footage."
            )
    return r


__all__ = ["RootPlacementError", "check_root_placement", "normalise"]
