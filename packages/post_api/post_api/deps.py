"""Per-request dependencies: turn a `{pid}` path segment into a project root, and register
this app's `ProjectRuntime`/registry on `app.state` so route modules never touch a global."""
from __future__ import annotations

from pathlib import Path

from fastapi import Request

from post_core.cli.context import resolve_project_root

from .registry import ProjectRegistry
from .runtime import RuntimeManager


def get_registry(request: Request) -> ProjectRegistry:
    return request.app.state.registry


def get_runtime_manager(request: Request) -> RuntimeManager:
    return request.app.state.runtimes


def get_project_root(pid: str, request: Request) -> Path:
    """Resolve `pid` to its project root via the registry -- never from anything the client
    supplies directly, so a client can never point a route at an arbitrary filesystem path."""
    registry: ProjectRegistry = request.app.state.registry
    root = registry.root_for(pid)
    return resolve_project_root(str(root))


__all__ = ["get_registry", "get_runtime_manager", "get_project_root"]
