"""lint.py — does a HyperFrames composition follow its brand kit? Can fail a build.

Two things get linted:
  - a composition directory (`lint_composition`): hexes used in its source are a subset of
    the kit's palette (brand colours + derived/explicit UI shades), font families used are
    a subset of the kit's typography, brand.css is linked, any copy of a kit logo the
    composition carries has not been altered. On-screen product/feature names that aren't
    in the kit's `core.names.official`/`products` are reported as a WARNING (never a
    failure) — T20 dropped the old forbidden-names list; brand kits are positive-only.
  - a bare string meant for an image-generation prompt (`lint_prompt`): flags hex codes, font
    names, and brand/logo words — the same purity rule `compile.find_prompt_violations`
    enforces at compile time, exposed here so callers can check arbitrary prompt text too.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .compile import compiled_ui_shades, find_prompt_violations
from .schema import BrandKit

HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}\b")
FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;}{]+)")
GENERIC_FACES = {"sans-serif", "monospace", "serif", "system-ui", "-apple-system",
                  "inherit", "cursive", "fantasy", "ui-sans-serif", "ui-monospace"}
# Heuristic for an on-screen product/feature name: two-to-four Title Case words.
TITLE_CASE_RE = re.compile(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+){1,3})\b")


def _sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _read_source(comp_dir: Path) -> str:
    idx = comp_dir / "index.html"
    if not idx.is_file():
        return ""
    text = idx.read_text(encoding="utf-8", errors="replace")
    for css in comp_dir.glob("**/*.css"):
        text += "\n" + css.read_text(encoding="utf-8", errors="replace")
    return text


def _flag(flags: list, kind: str, detail: str) -> None:
    flags.append({"kind": kind, "detail": detail})


def lint_composition(kit: BrandKit, comp_dir: str | Path) -> dict:
    comp_dir = Path(comp_dir)
    flags: list = []
    warnings: list = []
    idx = comp_dir / "index.html"
    if not idx.is_file():
        _flag(flags, "missing", f"no index.html in {comp_dir}")
        return {"comp": comp_dir.name, "kit": kit.name, "flags": flags, "warnings": warnings}

    src = _read_source(comp_dir)

    # --- hexes used ⊆ kit palette (core colours + derived/explicit UI shades) ----------
    allowed_hex = {c.hex.lower() for c in kit.core_colours.values() if c.status == "filled" and c.hex}
    allowed_hex |= {h.lower() for h in compiled_ui_shades(kit).values()}
    used_hex = {m.group(0).lower() for m in HEX_RE.finditer(src)}
    off_palette = sorted(used_hex - allowed_hex)
    if off_palette:
        _flag(flags, "palette", "hex(es) not in kit palette: " + ", ".join(off_palette))

    # --- font families used ⊆ kit typography -------------------------------------------
    allowed_faces = {t.family.lower() for t in kit.core_typography.values() if t.status == "filled" and t.family} | GENERIC_FACES
    used_faces = set()
    for m in FONT_FAMILY_RE.finditer(src):
        for part in m.group(1).split(","):
            face = part.strip().strip("'\"").lower()
            if face:
                used_faces.add(face)
    off_kit = sorted(used_faces - allowed_faces)
    if off_kit:
        _flag(flags, "font", "face(s) not in kit: " + ", ".join(off_kit))

    # --- brand.css linked ----------------------------------------------------------------
    if not re.search(r"href=[\"'][^\"']*brand\.css[\"']", src):
        _flag(flags, "adopt", "brand.css not linked")

    # --- logo file hash unchanged ----------------------------------------------------------
    for logo in kit.core_logos.values():
        if not logo.file:
            continue
        kit_svg = kit.path / logo.file
        comp_copy = comp_dir / "assets" / Path(logo.file).name
        if comp_copy.is_file():
            if _sha256_file(comp_copy) != _sha256_file(kit_svg):
                _flag(flags, "logo", f"{comp_copy.relative_to(comp_dir)} does not match "
                                      f"kit logo '{logo.variant}' — file was altered")

    # --- unknown on-screen names: WARNING, never a failure (T20: positive-only) ------------
    known_names = kit.core_names_official.items + kit.core_names_products.items
    masked = src
    for known in known_names:
        masked = re.sub(re.escape(known), "", masked)
    for name in sorted({m.group(1) for m in TITLE_CASE_RE.finditer(masked)}):
        warnings.append({"kind": "name", "detail": f"on-screen name not in names.official/products: {name!r}"})

    return {"comp": comp_dir.name, "kit": kit.name, "flags": flags, "warnings": warnings}


def lint_prompt(text: str, kit: BrandKit) -> list[dict]:
    """Flag hex codes, font names, and brand/logo words in arbitrary prompt text."""
    return [{"kind": "prompt", "detail": v} for v in find_prompt_violations(text, kit)]
