"""`GET /api/projects/{pid}/events`: one SSE stream per project, fed by polling the queue's
own `event` table (T10 spec: "works across processes" -- no in-memory pub/sub, so this
works even when the job that wrote an event ran in a different process/thread than the one
serving this request). The event table's autoincrement `id` is project-wide and monotonic,
so it doubles as the SSE id: a client's `Last-Event-ID` header (or `?last_event_id=`) resumes
exactly where it left off, even across a dropped connection or a server restart."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from post_core.queue import db as db_mod

from ..deps import get_project_root

router = APIRouter(prefix="/api/projects/{pid}/events", tags=["events"])

POLL_INTERVAL = 0.3
BATCH_LIMIT = 200


def _poll(root: Path, since_id: int, workflow_id: Optional[str]) -> list[dict]:
    query = "SELECT event.id AS row_id, event.job_id, event.seq, event.kind, event.json, event.at, job.workflow_id " \
            "FROM event JOIN job ON job.id = event.job_id WHERE event.id > ?"
    params: list = [since_id]
    if workflow_id:
        query += " AND job.workflow_id = ?"
        params.append(workflow_id)
    query += " ORDER BY event.id LIMIT ?"
    params.append(BATCH_LIMIT)
    with db_mod.open_db(root) as con:
        rows = con.execute(query, params).fetchall()
    return [dict(r) for r in rows]


async def _stream(root: Path, start_id: int, workflow_id: Optional[str], request: Request):
    since_id = start_id
    while True:
        if await request.is_disconnected():
            return
        rows = await asyncio.to_thread(_poll, root, since_id, workflow_id)
        for row in rows:
            since_id = row["row_id"]
            payload = {
                "job_id": row["job_id"], "workflow_id": row["workflow_id"],
                "seq": row["seq"], "kind": row["kind"], "at": row["at"],
                "event": json.loads(row["json"]),
            }
            yield f"id: {row['row_id']}\nevent: {row['kind']}\ndata: {json.dumps(payload)}\n\n"
        if not rows:
            await asyncio.sleep(POLL_INTERVAL)


@router.get("")
async def events(
    request: Request,
    workflow: Optional[str] = Query(None),
    last_event_id: Optional[int] = Query(None, alias="last_event_id"),
    root: Path = Depends(get_project_root),
) -> StreamingResponse:
    header_last_id = request.headers.get("last-event-id")
    start_id = 0
    if header_last_id is not None:
        try:
            start_id = int(header_last_id)
        except ValueError:
            start_id = 0
    elif last_event_id is not None:
        start_id = last_event_id
    return StreamingResponse(
        _stream(root, start_id, workflow, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


__all__ = ["router"]
