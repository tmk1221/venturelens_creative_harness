"""`/api/projects/{pid}/sources`: probe + add. Mirrors `post source add|probe` -- same
`post_core.ingest.probe`/model calls the CLI makes, no extra logic."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from post_core.ingest.probe import probe_source
from post_core.model.shoot import Shoot, Source, SyncGroup
from post_core.store import store as store_module
from post_core.store.paths import store_root

from ..deps import get_project_root
from ..models import ProbeOut, SourceAddOut

router = APIRouter(prefix="/api/projects/{pid}/sources", tags=["sources"])

DEFAULT_SHOOT_NAME = "default"


class ProbeRequest(BaseModel):
    path: str


class SourceAddRequest(BaseModel):
    path: str
    shoot: Optional[str] = None
    role: str = "other"


def _iter_shoot_ids(root: Path) -> list[str]:
    d = store_root(root) / "shoots"
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def _find_or_create_default_shoot(root: Path) -> tuple[Shoot, int]:
    for shoot_id in _iter_shoot_ids(root):
        shoot, revision = store_module.read(root, "shoot", shoot_id)
        if shoot.name == DEFAULT_SHOOT_NAME:
            return shoot, revision
    shoot = Shoot(name=DEFAULT_SHOOT_NAME)
    revision = store_module.write(root, "shoot", shoot, expected_rev=0)
    return shoot, revision


@router.post("/probe", response_model=ProbeOut)
def source_probe(body: ProbeRequest, root: Path = Depends(get_project_root)) -> dict:
    return probe_source(body.path)


shoots_router = APIRouter(prefix="/api/projects/{pid}/shoots", tags=["sources"])


@shoots_router.get("", response_model=list[Shoot])
def list_shoots(root: Path = Depends(get_project_root)) -> list[Shoot]:
    """Every Shoot in the project, each carrying its Sources (angles), SyncGroups, and
    `transcript_ids` -- the only place a client can resolve a Cut passage's `sync_group_id`
    to the Transcript that holds its words, or an `angle_source_id` to a playable Source."""
    shoots = []
    for shoot_id in _iter_shoot_ids(root):
        shoot, _rev = store_module.read(root, "shoot", shoot_id)
        shoots.append(shoot)
    return shoots


@router.post("", response_model=SourceAddOut)
def source_add(body: SourceAddRequest, root: Path = Depends(get_project_root)) -> SourceAddOut:
    probe = probe_source(body.path)
    if body.shoot:
        shoot, revision = store_module.read(root, "shoot", body.shoot)
    else:
        shoot, revision = _find_or_create_default_shoot(root)

    source = Source(
        path=probe["path"], fps=probe["fps"], start_timecode=probe["start_timecode"],
        role=body.role, content_fingerprint=probe["content_fingerprint"],
    )
    sync_group = SyncGroup(source_ids=[source.id], offsets={source.id: 0.0})
    updated = shoot.model_copy(update={
        "sources": [*shoot.sources, source],
        "sync_groups": [*shoot.sync_groups, sync_group],
    })
    store_module.write(root, "shoot", updated, expected_rev=revision)
    return SourceAddOut(
        shoot_id=shoot.id, source_id=source.id, sync_group_id=sync_group.id, probe=probe,
    )


__all__ = ["router", "shoots_router"]
