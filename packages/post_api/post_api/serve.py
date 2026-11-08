"""ASGI entrypoint for running `post_api` as a real server (dev/demo use --
`packages/post_api/.venv/bin/uvicorn post_api.serve:app_factory --factory`). Not exercised
by pytest (TestClient builds `create_app()` directly); this only wires the registry path,
which every other entrypoint (`python -m post_api.openapi`, the test fixtures) picks
explicitly for its own purpose instead.

Registry path comes from `POST_API_REGISTRY` so the same command works for a real project
registry or the T19 demo one (`scripts/dev.sh` sets it to `.demo/registry.json`); it
defaults to `.post_api_registry.json` in the current directory so `uvicorn post_api.serve:app_factory
--factory` also works with no setup for a quick manual check.
"""
from __future__ import annotations

import os

from .app import create_app


def app_factory():
    registry_path = os.environ.get("POST_API_REGISTRY", ".post_api_registry.json")
    return create_app(registry_path)


__all__ = ["app_factory"]
