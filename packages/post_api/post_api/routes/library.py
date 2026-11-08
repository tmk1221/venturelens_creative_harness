"""T39: `GET /api/library` -- the media library's companies (and their projects) for the New
project page's company picker -- and `POST /api/projects/{pid}/models/refresh`, the model
picker's refresh button (asks `higgsfield model list` again and re-caches it in `.post3/`).
Both read only; nothing here writes into the library."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from post_core import library as library_mod
from post_core.recipes import model_list as model_list_mod

from ..deps import get_project_root
from ..models import ModelOptionOut
from .enrich import model_options

router = APIRouter(tags=["library"])


class CompanyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    has_brand: bool
    projects: list[str]


class LibraryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root: str
    exists: bool
    companies: list[CompanyOut]


class ModelListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models: list[ModelOptionOut]
    fetched_at: float


@router.get("/api/library", response_model=LibraryOut)
def library() -> LibraryOut:
    root = library_mod.library_root()
    return LibraryOut(root=str(root), exists=root.is_dir(),
                      companies=[CompanyOut(**c) for c in library_mod.list_companies(root)])


@router.post("/api/projects/{pid}/models/refresh", response_model=ModelListOut)
def refresh_models(root: Path = Depends(get_project_root)) -> ModelListOut:
    try:
        out = model_list_mod.list_models(root, refresh=True)
    except Exception as exc:  # noqa: BLE001 - CLI missing, offline, bad output
        raise HTTPException(status_code=502, detail=f"Couldn't list Higgsfield models: {exc}") from exc
    return ModelListOut(models=model_options(out["models"]), fetched_at=out["fetched_at"])


__all__ = ["router"]
