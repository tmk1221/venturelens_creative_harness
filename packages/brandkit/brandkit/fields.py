"""fields.py — the fillable-field dataclasses that make up a `BrandKit` (schema.py).

Split out of schema.py purely to keep files small; `schema.py` owns all parsing/
validation logic and imports these as plain data containers. Most fields carry
`status: "filled" | "pending"` and `guessed: bool` — see schema.py's module docstring.

T20 (2026-09-21): the kit is rebuilt around a single `core` — identity, colours (role-
tagged, world_tone/dominant), typography, logos (moved here from `animation`),
personality, world (subject matter, positive only), names, sources. `animation` shrinks
to pure motion/graphics behaviour. Everything is positive-only: no forbid lists, no
brand-level negatives.
"""
from __future__ import annotations

from dataclasses import dataclass, field

COLOUR_ROLES = ("primary", "secondary", "accent", "dark_neutral", "light_neutral")
TYPOGRAPHY_ROLES = ("heading", "body", "mono")
WORLD_TONES = ("light", "dark")
TYPOGRAPHY_SOURCES = ("google", "file")
SOURCE_KINDS = ("website", "style_guide", "file")


@dataclass
class TextField:
    """A generic fillable free-text kit field."""
    text: str | None
    status: str
    guessed: bool


@dataclass
class ColourEntry:
    """One of the kit's 3-6 real brand colours. `role` is the dict key it's stored under
    on `BrandKit.core_colours` (one of `fields.COLOUR_ROLES`) as well as its own value,
    kept on the object for convenience when iterating `.values()`."""
    role: str
    name_plain: str | None
    hex: str | None
    status: str
    guessed: bool


@dataclass
class ItemsList:
    """A capped/countable list of short strings. `status` describes the list as a whole
    (pending until someone's actually approved entries)."""
    items: list[str]
    status: str
    guessed: bool = False  # T33: true only in a kit `init --from` drafted (brand-kit.json guessed)


@dataclass
class StyleBlock:
    """The derived-from-images still-style description (see derive.py): derived from real
    reference images (and reviewed/accepted by a human), or it doesn't exist yet (`status:
    pending`). T33: `guessed` is true only when `init --from` drafted it from site copy."""
    text: str | None
    version: str | None
    derived_from: list[str] = field(default_factory=list)
    status: str = "pending"
    guessed: bool = False


@dataclass
class TypeRole:
    """A typography role (`heading`/`body`/optional `mono`). `source` is `google` (load
    from Google Fonts at render time) or `file` (a local `.woff2`/`.ttf` under the kit)."""
    key: str
    family: str | None
    source: str | None
    file: str | None
    status: str
    guessed: bool


@dataclass
class LogoPlacement:
    position: str
    inset_px: float
    height_px: float


@dataclass
class Logo:
    variant: str
    file: str | None
    clear_space: float | None
    min_size_px: float | None
    placements: dict[str, LogoPlacement]
    status: str
    guessed: bool


@dataclass
class CaptionStyle:
    font_role: str
    palette: dict[str, str]
    band: float
    max_words: int
    font_scale: float
    status: str
    guessed: bool


@dataclass
class CssVar:
    """A raw CSS custom property override — an explicit value for a UI shade that
    `ui_shades.derive_ui_shades` would otherwise compute (e.g. Acme's recorded
    brand.css values), or a craft-level token that isn't a real brand colour at all."""
    key: str
    value: str | None
    status: str
    guessed: bool
