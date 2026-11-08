"""Executor lifecycle: one background thread per *opened* project, driving every workflow
in that project's store through the queue (T10 spec: "app lifespan starts Executor.serve()
in a background thread per opened project and stops it cleanly").

A project has no single Workflow at open time (workflows are created later, over HTTP), so
this isn't literally one `Executor.serve()` call -- it is a small poll loop that, each tick,
builds a fresh `Executor` for every workflow currently on disk and drains what's runnable
(`recover_interrupted()` once, then `run_once()` until nothing more is pickable). That reuses
the exact same core objects (`queue.executor.Executor`, `cli.context.build_registry`,
`cli.context.cmd_for`) the CLI's own `queue serve` command drives -- no new business logic.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from post_core.cli.context import load_workflow, resolve_project_root
from post_core.queue.executor import Executor
from post_core.store.errors import NotFound
from post_core.store.paths import store_root

from .graph_support import combined_cmd_for, combined_registry

POLL_INTERVAL = 0.25


def _iter_workflow_ids(root: Path) -> list[str]:
    d = store_root(root) / "workflows"
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


class ProjectRuntime:
    """Owns the background queue-draining thread for one opened project."""

    def __init__(self, root: str | Path) -> None:
        self.root = resolve_project_root(str(root))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # Only the workflows already on disk when this runtime starts can hold a job a dead
        # process left `running`. One created later (e.g. a T35 transcription the CLI queued
        # and is running itself) must never have its live job marked interrupted and re-run.
        self._to_recover: set[str] = set()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name=f"post-api-executor-{self.root.name}", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _loop(self) -> None:
        registry = combined_registry()
        self._to_recover = set(_iter_workflow_ids(self.root))
        while not self._stop.is_set():
            for workflow_id in _iter_workflow_ids(self.root):
                if self._stop.is_set():
                    break
                self._drain(registry, workflow_id)
            self._stop.wait(POLL_INTERVAL)

    def _drain(self, registry, workflow_id: str) -> None:
        try:
            workflow, _rev = load_workflow(self.root, workflow_id)
        except NotFound:
            return
        ex = Executor(project_root=self.root, workflow=workflow, registry=registry,
                       cmd_for=combined_cmd_for(workflow, registry, self.root))
        if workflow_id in self._to_recover:
            ex.recover_interrupted()
            self._to_recover.discard(workflow_id)
        while True:
            ran = ex.run_once()
            if not ran or self._stop.is_set():
                break


class RuntimeManager:
    """One `ProjectRuntime` per opened project id."""

    def __init__(self) -> None:
        self._runtimes: dict[str, ProjectRuntime] = {}
        self._lock = threading.Lock()

    def open(self, project_id: str, root: str | Path) -> None:
        with self._lock:
            if project_id in self._runtimes:
                return
            runtime = ProjectRuntime(root)
            self._runtimes[project_id] = runtime
        runtime.start()

    def stop_all(self) -> None:
        with self._lock:
            runtimes = list(self._runtimes.values())
            self._runtimes.clear()
        for runtime in runtimes:
            runtime.stop()


__all__ = ["ProjectRuntime", "RuntimeManager"]
