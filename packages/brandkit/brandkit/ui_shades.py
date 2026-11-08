"""ui_shades.py — GENERATE a kit's UI shade ramp from its real brand colours (T20).

`derive_ui_shades` takes the kit's `core.colours` (role -> hex) plus `world_tone`
("light" | "dark") and produces the craft-level tokens `compile.compile_css` needs but
that are never hand-picked brand colours in their own right: a ground, a surface tier
(surface/surface_2/surface_3), an ink tier (ink/ink_dim/ink_faint), a hairline, and an
accent wash. Everything is a plain sRGB lerp between the kit's own colours (no external
dependency — AGENTS.md: stdlib-first). A kit may still record explicit `animation.
css_vars` overrides for any of these keys (see `compile.compile_css`) — that's how
Acme's existing brand.css values are preserved unchanged by this rewrite.

`check_contrast` runs WCAG 2.x contrast (relative luminance ratio) between the ink tier
and every surface tier, raising `UIShadesError` if any pair falls under 4.5:1.
"""
from __future__ import annotations

HEX_RE_LEN = 7  # "#RRGGBB"

SHADE_KEYS = ("ground", "surface", "surface_2", "surface_3", "ink", "ink_dim", "ink_faint",
              "hairline", "accent_wash")


class UIShadesError(ValueError):
    """A derived UI shade ramp fails WCAG contrast (or bad input)."""


def _hex_to_rgb(hexv: str) -> tuple[int, int, int]:
    h = hexv.lstrip("#")
    if len(h) != 6:
        raise UIShadesError(f"not a 6-digit hex colour: {hexv!r}")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    r, g, b = (max(0, min(255, round(c))) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def mix(hex_a: str, hex_b: str, t: float) -> str:
    """Linear sRGB lerp from `hex_a` (t=0) to `hex_b` (t=1)."""
    a, b = _hex_to_rgb(hex_a), _hex_to_rgb(hex_b)
    return _rgb_to_hex(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))


def _srgb_channel_to_linear(c: int) -> float:
    cs = c / 255.0
    return cs / 12.92 if cs <= 0.04045 else ((cs + 0.055) / 1.055) ** 2.4


def relative_luminance(hexv: str) -> float:
    r, g, b = _hex_to_rgb(hexv)
    r, g, b = (_srgb_channel_to_linear(c) for c in (r, g, b))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    la, lb = relative_luminance(hex_a), relative_luminance(hex_b)
    lighter, darker = (la, lb) if la >= lb else (lb, la)
    return (lighter + 0.05) / (darker + 0.05)


def check_contrast(shades: dict[str, str], ink_key: str = "ink", min_ratio: float = 4.5) -> None:
    ink = shades[ink_key]
    for key in ("ground", "surface", "surface_2", "surface_3"):
        if key not in shades:
            continue
        ratio = contrast_ratio(ink, shades[key])
        if ratio < min_ratio:
            raise UIShadesError(
                f"derived UI shades fail contrast: {ink_key} on {key} is {ratio:.2f}:1, "
                f"below the {min_ratio}:1 minimum"
            )


def derive_ui_shades(colours: dict[str, str], world_tone: str) -> dict[str, str]:
    """`colours`: {role: hex} for whichever of primary/secondary/accent/dark_neutral/
    light_neutral the kit defines. `world_tone`: "light" or "dark" — which pole the frame
    reads as. Returns the 9 `SHADE_KEYS` hexes. Raises `UIShadesError` if the resulting
    ink-on-surface contrast fails WCAG 4.5:1."""
    if world_tone not in ("light", "dark"):
        raise UIShadesError(f"world_tone must be 'light' or 'dark', got {world_tone!r}")
    light = colours.get("light_neutral") or "#FFFFFF"
    dark = colours.get("dark_neutral") or "#000000"
    accent = colours.get("accent") or colours.get("primary") or (dark if world_tone == "light" else light)

    ground, ink = (light, dark) if world_tone == "light" else (dark, light)
    toward_ink = ink
    toward_ground = ground

    shades = {
        "ground": ground,
        "surface": mix(ground, toward_ink, 0.02),
        "surface_2": mix(ground, toward_ink, 0.045),
        "surface_3": mix(ground, toward_ink, 0.09),
        "ink": ink,
        "ink_dim": mix(ink, toward_ground, 0.35),
        "ink_faint": mix(ink, toward_ground, 0.55),
        "hairline": mix(ground, toward_ink, 0.12),
        "accent_wash": mix(accent, toward_ground, 0.85),
    }
    check_contrast(shades)
    return shades
