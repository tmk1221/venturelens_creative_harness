"""`/api/projects`: registry (list/add) and `/api/projects/{pid}` (show from disk; T33/T42: patch
the project's brand kit and picture mode)."""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from post_core import brand as brand_mod
from post_core import picture_mode as picture_mode_mod
from post_core.model.project import Project
from post_core.project_new import RootPlacementError, check_root_placement
from post_core.store import store as store_module
from post_core.store.paths import store_root

from ..deps import get_project_root, get_registry, get_runtime_manager
from ..models import ProjectList, ProjectRef

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    root: str
    name: Optional[str] = None


@router.get("", response_model=ProjectList)
def list_projects(registry=Depends(get_registry)) -> ProjectList:
    return ProjectList(projects=[ProjectRef(**p) for p in registry.list()])


@router.post("", response_model=ProjectRef)
def add_project(body: ProjectCreate, request: Request) -> ProjectRef:
    """Register (or re-register) a project by root path, initialising its `.post3/` store
    if needed, and open it (starts its background queue-draining thread)."""
    root = Path(body.root).resolve()
    if not store_root(root).is_dir():  # T34/T39: never start a new store inside a footage folder
        try:
            check_root_placement(root)
        except RootPlacementError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    store_module.init_project(root)
    project, revision = store_module.try_read(root, "project")
    if project is None:
        project = Project(name=body.name or root.name, root=str(root))
        store_module.write(root, "project", project, expected_rev=0)

    registry = request.app.state.registry
    entry = registry.add(root, name=body.name or project.name)
    request.app.state.runtimes.open(entry["id"], root)
    return ProjectRef(**entry)


@router.get("/{pid}", response_model=Project)
def show_project(root: Path = Depends(get_project_root)) -> Project:
    project, _revision = store_module.read(root, "project")
    return project


class ProjectPatch(BaseModel):
    model_config = {"extra": "forbid"}
    brand_kit: Optional[str] = None
    picture_mode: Optional[Literal["presenter", "audio_only"]] = None


@router.patch("/{pid}", response_model=Project)
def patch_project(body: ProjectPatch, root: Path = Depends(get_project_root)) -> Project:
    """T33: `brand_kit` switches the project's kit (`post_core.brand.set_project_kit`, the
    same op as `post project set-kit`). An unknown kit is a 400 naming the available ones;
    branded nodes go stale and nothing is regenerated."""
    if body.brand_kit is not None:
        brand_mod.set_project_kit(root, body.brand_kit)
    if body.picture_mode is not None:  # T42: same op as `post project set --picture-mode`
        picture_mode_mod.set_picture_mode(root, body.picture_mode)
    project, _revision = store_module.read(root, "project")
    return project


__all__ = ["router"]
