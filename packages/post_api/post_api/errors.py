"""Uniform JSON error responses. post_core's own exceptions map onto HTTP status codes
here -- never a raw traceback, and unknown `/api/...` routes always get JSON (FastAPI's
default 404 handler already returns `{"detail": "..."}` JSON, never index.html, as long as
no catch-all static mount shadows `/api`; this app never adds one)."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from post_core.agents import AgentError
from post_core.queue.enqueue import SpendNotAuthorized, UnknownBudget
from post_core.store.errors import CorruptFile, NotFound, RevisionConflict, StoreError

from .registry import UnknownProject


class PathTraversal(ValueError):
    """A path-like id resolved outside the area it is allowed to touch."""


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFound)
    async def _not_found(_request: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": str(exc)})

    @app.exception_handler(UnknownProject)
    async def _unknown_project(_request: Request, exc: UnknownProject) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": str(exc)})

    @app.exception_handler(RevisionConflict)
    async def _conflict(_request: Request, exc: RevisionConflict) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"error": str(exc), "current_revision": exc.actual_rev},
        )

    @app.exception_handler(UnknownBudget)
    async def _unknown_budget(_request: Request, exc: UnknownBudget) -> JSONResponse:
        # T31: a run naming a budget nobody created is a conflict with the project's state
        # (create it first with PUT .../budgets/{id}), not a payment problem.
        return JSONResponse(status_code=409, content={"error": str(exc), "reason": exc.reason})

    @app.exception_handler(SpendNotAuthorized)
    async def _spend_not_authorized(_request: Request, exc: SpendNotAuthorized) -> JSONResponse:
        return JSONResponse(status_code=402, content={"error": str(exc), "reason": exc.reason})

    @app.exception_handler(AgentError)
    async def _agent_error(_request: Request, exc: AgentError) -> JSONResponse:
        # T36: the terminal agent (Claude/Codex CLI) is an upstream service from the API's
        # point of view -- missing, timed out, failed or answered garbage. Nothing was applied.
        return JSONResponse(status_code=502, content={"error": str(exc), "reason": exc.reason})

    @app.exception_handler(PathTraversal)
    async def _path_traversal(_request: Request, exc: PathTraversal) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.exception_handler(CorruptFile)
    async def _corrupt(_request: Request, exc: CorruptFile) -> JSONResponse:
        return JSONResponse(status_code=500, content={"error": str(exc)})

    @app.exception_handler(StoreError)
    async def _store_error(_request: Request, exc: StoreError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.exception_handler(ValueError)
    async def _value_error(_request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.exception_handler(KeyError)
    async def _key_error(_request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": str(exc)})


__all__ = ["install_error_handlers", "PathTraversal"]
