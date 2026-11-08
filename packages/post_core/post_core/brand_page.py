"""T41: the project's brand kit as a live style guide -- the kit's design-system page
(`brandkit.design_system.render_html` + `tokens_css`, what `brandkit render-design-system`
writes), rendered in memory from the kit's own files and re-rendered whenever any of them
changes (an mtime/size signature, checked on every request).

Read-only by design: a company kit lives in the media library (`<Company>/brand/`), often on
an external drive, and the app never writes into a kit. Nothing here touches disk except to
read; a stale `index.html` a person rendered with the CLI is ignored in favour of the source.
"""
from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path

from brandkit import design_system

from . import brand as brand_mod

# Files the CLI renders into the folder: never part of the source signature, never served raw.
RENDERED = {"index.html", "tokens.css"}


class NoDesignSystem(ValueError):
    """The project's kit has no `design-system/` folder (an old brand.yaml-only kit)."""


class OutsideKit(ValueError):
    """A requested path escapes the kit's `design-system/` folder."""


@dataclass(frozen=True)
class BrandPage:
    kit_id: str
    folder: Path
    signature: str
    html: str
    css: str
    approved_looks: tuple[str, ...]


_cache: dict[Path, BrandPage] = {}
_lock = threading.Lock()


def design_folder(project_root: str | Path) -> tuple[str, Path]:
    """`(kit id, <kit>/design-system)` for the project's kit. Raises `UnknownKit`, `NoDesignSystem`."""
    kit_id = brand_mod.project_kit_id(project_root)
    folder = brand_mod.kit_dir(kit_id, project_root) / "design-system"
    if not (folder / "design-system.json").is_file():
        raise NoDesignSystem(f"brand kit {kit_id!r} has no design-system/ folder to show")
    return kit_id, folder.resolve()


def signature(folder: Path) -> str:
    """Changes whenever any source file under the folder is added, removed or rewritten."""
    h = hashlib.sha1()
    for p in sorted(folder.rglob("*")):
        if not p.is_file() or p.name.startswith(".") or (p.parent == folder and p.name in RENDERED):
            continue
        st = p.stat()
        h.update(f"{p.relative_to(folder)}\0{st.st_mtime_ns}\0{st.st_size}\n".encode())
    return h.hexdigest()[:16]


def page(project_root: str | Path) -> BrandPage:
    """The rendered page, re-rendered only when the kit's signature has moved on."""
    kit_id, folder = design_folder(project_root)
    sig = signature(folder)
    with _lock:
        cached = _cache.get(folder)
        if cached is not None and cached.signature == sig and cached.kit_id == kit_id:
            return cached
    html = design_system.render_html(folder)
    css = design_system.tokens_css(design_system._load(folder)["tokens"])
    looks = tuple(sorted(p.name for p in (folder / "assets").glob("approved-look-*.png")))
    fresh = BrandPage(kit_id=kit_id, folder=folder, signature=sig, html=html, css=css, approved_looks=looks)
    with _lock:
        _cache[folder] = fresh
    return fresh


def asset_path(project_root: str | Path, rel: str) -> Path:
    """A file inside the kit's `design-system/` folder, by relative path. Raises `OutsideKit`
    for anything that resolves outside it (`..`, absolute paths, symlinks out) and
    `FileNotFoundError` when there is no such file."""
    _kit_id, folder = design_folder(project_root)
    if not rel or rel.startswith(("/", "\\")) or "\0" in rel:
        raise OutsideKit(rel)
    target = (folder / rel).resolve()
    if not target.is_relative_to(folder) or target == folder:
        raise OutsideKit(rel)
    if any(part.startswith(".") for part in target.relative_to(folder).parts):
        raise OutsideKit(rel)
    if not target.is_file():
        raise FileNotFoundError(rel)
    return target


__all__ = ["BrandPage", "NoDesignSystem", "OutsideKit", "asset_path", "design_folder", "page", "signature"]
