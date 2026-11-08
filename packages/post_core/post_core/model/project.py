"""Project: the root object naming a project. One per `<root>/.post3/project.json`."""
from __future__ import annotations

from typing import Literal, Optional

from .base import Entity

# T33/T39: the kit a project without its own choice uses: the neutral demo kit in the repo.
# Client kits live with their company in the media library (`<Company>/brand/`), not in git.
DEFAULT_BRAND_KIT = "_demo"

# T42: whether the cut has a presenter on camera (`presenter`) or is a voice with every second
# covered by generated/provided picture (`audio_only`). Steers and constrains Suggest visuals.
PictureMode = Literal["presenter", "audio_only"]
PICTURE_MODES: tuple[str, ...] = ("presenter", "audio_only")


class Project(Entity):
    name: str
    root: str  # absolute path to the project root this store lives under
    # T33: the brand kit's id, a folder under `packages/brandkit/kits/` (see `post_core.brand`).
    brand_kit: str = DEFAULT_BRAND_KIT
    # T39: the company folder this project sits under in the media library
    # (`<library>/<company>/<name>/`); None for a project outside the library.
    company: Optional[str] = None
    picture_mode: PictureMode = "presenter"
