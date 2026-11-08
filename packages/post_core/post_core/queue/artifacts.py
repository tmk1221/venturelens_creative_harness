"""What the executor does with a job's outcome, on disk: move a successful worker's declared
artifacts into the content-addressed artifact dir and write `manifest.json` atomically, or
write the `failed.json` marker `graph.state` already reads (`_has_failed_marker`).

T39: in a library project, generated stills/video are also copied to `AI Generations/`.

This is the one place `graph.state.record_history_entry` is called from (T05 carry-over #1:
`compute_states` reads are pure; recording history happens exactly when a manifest is
written, not as a side effect of every read).
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Sequence

from ..graph.state import artifact_dir, record_history_entry
from ..library import publish_generated
from ..store.atomic import atomic_write_bytes
from ..workers.runner import RunResult


def _resolve_source(raw_path: str, cwd: Path) -> Path:
    p = Path(raw_path)
    return p if p.is_absolute() else (cwd / p)


def finalize_success(
    project_root: str | Path,
    node_type_id: str,
    node_id: str,
    input_hash: str,
    result: RunResult,
    cwd: Path,
    cmd: Sequence[str],
) -> Path:
    """Move every artifact `result` declared into the artifact dir, write its manifest, and
    record this hash in the node's history. Returns the artifact dir."""
    directory = artifact_dir(project_root, node_type_id, input_hash)
    directory.mkdir(parents=True, exist_ok=True)

    outputs = []
    for event in result.artifacts:
        if not event.get("path"):
            continue
        src = _resolve_source(event["path"], cwd)
        dest = directory / src.name
        if src.resolve() != dest.resolve():
            shutil.move(str(src), str(dest))
        # T12 carry-over: pass through every field an `artifact` event declared beyond
        # path/role/sha256 (e.g. `fps_num`/`fps_den`/`duration_frames` from
        # `recipes.workers.asset_verify`'s ffprobe), not just the original three -- so a
        # worker can attach whatever probe data belongs to its own artifact without this
        # module needing to know each node type's vocabulary in advance.
        extra = {k: v for k, v in event.items() if k not in ("kind", "path")}
        outputs.append({"path": dest.name, **extra})

    manifest = {
        "outputs": outputs,
        "finished_at": time.time(),
        "cost": result.cost_total,
        "worker": list(cmd),
    }
    # T39: a library project also gets generated media in `AI Generations/` for Resolve.
    media = [directory / o["path"] for o in outputs if o.get("role") in ("image", "video")]
    try:
        published = publish_generated(project_root, node_type_id, node_id, input_hash, media)
    except OSError as exc:
        manifest["published_error"] = str(exc)
    else:
        if published:
            manifest["published"] = published
    atomic_write_bytes(directory / "manifest.json", contract_json(manifest))

    record_history_entry(project_root, node_id, input_hash)
    return directory


def contract_json(payload: dict) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8")


def mark_failed(
    project_root: str | Path, node_type_id: str, input_hash: str, summary: str
) -> Path:
    directory = artifact_dir(project_root, node_type_id, input_hash)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summary, "at": time.time()}
    atomic_write_bytes(directory / "failed.json", contract_json(payload))
    return directory


__all__ = ["finalize_success", "mark_failed"]
