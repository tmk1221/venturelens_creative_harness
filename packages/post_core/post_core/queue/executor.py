"""The worker loop: pick ready jobs, run them via the T03 runner, and record what happened.

Ports the ideas worth keeping from the old app's queue (`~/cc/post/backend/app/jobs.py`):
lane concurrency (a fixed worker count per lane, not one big pool -- a one-off job should
not queue behind a batch), a resource lock (T06 carry-over #3: `NodeType.resources`, not a
magic lane name) serialising anything that touches a shared, stateful external tool like
DaVinci Resolve regardless of lane, and "running when the process died" becoming a distinct
`interrupted` state rather than `failed` or `done`.

One `Executor` instance owns one workflow's queue traffic. Two ways to drive it:
`recover_interrupted()` once at startup then `run_once()` repeatedly (single-threaded,
deterministic -- what the tests use); or `serve()` (T06 carry-over #1), a persistent loop
that dispatches picked jobs to a real thread pool sized per lane so lane limits are actually
used for concurrency, not just respected one job at a time.
"""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..graph.hashing import compute_hashes
from ..graph.plan import Plan, plan as plan_fn
from ..graph.lanes import DEFAULT_LANES
from ..graph.registry import NodeRegistry
from ..graph.state import NodeState, compute_states
from ..graph.workflow import Workflow
from ..workers import runner as runner_mod
from . import artifacts, authorisation as authorisation_mod, budget as budget_mod, db as db_mod
from .enqueue import Authorization, CmdFor, SpendNotAuthorized, UnknownBudget, enqueue
from .resolve_lock import resource_lock

# Lane concurrency: defined in `graph.lanes` (T18 item 4 added "default", limit 2, so a node
# type left at `NodeType.lane`'s default is scheduled; the registry rejects any other name).

# A provider limit with no `retry_at` in its result event waits this long before retrying.
DEFAULT_RETRY_SECONDS = 1800.0

RunFn = Callable[..., runner_mod.RunResult]


@dataclass
class Executor:
    project_root: str | Path
    workflow: Workflow
    registry: NodeRegistry
    cmd_for: CmdFor
    lanes: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_LANES))
    authorization: Optional[Authorization] = None
    cwd: Optional[Path] = None
    run_fn: RunFn = runner_mod.run
    now: Callable[[], float] = time.time

    def _cwd(self) -> Path:
        return self.cwd if self.cwd is not None else Path(self.project_root)

    # ------------------------------------------------------------------ startup recovery
    def recover_interrupted(self) -> list[str]:
        """Any job still `running` when the process last stopped did not finish and did not
        fail -- mark it `interrupted`, then requeue its node if it is still ready. A
        recovered node is resumed with whatever authorisation named the interrupted job
        itself (T06 carry-over #2: that authorisation is durable, so a brand new process
        with no in-memory Authorization at all can still legitimately re-run the exact same
        spend it was already authorised for -- this is not the same thing as
        `covers_downstream`, which is about *new* nodes becoming ready, not resuming one
        that was already authorised). T34: only this executor's own lanes -- an in-process
        job (`queue.inline`) lives in a lane no executor runs, so it is never touched here."""
        lanes = tuple(self.lanes)
        with db_mod.open_db(self.project_root) as con:
            rows = [dict(r) for r in con.execute(
                "SELECT id, node_id, authorisation_id FROM job WHERE state='running' "
                f"AND lane IN ({','.join('?' * len(lanes))})", lanes,
            ).fetchall()]
            now = self.now()
            for row in rows:
                con.execute(
                    "UPDATE job SET state='interrupted', finished_at=?, "
                    "summary='the process stopped while this was running' WHERE id=?",
                    (now, row["id"]),
                )
            con.commit()
        for row in rows:
            self._enqueue_ready([row["node_id"]], source_job=row, resume=True)
        return [row["id"] for row in rows]

    # ------------------------------------------------------------------ picking + running
    def _lane_hold_until(self, con, lane: str) -> float:
        row = con.execute(
            "SELECT MAX(not_before) AS h FROM job WHERE lane=? AND state='retry_later'", (lane,)
        ).fetchone()
        return row["h"] or 0.0

    def _pick_jobs(self, con) -> list[dict]:
        now = self.now()
        picked: list[dict] = []
        for lane, limit in self.lanes.items():
            running = con.execute(
                "SELECT COUNT(*) AS c FROM job WHERE lane=? AND state='running'", (lane,)
            ).fetchone()["c"]
            slots = limit - running
            if slots <= 0:
                continue
            if now < self._lane_hold_until(con, lane):
                continue  # a provider limit holds the whole lane, not just that one job
            # T30d fix: scoped to *this* Executor's own workflow. `runtime.py`'s background
            # drain loop builds one fresh `Executor` per workflow_id on disk, all sharing one
            # project-wide `queue.db` (lane concurrency -- `running`/`_lane_hold_until` above
            # -- is deliberately project-wide, per ARCHITECTURE.md's "a fixed worker count per
            # lane"). Without this filter, a project with more than one instantiated workflow
            # (e.g. two beats both mid-plan) could have workflow A's `Executor` claim a job
            # that actually belongs to workflow B: `self.workflow.node(job["node_id"])` then
            # raises `KeyError` (the id genuinely isn't in *this* workflow), which kills the
            # whole background thread for the rest of the project's session -- silently, since
            # it's an uncaught exception in a daemon thread. Reproduced by `test_executor.py`'s
            # `test_jobs_are_scoped_to_their_own_workflow_when_sharing_a_project`.
            rows = con.execute(
                """SELECT * FROM job WHERE lane=? AND workflow_id=? AND
                       (state='queued' OR (state='retry_later' AND
                                            (not_before IS NULL OR not_before <= ?)))
                   ORDER BY created_at LIMIT ?""",
                (lane, self.workflow.id, now, slots),
            ).fetchall()
            picked.extend(dict(r) for r in rows)
        return picked

    def _claim_jobs(self, con) -> list[dict]:
        jobs = self._pick_jobs(con)
        now = self.now()
        for job in jobs:
            con.execute(
                "UPDATE job SET state='running', started_at=?, attempts=attempts+1 WHERE id=?",
                (now, job["id"]),
            )
        con.commit()
        return jobs

    def run_once(self) -> list[str]:
        """Run every job currently pickable across all lanes, one at a time. Returns the
        job ids run. Deterministic and single-threaded -- what tests drive directly; `serve()`
        is the persistent, actually-concurrent-per-lane version of the same picking logic."""
        with db_mod.open_db(self.project_root) as con:
            jobs = self._claim_jobs(con)

        for job in jobs:
            self._run_job(job)
        return [job["id"] for job in jobs]

    # ------------------------------------------------------------------ persistent serving
    def serve(self, stop_event: threading.Event, poll_interval: float = 0.25) -> None:
        """T06 carry-over #1: a persistent worker loop with real concurrency -- a thread
        pool per lane, sized to that lane's limit, so `lanes={"remote": 8}` actually runs up
        to 8 jobs in that lane at once instead of `run_once()`'s one-at-a-time picking.

        Calls `recover_interrupted()` once, then loops picking + dispatching jobs until
        `stop_event` is set. On shutdown every job still in flight is cancelled (its worker
        subprocess killed via `workers.runner.run`'s own `cancel` support) and, through the
        ordinary `_finish_job` INTERRUPTED path, lands as `interrupted` in the queue rather
        than being left stuck `running` -- a restart's `recover_interrupted()` would also
        catch a harder kill (SIGKILL), but a clean `stop_event` shutdown does not need to
        wait for that: it happens immediately, here.
        """
        self.recover_interrupted()
        pools: dict[str, ThreadPoolExecutor] = {
            lane: ThreadPoolExecutor(max_workers=max(1, limit)) for lane, limit in self.lanes.items()
        }
        cancels: dict[str, threading.Event] = {}
        lock = threading.Lock()

        def _dispatch(job: dict) -> None:
            cancel = threading.Event()
            with lock:
                cancels[job["id"]] = cancel
            try:
                self._run_job(job, cancel=cancel)
            finally:
                with lock:
                    cancels.pop(job["id"], None)

        try:
            while not stop_event.is_set():
                with db_mod.open_db(self.project_root) as con:
                    jobs = self._claim_jobs(con)
                for job in jobs:
                    lane = job["lane"]
                    pool = pools.setdefault(lane, ThreadPoolExecutor(max_workers=1))
                    pool.submit(_dispatch, job)
                stop_event.wait(poll_interval)
        finally:
            with lock:
                pending_cancels = list(cancels.values())
            for cancel in pending_cancels:
                cancel.set()
            for pool in pools.values():
                pool.shutdown(wait=True)

    def cancel_job(self, job_id: str) -> bool:
        return cancel_job(self.project_root, job_id, now=self.now)

    def _node_resources(self, node_id: str) -> tuple[str, ...]:
        node = self.workflow.node(node_id)
        return self.registry.get(node.type_id).resources

    def _run_job(self, job: dict, cancel: Optional[threading.Event] = None) -> None:
        cmd = json.loads(job["cmd_json"])
        seq_lock = threading.Lock()
        seq = 0
        job_id = job["id"]

        def on_event(ev: dict) -> None:
            nonlocal seq
            with db_mod.open_db(self.project_root) as con:
                with seq_lock:
                    this_seq = seq
                    seq += 1
                con.execute(
                    "INSERT INTO event (job_id, seq, kind, json, at) VALUES (?,?,?,?,?)",
                    (job_id, this_seq, ev.get("kind", ""), json.dumps(ev, default=str), self.now()),
                )
                con.commit()

        resources = self._node_resources(job["node_id"])

        def _run() -> runner_mod.RunResult:
            return self.run_fn(cmd, cwd=self._cwd(), on_event=on_event, cancel=cancel)

        result = self._with_resource_locks(resources, _run)
        self._finish_job(job, result)

    def _with_resource_locks(self, resources: tuple[str, ...], fn: Callable[[], runner_mod.RunResult]) -> runner_mod.RunResult:
        """Hold every declared resource's cross-process flock (T06 carry-over #3) around
        `fn`, nested in a fixed (sorted) order so two jobs that both need several of the
        same resources can never deadlock against each other."""
        if not resources:
            return fn()

        def _nested(remaining: list[str]) -> runner_mod.RunResult:
            if not remaining:
                return fn()
            with resource_lock(self.project_root, remaining[0]):
                return _nested(remaining[1:])

        return _nested(sorted(resources))

    # ------------------------------------------------------------------ finishing a job
    def _finish_job(self, job: dict, result: runner_mod.RunResult) -> None:
        node = self.workflow.node(job["node_id"])
        node_type = self.registry.get(node.type_id)
        now = self.now()
        state = job["state"]
        not_before: Optional[float] = None
        summary = ""

        # T31: count the spend first. A cost in a unit the budget doesn't count fails the job
        # (that amount is never added); a job that failed after a paid call still counts it.
        cost_problem = None
        if result.outcome == runner_mod.OK:
            cost_problem = budget_mod.record_cost(self.project_root, job, result.cost_total)
        elif result.cost_total:
            budget_mod.record_cost(self.project_root, job, result.cost_total, charge_estimate=False)
        if cost_problem:
            state, summary = "failed", f"the worker's cost could not be counted: {cost_problem}"
            artifacts.mark_failed(self.project_root, node_type.id, job["input_hash"], summary)
        elif result.outcome == runner_mod.OK:
            artifacts.finalize_success(
                self.project_root, node_type.id, job["node_id"], job["input_hash"],
                result, self._cwd(), json.loads(job["cmd_json"]),
            )
            state, summary = "ok", "completed"
        elif result.outcome == runner_mod.RETRY_LATER:
            not_before = self._retry_at(result.retry_at, now)
            state = "retry_later"
            summary = f"provider limit (cause: provider-limit); retrying after {not_before}"
        elif result.outcome == runner_mod.NEEDS_HUMAN:
            state, summary = "needs_human", "exited needs-human (cause: needs-human)"
        elif result.outcome == runner_mod.INTERRUPTED:
            state, summary = "interrupted", "cancelled or timed out (cause: interrupted)"
        else:
            state = "failed"
            summary = self._failure_summary(result)
            artifacts.mark_failed(self.project_root, node_type.id, job["input_hash"], summary)

        with db_mod.open_db(self.project_root) as con:
            con.execute(
                "UPDATE job SET state=?, finished_at=?, not_before=?, summary=? WHERE id=?",
                (state, now, not_before, summary, job["id"]),
            )
            con.commit()

        if state == "ok":
            self._enqueue_ready(self._descendant_targets(job["node_id"]), source_job=job)

    @staticmethod
    def _retry_at(retry_at: Optional[str], now: float) -> float:
        if not retry_at:
            return now + DEFAULT_RETRY_SECONDS
        try:
            return float(retry_at)
        except (TypeError, ValueError):
            return now + DEFAULT_RETRY_SECONDS

    @staticmethod
    def _failure_summary(result: runner_mod.RunResult) -> str:
        # T37: a worker's own failure detail (e.g. asset.verify's one-sentence causes) is what the card shows.
        detail = next((e.get("detail") for e in reversed(result.events) if e.get("kind") == "result" and e.get("ok") is False), None)
        if detail:
            return str(detail)
        cause = f"exit-{result.exit_code}" if result.exit_code is not None else "no-exit"
        last_line = result.tail.splitlines()[-1] if result.tail else "no output"
        return f"the worker failed (cause: {cause}): {last_line}"

    # ------------------------------------------------------------------ auto-continuation
    def _descendant_targets(self, finished_node_id: str) -> list[str]:
        hashes = compute_hashes(self.workflow, self.registry)
        states = compute_states(self.workflow, self.registry, self.project_root, hashes=hashes)
        candidates = plan_fn(self.workflow, self.registry, states, from_node=finished_node_id)
        return [nid for nid in candidates.runnable if nid != finished_node_id]

    def _effective_authorization(self, source_job: Optional[dict], resume: bool = False) -> Optional[Authorization]:
        """The authorisation to enqueue `node_ids` with. Prefers the in-memory one this
        Executor was built with; falls back to the persisted authorisation that named
        `source_job` (T06 carry-over #2 -- a process restarted with no Authorization object
        at all can still act on it, because the authorisation itself is durable, not process
        state). `resume=True` (recovering the exact same node an interrupted job already
        covered) reuses that authorisation unconditionally; auto-continuation onto *new*
        downstream nodes additionally requires `covers_downstream=True` on it."""
        if self.authorization is not None:
            return self.authorization
        if source_job is None:
            return None
        # The job's row as it is now, not as claimed: a confirmed click can attach its
        # authorisation to a free step that is already running (`enqueue`'s join path).
        persisted = authorisation_mod.load_for_job(self.project_root, source_job["id"])
        if persisted is None:
            return None
        if resume or persisted.covers_downstream:
            return persisted
        return None

    def _enqueue_ready(
        self, node_ids: list[str], source_job: Optional[dict] = None, resume: bool = False,
    ) -> list[str]:
        if not node_ids:
            return []
        hashes = compute_hashes(self.workflow, self.registry)
        states = compute_states(self.workflow, self.registry, self.project_root, hashes=hashes)
        ready = [nid for nid in node_ids if states.get(nid) == NodeState.READY]
        if not ready:
            return []
        authorization = self._effective_authorization(source_job, resume=resume)
        # Spending nodes only get auto-enqueued if an authorisation already covers them;
        # otherwise they stay `ready`, waiting on a fresh authorisation (T05 spec: "spending
        # ones wait unless the batch authorisation covered them").
        allowed = [
            nid for nid in ready
            if not self.registry.get(self.workflow.node(nid).type_id).spends
            or (authorization is not None and authorization.covers(nid))
        ]
        if not allowed:
            return []
        restricted = Plan(
            runnable=allowed,
            needs_authorization=[nid for nid in allowed
                                  if self.registry.get(self.workflow.node(nid).type_id).spends],
            blocked_on_human=[],
            estimated_cost=[],
        )
        try:
            return enqueue(
                self.project_root, self.workflow, self.registry, hashes, restricted,
                self.cmd_for, authorization,
            )
        except SpendNotAuthorized as exc:
            # T31: the budget refused (e.g. past the headroom the person saw): those nodes stay
            # `ready` for a fresh authorisation, free ones continue, nothing escapes the thread.
            free = [nid for nid in allowed if nid not in restricted.needs_authorization]
            auth = None if isinstance(exc, UnknownBudget) else authorization
            return enqueue(self.project_root, self.workflow, self.registry, hashes,
                           Plan(runnable=free), self.cmd_for, auth) if free else []


def cancel_job(project_root: str | Path, job_id: str, now: Callable[[], float] = time.time) -> bool:
    """Cancel a job that hasn't started running yet (queued/retry_later/needs_human), with
    no need for a full `Executor` (a workflow/registry/cmd_for) -- callers like the CLI's
    `queue cancel` only have a job id. A `running` job belongs to some `serve()` call's
    thread pool -- possibly in another process -- and can only be stopped by that call's own
    `stop_event`/shutdown, or by killing the process and letting `recover_interrupted()`
    mark it `interrupted` on the next restart. Returns whether a job was actually
    cancelled."""
    with db_mod.open_db(project_root) as con:
        row = con.execute("SELECT state FROM job WHERE id=?", (job_id,)).fetchone()
        if row is None or row["state"] not in ("queued", "retry_later", "needs_human"):
            return False
        con.execute(
            "UPDATE job SET state='cancelled', finished_at=?, summary='cancelled by request' "
            "WHERE id=?",
            (now(), job_id),
        )
        con.commit()
    return True


__all__ = ["Executor", "DEFAULT_LANES", "DEFAULT_RETRY_SECONDS", "cancel_job"]
