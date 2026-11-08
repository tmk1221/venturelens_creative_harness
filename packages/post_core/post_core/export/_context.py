"""Read-only project data loading for export: shoots, sources, sync groups, transcripts,
and the assets that back workflow spans. Nothing here writes to disk.

`find_asset_for_node` is a deliberate simplification: T09 does not walk the full
build-graph node-state machine (`graph/state.py`), because the concrete compute node
types it would need to resolve `done` for (image/video generation) don't exist yet --
they land in T12, and `graph/` is being worked on concurrently by another task. Instead,
an Asset is treated as "done" once a matching `Asset` record exists on disk (keyed by
`node_id`, T02) and its file is present, and "approved" is checked the real way, via
`graph.approvals.is_approved(content_hash)`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..edit.ranges import TranscriptIndex
from ..graph.approvals import is_approved
from ..model.asset import Asset
from ..model.cut import Cut
from ..model.shoot import Shoot, Source, SyncGroup
from ..model.transcript import Transcript
from ..store import read as store_read
from ..store.paths import store_root


@dataclass
class ExportContext:
    project_root: Path
    cut: Cut
    sources: dict[str, Source]
    sync_groups: dict[str, SyncGroup]
    transcripts: dict[str, Transcript]
    index: TranscriptIndex

    def sync_group_of(self, sync_group_id: str) -> SyncGroup:
        try:
            return self.sync_groups[sync_group_id]
        except KeyError:
            raise KeyError(f"no SyncGroup {sync_group_id!r} found in any shoot") from None

    def source(self, source_id: str) -> Source:
        try:
            return self.sources[source_id]
        except KeyError:
            raise KeyError(f"no Source {source_id!r} found in any shoot") from None


def _load_shoots(project_root: str | Path) -> list[Shoot]:
    shoots_dir = store_root(project_root) / "shoots"
    if not shoots_dir.exists():
        return []
    shoots = []
    for f in sorted(shoots_dir.glob("*.json")):
        obj, _ = store_read(project_root, "shoot", f.stem)
        shoots.append(obj)
    return shoots


def _load_transcripts(project_root: str | Path) -> dict[str, Transcript]:
    tdir = store_root(project_root) / "transcripts"
    out: dict[str, Transcript] = {}
    if not tdir.exists():
        return out
    for f in sorted(tdir.glob("*.json")):
        obj, _ = store_read(project_root, "transcript", f.stem)
        out[obj.id] = obj
    return out


def load_context(project_root: str | Path, cut_id: str) -> ExportContext:
    cut, _ = store_read(project_root, "cut", cut_id)
    shoots = _load_shoots(project_root)
    sources: dict[str, Source] = {}
    sync_groups: dict[str, SyncGroup] = {}
    for shoot in shoots:
        for source in shoot.sources:
            sources[source.id] = source
        for group in shoot.sync_groups:
            sync_groups[group.id] = group
    transcripts = _load_transcripts(project_root)
    index = TranscriptIndex(transcripts.values())
    return ExportContext(
        project_root=Path(project_root).resolve(),
        cut=cut,  # type: ignore[arg-type]
        sources=sources,
        sync_groups=sync_groups,
        transcripts=transcripts,
        index=index,
    )


def find_asset_for_node(project_root: str | Path, node_id: str) -> Optional[Asset]:
    """The Asset recorded against build-graph node `node_id`, if any (see module docstring)."""
    assets_dir = store_root(project_root) / "assets"
    if not assets_dir.exists():
        return None
    for f in sorted(assets_dir.glob("*.json")):
        obj, _ = store_read(project_root, "asset", f.stem)
        if obj.node_id == node_id:  # type: ignore[union-attr]
            return obj  # type: ignore[return-value]
    return None


def asset_done_and_approved(project_root: str | Path, asset: Optional[Asset]) -> bool:
    if asset is None:
        return False
    if not Path(asset.path).is_file():
        return False
    return is_approved(project_root, asset.content_hash)
