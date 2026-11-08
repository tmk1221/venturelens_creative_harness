"""Small value types shared across the v3 model."""
from __future__ import annotations

from fractions import Fraction

from pydantic import field_validator

from .base import Value


class Rational(Value):
    """An exact rational number (e.g. frame rate 30000/1001), never a lossy float."""

    num: int
    den: int = 1

    @field_validator("den")
    @classmethod
    def _den_nonzero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("Rational denominator must not be zero")
        return v

    def as_fraction(self) -> Fraction:
        return Fraction(self.num, self.den)

    def as_float(self) -> float:
        return self.num / self.den


class WordAnchor(Value):
    """Points at one word in one transcript. The unit of truth for edit-time anchoring."""

    transcript_id: str
    word_id: str
