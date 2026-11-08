"""T34: in-process jobs (`queue.inline`) share the job/event tables with executor jobs, but no
workflow's executor ever claims or "recovers" one that is still running in its thread."""
from __future__ import annotations

import json

from post_core.graph.workflow import Workflow
from post_core.queue import db as db_mod
from post_core.queue.executor import Executor
from post_core.queue.inline import INLINE_LANE, InlineJob, latest_inline_job, recover_inline_jobs


def _rows(root, sql, *params):
    with db_mod.open_db(root) as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def test_inline_job_records_events_and_outcome(tmp_path):
    job = InlineJob.start(tmp_path, workflow_id="_ingest", node_id="project.new", params={"root": "/x"})
    job.emit({"kind": "step", "step": "init", "status": "running"})
    job.emit({"kind": "progress", "step": "audio:0", "i": 40, "n": 100})
    job.finish(False, "Audio for ep.mp4: ffmpeg could not read the file (bad).")

    (row,) = _rows(tmp_path, "SELECT * FROM job")
    assert (row["state"], row["lane"], row["workflow_id"]) == ("failed", INLINE_LANE, "_ingest")
    assert json.loads(row["cmd_json"]) == {"root": "/x"}
    events = _rows(tmp_path, "SELECT seq, kind, json FROM event WHERE job_id=? ORDER BY seq", job.id)
    assert [(e["seq"], e["kind"]) for e in events] == [(0, "step"), (1, "progress"), (2, "result")]
    assert json.loads(events[-1]["json"]) == {"kind": "result", "ok": False, "detail": row["summary"]}
    assert latest_inline_job(tmp_path, "_ingest")["id"] == job.id
    assert latest_inline_job(tmp_path, "other") is None


def test_executor_recovery_leaves_inline_jobs_alone_and_reopen_marks_them(tmp_path, registry):
    job = InlineJob.start(tmp_path, workflow_id="_ingest", node_id="project.new", params={})
    ex = Executor(project_root=tmp_path, workflow=Workflow(recipe_id="r"), registry=registry,
                  cmd_for=lambda nid: ["true"])
    assert ex.recover_interrupted() == []
    assert _rows(tmp_path, "SELECT state FROM job")[0]["state"] == "running"

    assert recover_inline_jobs(tmp_path, "_ingest", live_ids=[job.id]) == []  # still owned by a thread
    assert recover_inline_jobs(tmp_path, "_ingest") == [job.id]  # a fresh process owns nothing
    (row,) = _rows(tmp_path, "SELECT state, summary FROM job")
    assert row["state"] == "interrupted" and "run it again" in row["summary"]
