"""T33: `GET /api/brand-kits` -- every kit a project can use, with its readiness (the same
`brandkit status` counts), for the web kit picker (T39: `?project=` adds its company's kit). Choosing one is `PATCH /api/projects/{pid}`
(`routes/projects.py`); both go through `post_core.brand`, like the CLI's `project set-kit`."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from post_core import brand as brand_mod

router = APIRouter(prefix="/api/brand-kits", tags=["brand"])


class BrandKitCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filled: int
    guessed: int
    pending: int
    total: int


class BrandKitOut(BaseModel):
    """`status`: `filled` (every filled field confirmed), `guessed` (some filled field is a
    first guess, e.g. drafted by `brandkit init --from`), `broken` (the kit does not load)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    status: Literal["filled", "guessed", "broken"]
    counts: Optional[BrandKitCounts] = None
    error: Optional[str] = None


class BrandKitList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kits: list[BrandKitOut]


@router.get("", response_model=BrandKitList)
def list_brand_kits(request: Request, project: Optional[str] = None) -> BrandKitList:
    """T39: with `?project=<pid>`, a library project's company kit comes first."""
    root = request.app.state.registry.root_for(project) if project else None
    return BrandKitList(kits=[BrandKitOut(**k) for k in brand_mod.list_kit_summaries(root)])


__all__ = ["router"]
