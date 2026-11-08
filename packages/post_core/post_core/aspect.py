"""Aspect ratios in plain words (T37): "4:5" for people, "4x5" for file names, an exact
`Fraction` for comparisons, and the delivery resolution each one is meant to land at.

One small, pure module that recipes (what to generate at), `asset.verify` (does the clip
match) and export (what the timeline is called) all share, so a 4:5 short is "4:5" in
every place it is named.
"""
from __future__ import annotations

import math
from fractions import Fraction
from typing import Optional, Sequence, Union

from .model.common import Rational

AspectLike = Union[str, Rational, Fraction]

# The resolution a cut of each aspect is delivered at (T37 spec): 1080 on the short side.
INTENDED_RESOLUTION: dict[str, tuple[int, int]] = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "4:5": (1080, 1350),
    "1:1": (1080, 1080),
}


def to_fraction(value: AspectLike) -> Fraction:
    """`"4:5"`, `"4x5"`, `"4/5"`, a `Rational` or a `Fraction` -> `Fraction(4, 5)`."""
    if isinstance(value, Fraction):
        result = value
    elif isinstance(value, Rational):
        result = value.as_fraction()
    else:
        raw = str(value).strip().lower()
        for sep in (":", "x", "/"):
            if sep in raw:
                left, _, right = raw.partition(sep)
                result = Fraction(int(left), int(right))
                break
        else:
            raise ValueError(f"not an aspect ratio: {value!r}")
    if result <= 0:
        raise ValueError(f"aspect ratio must be positive: {value!r}")
    return result


# Conventional names that are not in lowest terms (21:9 is 7:3).
_NAMED: dict[Fraction, str] = {Fraction(21, 9): "21:9", Fraction(9, 21): "9:21"}


def label(value: AspectLike) -> str:
    """Reduced, human form: `Rational(16, 9)` -> `"16:9"`, `"8:10"` -> `"4:5"` (but 21:9 stays
    21:9, its conventional name)."""
    f = to_fraction(value)
    return _NAMED.get(f, f"{f.numerator}:{f.denominator}")


def token(value: AspectLike) -> str:
    """File-name form: `"4:5"` -> `"4x5"` (a colon is not safe in every file system)."""
    return label(value).replace(":", "x")


def same(a: AspectLike, b: AspectLike) -> bool:
    return to_fraction(a) == to_fraction(b)


def intended_resolution(value: AspectLike) -> tuple[int, int]:
    """(width, height) a cut of this aspect is delivered at: the table above, else 1080 on
    the short side with the long side rounded to an even number of pixels."""
    name = label(value)
    if name in INTENDED_RESOLUTION:
        return INTENDED_RESOLUTION[name]
    f = to_fraction(value)
    if f >= 1:
        return _even(1080 * f), 1080
    return 1080, _even(1080 / f)


def _even(x: Fraction) -> int:
    return int(round(x / 2)) * 2


def matches(width: int, height: int, value: AspectLike, tolerance: float = 0.01) -> bool:
    """Whether a `width`x`height` frame is `value`, within `tolerance` (relative) -- even-pixel
    rounding means a crop is rarely the exact fraction."""
    if not width or not height:
        return False
    target = float(to_fraction(value))
    return abs((width / height) / target - 1.0) <= tolerance


def _covers(candidate: Fraction, target: Fraction) -> bool:
    """A frame generated at `candidate` covers a `target` frame when, scaled to the target's
    short side, it is at least as long on the long side -- so the target is a crop along one
    axis and its short side keeps every generated pixel. Portrait targets want an equal or
    taller candidate, landscape ones an equal or wider one; a square target is covered by
    anything."""
    if target < 1:
        return candidate <= target
    if target > 1:
        return candidate >= target
    return True


def choose_generation_aspect(target: AspectLike, offered: Optional[Sequence[str]]) -> tuple[str, Optional[str]]:
    """What to generate at for a `target` frame, given a model's `offered` aspects:
    `(generate_at, crop_to)`. `crop_to` is `None` when the model offers the target itself (or
    when nothing is known about what it offers); otherwise it is the target, and
    `generate_at` is the nearest offered aspect that covers the frame (`_covers`), or the
    nearest offered aspect of all when none covers it."""
    want = to_fraction(target)
    if not offered:
        return label(want), None
    parsed = [(to_fraction(o), label(o)) for o in offered]
    for f, name in parsed:
        if f == want:
            return name, None
    covering = [(f, name) for f, name in parsed if _covers(f, want)]
    pool = covering or parsed
    _f, best = min(pool, key=lambda item: abs(math.log(item[0] / want)))
    return best, label(want)


__all__ = [
    "INTENDED_RESOLUTION", "to_fraction", "label", "token", "same", "intended_resolution",
    "matches", "choose_generation_aspect",
]
