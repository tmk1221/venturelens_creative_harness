"""`post init`, `post project new|show|set-kit|set`, `post source add|probe`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ... import brand as brand_mod
from ... import picture_mode as picture_mode_mod
from ...ingest.probe import probe_source
from ...library import LibraryError
from ...model.project import Project
from ...model.shoot import Shoot, Source, SyncGroup
from ...project_new import NewProjectError, RootPlacementError, check_root_placement, new_project
from ...store import store as store_module
from ...store.errors import NotFound
from ...store.paths import store_root
from ..context import resolve_project_root
from ..output import CLIError, print_json

DEFAULT_SHOOT_NAME = "default"


def init(args: argparse.Namespace) -> dict:
    root = Path(args.root).resolve()
    if not store_root(root).is_dir():  # T34/T39: never start a new store inside a footage folder
        try:
            check_root_placement(root)
        except RootPlacementError as exc:
            raise CLIError(str(exc)) from exc
    store_module.init_project(root)
    project, _rev = store_module.try_read(root, "project")
    if project is None:
        project = Project(name=args.name or root.name, root=str(root))
        store_module.write(root, "project", project, expected_rev=0)
    return {"root": str(root), "project_id": project.id, "name": project.name}


def project_new(args: argparse.Namespace) -> dict:
    """T34: `post project new <name> --root <dir> --source <file> [...]` (T39: or
    `--company <C> --project <P>`, the media library's `<C>/<P>/`) -- the whole
    `init` + `source add` + `ingest audio|peaks` (+ `import-transcript` + `cut new` when a
    `--transcript` is given) sequence in one idempotent call. Prints one JSON line per
    finished step as it goes; the last line is the usual single result object."""
    def emit(event: dict) -> None:
        if event.get("kind") == "step" and event.get("status") in ("done", "skipped"):
            print_json({k: v for k, v in event.items() if k != "kind"})
            sys.stdout.flush()

    name = args.project or args.name
    if args.project and args.name and args.project != args.name:
        raise CLIError("Give the project name once: as the argument or as --project.")
    if args.company is None and args.root is None:
        raise CLIError("Give --company (the media library) or --root (any other folder).")
    if args.company is not None and not name:
        raise CLIError("--company needs a project name (--project), which is also the Resolve project's name.")
    try:
        return new_project(args.root, name, args.sources, transcripts=args.transcripts or [],
                           kit=args.kit, emit=emit, company=args.company, copy=args.copy)
    except NewProjectError as exc:
        raise CLIError(f"{exc.step}: {exc}") from exc
    except (RootPlacementError, LibraryError) as exc:
        raise CLIError(f"check: {exc}") from exc


def project_show(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    project, revision = store_module.read(root, "project")
    return {"revision": revision, "project": project}


def project_set_kit(args: argparse.Namespace) -> dict:
    """T33: choose the project's brand kit; refuses an unknown kit, listing the ones there
    are. Branded nodes in every workflow go stale; nothing is regenerated."""
    root = resolve_project_root(args.root)
    try:
        return brand_mod.set_project_kit(root, args.kit_id)
    except ValueError as exc:  # UnknownKit, or a kit that does not load (BrandKitError)
        raise CLIError(str(exc)) from exc


def project_set(args: argparse.Namespace) -> dict:
    """T42: `post project set --picture-mode presenter|audio_only` -- writes only
    `.post3/project.json`."""
    root = resolve_project_root(args.root)
    if args.picture_mode is None:
        raise CLIError("Nothing to set: give --picture-mode presenter|audio_only.")
    try:
        return picture_mode_mod.set_picture_mode(root, args.picture_mode)
    except ValueError as exc:
        raise CLIError(str(exc)) from exc


def _iter_shoot_ids(root: Path) -> list[str]:
    d = store_root(root) / "shoots"
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def _find_or_create_default_shoot(root: Path) -> tuple[Shoot, int]:
    for shoot_id in _iter_shoot_ids(root):
        shoot, revision = store_module.read(root, "shoot", shoot_id)
        if shoot.name == DEFAULT_SHOOT_NAME:
            return shoot, revision
    shoot = Shoot(name=DEFAULT_SHOOT_NAME)
    revision = store_module.write(root, "shoot", shoot, expected_rev=0)
    return shoot, revision


def _load_shoot(root: Path, shoot_id: str) -> tuple[Shoot, int]:
    try:
        return store_module.read(root, "shoot", shoot_id)
    except NotFound as exc:
        raise CLIError(str(exc)) from exc


def source_probe(args: argparse.Namespace) -> dict:
    return probe_source(args.path)


def source_add(args: argparse.Namespace) -> dict:
    root = resolve_project_root(args.root)
    probe = probe_source(args.path)

    if args.shoot:
        shoot, revision = _load_shoot(root, args.shoot)
    else:
        shoot, revision = _find_or_create_default_shoot(root)

    source = Source(
        path=probe["path"],
        fps=probe["fps"],
        start_timecode=probe["start_timecode"],
        role=args.role,
        content_fingerprint=probe["content_fingerprint"],
    )
    sync_group = SyncGroup(source_ids=[source.id], offsets={source.id: 0.0})
    updated = shoot.model_copy(update={
        "sources": [*shoot.sources, source],
        "sync_groups": [*shoot.sync_groups, sync_group],
    })
    store_module.write(root, "shoot", updated, expected_rev=revision)

    return {
        "shoot_id": shoot.id,
        "source_id": source.id,
        "sync_group_id": sync_group.id,
        "probe": probe,
    }


__all__ = ["init", "project_new", "project_set", "project_set_kit", "project_show", "source_add", "source_probe"]
