"""T34: the new-project ingest as a background job, not a blocking request. Runs
`post_core.project_new.new_project` -- the same op as `post project new` -- on a thread,
recording its `step`/`progress` events as an in-process queue job (`post_core.queue.inline`),
so `GET /api/projects/{pid}/events?workflow=_ingest` streams them like any worker's.

`start` returns once the job's `init` step has written `project.json` (milliseconds), so the
project a client is sent to next always exists. One app owns the live threads (`app.state`);
a job left `running` by a previous process is marked `interrupted` when its project opens.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from post_core.project_new import NewProjectError, new_project
from post_core.queue.inline import InlineJob, latest_inline_job, recover_inline_jobs

INGEST_WORKFLOW = "_ingest"
NODE_ID = "project.new"
INIT_WAIT_SECONDS = 15.0


class IngestAlreadyRunning(RuntimeError):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__("This project's ingest is already running; wait for it to finish.")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _summary(out: dict) -> str:
    """e.g. "Ready: 1 recording, 4 steps done." / "Ready: 1 recording, 5 already done."."""
    done = sum(1 for s in out["steps"] if s["status"] == "done" and s["step"] != "check")
    skipped = sum(1 for s in out["steps"] if s["status"] == "skipped")
    parts = [f"Ready: {_plural(len(out['sources']), 'recording')}"]
    parts += [f"{_plural(done, 'step')} done"] if done else []
    parts += [f"{skipped} already done"] if skipped else []
    return ", ".join(parts) + "."


class IngestJobs:
    def __init__(self) -> None:
        self._live: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        # Held while a job row is created and registered as live, and while stale rows are
        # recovered, so a recovery can never catch a brand-new row before its thread exists.
        self._rows = threading.RLock()

    def live_ids(self) -> list[str]:
        # Registered before the thread starts and removed in its `finally`, so membership
        # alone (not `is_alive`) is what "a thread owns this row" means.
        with self._lock:
            return list(self._live)

    def recover(self, root: str | Path) -> list[str]:
        with self._rows:
            return recover_inline_jobs(root, INGEST_WORKFLOW, self.live_ids())

    def latest(self, root: str | Path) -> Optional[dict]:
        self.recover(root)
        return latest_inline_job(root, INGEST_WORKFLOW)

    def start(self, root: str | Path, params: dict) -> str:
        """`params`: `{root, name, sources, transcripts, brand_kit, company, copy}` (already validated)."""
        init_seen = threading.Event()
        with self._rows:
            latest = self.latest(root)
            if latest is not None and latest["state"] == "running":
                raise IngestAlreadyRunning(latest["id"])
            job = InlineJob.start(root, workflow_id=INGEST_WORKFLOW, node_id=NODE_ID, params=params)
            thread = threading.Thread(target=self._run, args=(job, params, init_seen),
                                      name=f"post-api-ingest-{job.id[:8]}", daemon=True)
            with self._lock:
                self._live[job.id] = thread
        thread.start()
        init_seen.wait(INIT_WAIT_SECONDS)
        return job.id

    def _run(self, job: InlineJob, params: dict, init_seen: threading.Event) -> None:
        def emit(event: dict) -> None:
            job.emit(event)
            if event.get("step") == "init" and event.get("status") in ("done", "skipped", "failed"):
                init_seen.set()

        try:
            out = new_project(params["root"], params.get("name"), params["sources"],
                              transcripts=params.get("transcripts") or [], kit=params.get("brand_kit"), emit=emit,
                              company=params.get("company"), copy=bool(params.get("copy")))
            job.finish(True, _summary(out))
        except NewProjectError as exc:
            job.finish(False, str(exc))
        except Exception as exc:  # noqa: BLE001 - a job always ends with a recorded outcome
            job.finish(False, f"Something went wrong: {type(exc).__name__}: {exc}")
        finally:
            init_seen.set()
            with self._lock:
                self._live.pop(job.id, None)


__all__ = ["INGEST_WORKFLOW", "IngestAlreadyRunning", "IngestJobs"]
