"""T39: the media library -- where real projects live, organised Company -> Project.

    <library>/<Company>/brand/                 that company's brand kit (design-system layout)
    <library>/<Company>/<Project>/             one folder per DaVinci Resolve project, same name
        Video/source/  Audio/  Transcript/  BRolls/  AI Generations/  Animations/
        Renders/  Exports/  .post3/

The library is `$POST3_LIBRARY`, else `library = <path>` in the rc file (`$POST3_RC`, else
`~/.post3rc`), else `/Volumes/MediaDrive`. A project made with `--company` records the company
on `Project.company`; that is what makes it a library project, so its exports land in
`Exports/`, generated media is copied to `AI Generations/`, and its kit lookup tries
`<Company>/brand/` first. Projects without a company (temp and demo roots, tests) keep the
T34 layout (`exports/`, kits from the repo only). Nothing here deletes anything.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

LIBRARY_ENV = "POST3_LIBRARY"
RC_ENV = "POST3_RC"
DEFAULT_LIBRARY = Path("/Volumes/MediaDrive")

SOURCE_FOLDER = "Video/source"
GENERATIONS_FOLDER = "AI Generations"
EXPORTS_FOLDER = "Exports"
BRAND_FOLDER = "brand"
HOUSE_FOLDERS = (SOURCE_FOLDER, "Audio", "Transcript", "BRolls", GENERATIONS_FOLDER, "Animations",
                 "Renders", EXPORTS_FOLDER)
# Folders under the library that are not companies (Resolve's own, caches).
_NOT_COMPANIES = {"CacheClip", "Resolve Media", "Resolve Project Library"}


class LibraryError(ValueError):
    """A company or project name Post can't use as a folder name; the message says why."""


def _rc_path() -> Path:
    return Path(os.environ.get(RC_ENV) or Path.home() / ".post3rc").expanduser()


def _rc_library() -> Optional[str]:
    try:
        lines = _rc_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        key, sep, value = line.split("#", 1)[0].partition("=")
        if sep and key.strip() == "library" and value.strip():
            return value.strip()
    return None


def library_root() -> Path:
    raw = os.environ.get(LIBRARY_ENV) or _rc_library()
    return Path(raw).expanduser() if raw else DEFAULT_LIBRARY


def check_name(name: str, what: str) -> str:
    """A company/project name is one folder name: no slashes, no leading dot, not blank."""
    clean = (name or "").strip()
    if not clean or clean.startswith(".") or "/" in clean or "\\" in clean or clean != Path(clean).name:
        raise LibraryError(f"{what} name {name!r} can't be a folder name: use plain words, no slashes.")
    return clean


def company_dir(company: str, library: Optional[Path] = None) -> Path:
    return (library or library_root()) / check_name(company, "Company")


def project_dir(company: str, project: str, library: Optional[Path] = None) -> Path:
    return company_dir(company, library) / check_name(project, "Project")


def ensure_project_layout(root: Path) -> list[str]:
    """Create the house subfolders that are missing; returns the ones it made."""
    made = []
    for sub in HOUSE_FOLDERS:
        d = root / sub
        if not d.is_dir():
            d.mkdir(parents=True, exist_ok=True)
            made.append(sub)
    return made


def _is_project_folder(path: Path) -> bool:
    return (path / ".post3").is_dir() or (path / "Video").is_dir()


def list_companies(library: Optional[Path] = None) -> list[dict]:
    """`[{name, has_brand, projects}]` for a company picker. Read-only."""
    lib = library or library_root()
    if not lib.is_dir():
        return []
    out = []
    for d in sorted(lib.iterdir(), key=lambda p: p.name.lower()):
        if not d.is_dir() or d.name[0] in "._" or d.name in _NOT_COMPANIES:
            continue
        projects = sorted(p.name for p in d.iterdir()
                          if p.is_dir() and p.name[0] not in "._" and p.name != BRAND_FOLDER and _is_project_folder(p))
        out.append({"name": d.name, "has_brand": (d / BRAND_FOLDER).is_dir(), "projects": projects})
    return out


def project_company(project_root: str | Path) -> Optional[str]:
    from .store import store as store_module
    project, _rev = store_module.try_read(project_root, "project")
    return getattr(project, "company", None) if project is not None else None


def company_brand_dir(project_root: str | Path, company: Optional[str] = None) -> Optional[Path]:
    """`<Company>/brand/` for a library project (the project folder's parent), else None.
    `company` stands in for `Project.company` before the project exists."""
    if not (company or project_company(project_root)):
        return None
    return Path(project_root).resolve().parent / BRAND_FOLDER


def exports_dir(project_root: str | Path) -> Path:
    root = Path(project_root).resolve()
    return root / (EXPORTS_FOLDER if project_company(root) else "exports")


def generations_dir(project_root: str | Path) -> Optional[Path]:
    """Where generated media is copied for a library project; None for other projects."""
    root = Path(project_root).resolve()
    return root / GENERATIONS_FOLDER if project_company(root) else None


# Node types whose output is generated media an editor wants in Resolve (T39).
GENERATED_MEDIA_TYPES = frozenset({"still.generate", "endframe.generate", "video.generate"})


def publish_generated(project_root: str | Path, node_type_id: str, node_id: str, input_hash: str,
                      files: list[Path]) -> list[str]:
    """Copy a generation node's media into `AI Generations/` of a library project, named
    `<node id>_<hash[:8]>_<file>` so a re-generation never overwrites an earlier take. The
    content-addressed artifact stays the source of truth. Hard link when the drive allows,
    else copy (temp file + rename). Returns the paths written; [] when not applicable."""
    import shutil

    target = generations_dir(project_root) if node_type_id in GENERATED_MEDIA_TYPES else None
    if target is None:
        return []
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for src in files:
        dest = target / f"{node_id}_{input_hash[:8]}_{src.name}"
        if not dest.exists():
            tmp = target / f".{dest.name}.part"
            try:
                os.link(src, tmp)
            except OSError:
                shutil.copyfile(src, tmp)
            os.replace(tmp, dest)
        written.append(str(dest))
    return written


__all__ = [
    "GENERATED_MEDIA_TYPES", "publish_generated",
    "BRAND_FOLDER", "DEFAULT_LIBRARY", "EXPORTS_FOLDER", "GENERATIONS_FOLDER", "HOUSE_FOLDERS", "LIBRARY_ENV",
    "LibraryError", "RC_ENV", "SOURCE_FOLDER", "check_name", "company_brand_dir", "company_dir",
    "ensure_project_layout", "exports_dir", "generations_dir", "library_root", "list_companies",
    "project_company", "project_dir",
]
