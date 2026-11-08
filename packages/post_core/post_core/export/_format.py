"""T37: what format an export says it is. The timeline name and file name carry the cut's
aspect (`<cut>_4x5_v003`), the timeline's `post3` metadata carries the aspect and intended
delivery resolution, and a README beside each export says what the A-roll is and that it is
reframed in Resolve. Post never reframes the A-roll and never scripts Resolve; whether
Resolve honours the metadata on import is H1's open question.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .. import aspect as aspect_mod
from ..model.cut import Cut
from ..store import read as store_read


@dataclass(frozen=True)
class ExportFormat:
    aspect: str  # "4:5"
    width: int
    height: int
    a_roll_aspect: str  # the source frame, "16:9"

    @property
    def token(self) -> str:
        return aspect_mod.token(self.aspect)

    @property
    def reframed(self) -> bool:
        return not aspect_mod.same(self.aspect, self.a_roll_aspect)

    def metadata(self, cut: Cut) -> dict:
        return {
            "cut_id": cut.id,
            "aspect": self.aspect,
            "resolution": {"width": self.width, "height": self.height},
            "fps": {"num": cut.fps.num, "den": cut.fps.den},
            "a_roll_aspect": self.a_roll_aspect,
            "a_roll_reframed_in": "resolve" if self.reframed else None,
        }


def _a_roll_aspect(project_root: str | Path, cut: Cut) -> str:
    """The A-roll's frame: the aspect of the cut this one was derived from, all the way up
    (a project's first cut is made at the recording's aspect; shorts are derived from it).
    Sources carry no frame size, and export never probes media."""
    current, seen = cut, {cut.id}
    while current.parent_cut_id and current.parent_cut_id not in seen:
        seen.add(current.parent_cut_id)
        try:
            parent, _rev = store_read(project_root, "cut", current.parent_cut_id)
        except Exception:  # noqa: BLE001 -- a missing parent just ends the walk
            break
        current = parent  # type: ignore[assignment]
    return aspect_mod.label(current.aspect)


def export_format(project_root: str | Path, cut: Cut) -> ExportFormat:
    aspect = aspect_mod.label(cut.aspect)
    width, height = aspect_mod.intended_resolution(aspect)
    return ExportFormat(aspect=aspect, width=width, height=height, a_roll_aspect=_a_roll_aspect(project_root, cut))


def readme_text(fmt: ExportFormat, otio_name: str, cut: Cut) -> str:
    fps = cut.fps.as_fraction()
    fps_text = str(fps.numerator) if fps.denominator == 1 else f"{float(fps):.3f}".rstrip("0").rstrip(".")
    lines = [
        f"{otio_name}: a {fmt.aspect} timeline at {fmt.width}x{fmt.height}, {fps_text} fps.",
        (
            f"The A-roll is {fmt.a_roll_aspect} and is reframed in Resolve to {fmt.aspect}; Post does not reframe it."
            if fmt.reframed else
            f"The A-roll is {fmt.a_roll_aspect}, the same as this timeline; no reframe needed."
        ),
        f"If the import does not set the timeline to {fmt.width}x{fmt.height}, set it by hand"
        " (whether Resolve reads the OTIO metadata is still open: H1).",
    ]
    return "\n".join(lines) + "\n"


__all__ = ["ExportFormat", "export_format", "readme_text"]
