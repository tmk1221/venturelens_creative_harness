"""T35: transcription is a queued, authorised spend, like any other (T31).

One workflow per sync group (`transcribe-<sync_group_id>`) holding one `transcript.transcribe`
node, lane `remote`, `spends=True`. Its estimate is the audio proxy's minutes x the configured
Deepgram rate in `usd`, rounded up to the cent -- the amount the person is shown is the cap of
the one budget their click creates, and the amount the job records. `enqueue_transcription`
goes through `queue.enqueue`, so no budget / an unknown budget / an estimate past the budget's
headroom is refused in the core before anything is queued.

The worker (`job_worker.py`) uploads the group's audio proxy -- never the camera file -- and
writes the transcript into the store linked to the group (`link.add_transcript`).
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict

from ...cli.config import load_project_config
from ...graph.hashing import compute_hashes
from ...graph.plan import plan as plan_fn
from ...graph.registry import NodeRegistry, register_builtins
from ...graph.state import NodeState, artifact_dir, compute_states
from ...graph.types import Cost, NodeType, OutputSpec
from ...graph.workflow import Node, Workflow
from ...ingest.audio_proxy import is_valid_audio_proxy
from ...ingest.probe import ffprobe_json
from ...model.shoot import Shoot, SyncGroup, clean_audio_source
from ...queue import db as db_mod
from ...queue.budget import check_spend
from ...queue.enqueue import Authorization, SpendNotAuthorized, enqueue
from ...store import store as store_module
from ...store.errors import NotFound
from ...store.paths import store_root
from . import base
from .link import latest_for_group

TYPE_ID = "transcript.transcribe"
NODE_ID = "transcribe"
WORKFLOW_PREFIX = "transcribe-"
PROVIDERS = ("deepgram",)
RATE_KEY = "deepgram_usd_per_minute"
# Deepgram's pay-as-you-go list price as understood when this was written: nova-3 pre-recorded
# $0.0043/min + the diarization add-on $0.0020/min. UNVERIFIED -- check deepgram.com/pricing
# before the first real run; a project overrides it with `deepgram_usd_per_minute` in
# `.post3/config.json`.
DEFAULT_USD_PER_MINUTE = 0.0063
TERMINAL_STATES = ("ok", "failed", "cancelled", "interrupted", "needs_human")


class TranscribeError(ValueError):
    """A plain-sentence refusal before anything is queued or spent."""


class NoAudioProxy(TranscribeError):
    pass


class AlreadyTranscribed(TranscribeError):
    pass


class TranscribeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "deepgram"
    audio_path: str
    fingerprint: str
    shoot_id: str
    sync_group_id: str
    duration_seconds: float
    usd_per_minute: float


def estimate_usd(duration_seconds: float, usd_per_minute: float) -> float:
    """Minutes x rate, rounded UP to the cent (the shown estimate is the budget's cap)."""
    return math.ceil(round(duration_seconds / 60.0 * usd_per_minute * 100, 6)) / 100


def _estimate(params: TranscribeParams) -> Optional[Cost]:
    if params.duration_seconds <= 0 or params.usd_per_minute <= 0:
        return None
    return Cost(amount=estimate_usd(params.duration_seconds, params.usd_per_minute), unit="usd",
                provider=params.provider)


TRANSCRIBE = NodeType(
    id=TYPE_ID, kind="compute", outputs=(OutputSpec(name="words", type="words"),),
    params_schema=TranscribeParams, spends=True, lane="remote", estimate_cost=_estimate,
)


def register(registry: NodeRegistry) -> None:
    registry.register(TRANSCRIBE, replace=True)


def registry() -> NodeRegistry:
    reg = NodeRegistry()
    register_builtins(reg)
    register(reg)
    return reg


def workflow_id_for(sync_group_id: str) -> str:
    return f"{WORKFLOW_PREFIX}{sync_group_id}"


def usd_per_minute(root: str | Path) -> float:
    return float(load_project_config(root).get(RATE_KEY, DEFAULT_USD_PER_MINUTE))


def audio_duration(path: str | Path) -> float:
    return float((ffprobe_json(path).get("format") or {}).get("duration") or 0.0)


def find_group(root: str | Path, sync_group_id: str) -> tuple[Shoot, SyncGroup]:
    shoots = store_root(root) / "shoots"
    for f in sorted(shoots.glob("*.json")) if shoots.is_dir() else []:
        shoot, _rev = store_module.read(root, "shoot", f.stem)
        group = next((g for g in shoot.sync_groups if g.id == sync_group_id), None)
        if group is not None:
            return shoot, group
    raise TranscribeError(f"This project has no recording in sync group {sync_group_id!r}.")


def prepare(root: str | Path, sync_group_id: str, provider: str = "deepgram") -> TranscribeParams:
    """The job's params, or a refusal: an unknown/unbuilt provider, or no audio proxy yet."""
    if provider == "local":
        raise TranscribeError(base.LOCAL_UNAVAILABLE)
    if provider not in PROVIDERS:
        raise TranscribeError(f"Unknown transcript provider {provider!r}; the paid one is 'deepgram'. "
                              f"{base.LOCAL_UNAVAILABLE}")
    shoot, group = find_group(root, sync_group_id)
    source = clean_audio_source(shoot, group)
    audio = source.audio_proxy_path
    if not audio or not is_valid_audio_proxy(audio):
        name = Path(source.path).name if source.path else source.id
        raise NoAudioProxy(f"{name} has no audio proxy yet, so there is nothing to transcribe: run ingest "
                           f"audio first (`post ingest audio --shoot {shoot.id} --source-id {source.id}`).")
    return TranscribeParams(
        provider=provider, audio_path=str(audio), fingerprint=source.content_fingerprint, shoot_id=shoot.id,
        sync_group_id=group.id, duration_seconds=audio_duration(audio), usd_per_minute=usd_per_minute(root),
    )


def estimate(root: str | Path, sync_group_id: str, provider: str = "deepgram") -> dict:
    params = prepare(root, sync_group_id, provider)
    cost = _estimate(params)
    return {
        "sync_group_id": sync_group_id, "provider": provider, "audio_path": params.audio_path,
        "minutes": round(params.duration_seconds / 60.0, 2), "usd_per_minute": params.usd_per_minute,
        "amount": cost.amount if cost else None, "unit": "usd",
    }


def _save_workflow(root: str | Path, params: TranscribeParams) -> Workflow:
    workflow_id = workflow_id_for(params.sync_group_id)
    node = Node(id=NODE_ID, type_id=TYPE_ID, params=params.model_dump())
    try:
        existing, revision = store_module.read(root, "workflow", workflow_id)
    except NotFound:
        existing, revision = None, 0
    if existing is not None and existing.nodes == [node]:
        return existing
    workflow = Workflow(id=workflow_id, recipe_id="transcribe", nodes=[node])
    store_module.write(root, "workflow", workflow, expected_rev=revision)
    return workflow


def _clear_failure(root: str | Path, input_hash: str) -> None:
    """A failed attempt leaves `failed.json`, which keeps the node out of every plan. A new
    confirmed click is an explicit retry: keep the old marker as history and plan again."""
    marker = artifact_dir(root, TYPE_ID, input_hash) / "failed.json"
    if marker.is_file():
        marker.rename(marker.with_name(f"failed-{int(time.time() * 1000)}.json"))


def enqueue_transcription(
    root: str | Path, sync_group_id: str, *, budget_id: Optional[str], by: str, provider: str = "deepgram",
) -> dict:
    """Queue one transcription against an existing budget. Refuses (before writing a job)
    when the group already has a transcript, has no audio proxy, or the spend isn't covered."""
    params = prepare(root, sync_group_id, provider)
    shoot, _group = find_group(root, sync_group_id)
    if latest_for_group(root, shoot, sync_group_id) is not None:
        raise AlreadyTranscribed("This recording already has a transcript.")
    cost = _estimate(params)
    if not budget_id:
        raise SpendNotAuthorized(
            f"Transcribing costs about ${cost.amount if cost else '?'} (Deepgram), so it needs a budget: "
            "create one for that amount, then name it."
        )
    with db_mod.open_db(root) as con:  # refuse a bad budget before writing anything (enqueue re-checks)
        check_spend(con, budget_id, {NODE_ID: cost})
    workflow = _save_workflow(root, params)
    reg = registry()
    hashes = compute_hashes(workflow, reg)
    if compute_states(workflow, reg, root, hashes=hashes).get(NODE_ID) == NodeState.FAILED:
        _clear_failure(root, hashes[NODE_ID])
    states = compute_states(workflow, reg, root, hashes=hashes)
    plan = plan_fn(workflow, reg, states, targets=[NODE_ID])
    if NODE_ID not in plan.runnable:
        state = getattr(states.get(NODE_ID), "value", "unknown")
        raise AlreadyTranscribed(f"This recording's transcription already finished (state: {state}).")
    authorization = Authorization(budget_id=budget_id, by=by, node_ids=frozenset({NODE_ID}), workflow_id=workflow.id)
    job_ids = enqueue(root, workflow, reg, hashes, plan, cmd_for=lambda nid: build_cmd(workflow, nid),
                      authorization=authorization)
    return {"job_id": job_ids[0], "workflow_id": workflow.id, "amount": cost.amount if cost else None, "unit": "usd"}


def build_cmd(workflow: Workflow, node_id: str) -> list[str]:
    """The worker argv. Runs with the project root as its cwd (the executor's default)."""
    params = TranscribeParams.model_validate(workflow.node(node_id).params)
    out_dir = Path(".post3") / "tmp" / workflow.id
    return [
        sys.executable, "-m", "post_core.ingest.transcribe.job_worker",
        "--project-root", ".", "--provider", params.provider, "--audio", params.audio_path,
        "--shoot-id", params.shoot_id, "--sync-group-id", params.sync_group_id,
        "--fingerprint", params.fingerprint, "--duration-seconds", repr(params.duration_seconds),
        "--usd-per-minute", repr(params.usd_per_minute), "--out-dir", str(out_dir),
    ]


def job_row(root: str | Path, job_id: str) -> Optional[dict]:
    with db_mod.open_db(root) as con:
        row = con.execute("SELECT * FROM job WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row is not None else None


def run_job(root: str | Path, sync_group_id: str, job_id: str, *, poll: float = 0.5, timeout: float = 3600.0) -> dict:
    """Drive this group's queue in-process until `job_id` ends (the CLI's path; the API's
    background runtime picks the same job up on its own). Returns the job row."""
    from ...queue.executor import Executor  # local: the executor pulls in the worker runner

    workflow, _rev = store_module.read(root, "workflow", workflow_id_for(sync_group_id))
    executor = Executor(project_root=root, workflow=workflow, registry=registry(),
                        cmd_for=lambda nid: build_cmd(workflow, nid))
    deadline = time.monotonic() + timeout
    while True:
        executor.run_once()
        row = job_row(root, job_id) or {}
        if row.get("state") in TERMINAL_STATES or time.monotonic() > deadline:
            return row
        time.sleep(poll)  # another process (the API) is running it: wait for its outcome


def latest_job(root: str | Path, sync_group_id: str) -> Optional[dict]:
    with db_mod.open_db(root) as con:
        row = con.execute("SELECT * FROM job WHERE workflow_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                          (workflow_id_for(sync_group_id),)).fetchone()
    return dict(row) if row is not None else None


__all__ = [
    "AlreadyTranscribed", "DEFAULT_USD_PER_MINUTE", "NODE_ID", "NoAudioProxy", "TERMINAL_STATES", "TRANSCRIBE",
    "TYPE_ID", "TranscribeError", "TranscribeParams", "build_cmd", "enqueue_transcription", "estimate",
    "estimate_usd", "find_group", "job_row", "latest_job", "prepare", "register", "registry", "run_job", "workflow_id_for",
]
