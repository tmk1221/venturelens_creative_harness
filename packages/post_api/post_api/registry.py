"""The project registry: which project ids map to which root directories on disk.

Many projects are addressable at once (T10 spec: "NO module-level 'open project' global"),
so the registry is its own small JSON file (atomic write via post_core's own primitives),
separate from any single project's `.post3/` store. A registry entry's `id` is what every
`/api/projects/{pid}/...` route takes; the actual project object (name etc.) still lives in
that project's own `.post3/project.json`, read fresh on every request.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from post_core.store.atomic import atomic_write_bytes
from post_core.model.base import new_id

import json


class UnknownProject(KeyError):
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        super().__init__(f"no registered project {project_id!r}")


class ProjectRegistry:
    """Persisted `{id: {"root": "...", "name": "..."}}` map, guarded by an in-process lock
    (registry files are small and local -- unlike a project's own store, nothing here needs
    cross-process file locking)."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()

    def _read(self) -> dict[str, dict]:
        if not self._path.is_file():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except ValueError:
            return {}
        return data.get("projects", {}) if isinstance(data, dict) else {}

    def _write(self, projects: dict[str, dict]) -> None:
        atomic_write_bytes(self._path, json.dumps({"projects": projects}, indent=2).encode("utf-8"))

    def list(self) -> list[dict]:
        with self._lock:
            projects = self._read()
        return [{"id": pid, **entry} for pid, entry in sorted(projects.items())]

    def add(self, root: str | Path, name: Optional[str] = None) -> dict:
        resolved = str(Path(root).resolve())
        with self._lock:
            projects = self._read()
            for pid, entry in projects.items():
                if entry.get("root") == resolved:
                    return {"id": pid, **entry}
            pid = new_id()
            entry = {"root": resolved, "name": name or Path(resolved).name}
            projects[pid] = entry
            self._write(projects)
        return {"id": pid, **entry}

    def root_for(self, project_id: str) -> Path:
        with self._lock:
            projects = self._read()
        entry = projects.get(project_id)
        if entry is None:
            raise UnknownProject(project_id)
        return Path(entry["root"])

    def remove(self, project_id: str) -> bool:
        with self._lock:
            projects = self._read()
            if project_id not in projects:
                return False
            del projects[project_id]
            self._write(projects)
        return True


__all__ = ["ProjectRegistry", "UnknownProject"]
