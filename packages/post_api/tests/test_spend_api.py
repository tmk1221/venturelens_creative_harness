"""T31 over HTTP: `run` never creates a budget (unknown -> 409, a `cap` in the body is
rejected), one click's authorisation names its node ids, an estimate past headroom is a 402
that persists nothing, `GET /api/doctor` says fake|real, and `scripts/dev.sh`'s mode switch
is fake unless `POST3_REAL=1`."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from post_core.queue import db as db_mod

REPO_ROOT = Path(__file__).resolve().parents[3]


def _spend_workflow(client, pid, n=1) -> str:
    nodes = [{"id": f"g{i}", "type_id": "fake.api_spend", "params": {"text": str(i), "cmd": ["true"]}} for i in range(n)]
    r = client.post(f"/api/projects/{pid}/workflows", json={"recipe": "t31", "graph": {"nodes": nodes, "edges": []}})
    assert r.status_code == 200, r.text
    return r.json()["workflow_id"]


def _rows(root, table) -> list[dict]:
    with db_mod.open_db(root) as con:
        return [dict(r) for r in con.execute(f"SELECT * FROM {table}").fetchall()]


def test_run_never_creates_a_budget(client, project):
    pid, root = project["id"], project["root"]
    wf = _spend_workflow(client, pid)

    r = client.post(f"/api/projects/{pid}/workflows/{wf}/run", json={"budget": "click-1", "by": "t"})
    assert r.status_code == 409, r.text
    assert r.json()["reason"] == "unknown_budget"
    assert "unknown budget 'click-1'" in r.json()["error"]

    # the old implicit-budget shape is rejected outright, not silently honoured
    r = client.post(f"/api/projects/{pid}/workflows/{wf}/run", json={"budget": "click-1", "cap": 1000, "unit": "usd"})
    assert r.status_code == 422, r.text

    assert client.get(f"/api/projects/{pid}/budgets/click-1").status_code == 404
    assert _rows(root, "budget") == [] and _rows(root, "authorisation") == [] and _rows(root, "job") == []


def test_budget_put_requires_a_unit(client, project):
    r = client.put(f"/api/projects/{project['id']}/budgets/b", json={"cap": 5.0})
    assert r.status_code == 422, r.text


def test_one_click_budget_and_authorisation_name_exactly_the_shown_nodes(client, project):
    pid, root = project["id"], project["root"]
    wf = _spend_workflow(client, pid, n=2)
    plan = client.get(f"/api/projects/{pid}/workflows/{wf}/plan").json()["plan"]
    assert [(s["node_id"], s["amount"], s["unit"]) for s in plan["spends"]] == [("g0", 1.5, "usd"), ("g1", 1.5, "usd")]

    r = client.put(f"/api/projects/{pid}/budgets/{wf}-1", json={"cap": 3.0, "unit": "usd"})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/projects/{pid}/workflows/{wf}/run", json={
        "budget": f"{wf}-1", "by": "web", "node_ids": ["g0", "g1"], "covers_downstream": True,
    })
    assert r.status_code == 200, r.text
    assert len(r.json()["job_ids"]) == 2
    (auth,) = _rows(root, "authorisation")
    assert json.loads(auth["scope"])["node_ids"] == ["g0", "g1"]
    assert auth["budget_id"] == f"{wf}-1" and auth["covers_downstream"] == 1


def test_estimate_past_headroom_is_refused_and_persists_nothing(client, project):
    pid, root = project["id"], project["root"]
    wf = _spend_workflow(client, pid, n=2)
    assert client.put(f"/api/projects/{pid}/budgets/small", json={"cap": 2.0, "unit": "usd"}).status_code == 200
    r = client.post(f"/api/projects/{pid}/workflows/{wf}/run", json={"budget": "small", "by": "t"})
    assert r.status_code == 402, r.text
    assert r.json()["reason"] == "over_headroom"
    assert _rows(root, "authorisation") == [] and _rows(root, "job") == []


def test_unit_mismatch_is_refused(client, project):
    pid = project["id"]
    wf = _spend_workflow(client, pid)
    assert client.put(f"/api/projects/{pid}/budgets/cr", json={"cap": 50.0, "unit": "credits"}).status_code == 200
    r = client.post(f"/api/projects/{pid}/workflows/{wf}/run", json={"budget": "cr", "by": "t"})
    assert r.status_code == 402, r.text
    assert r.json()["reason"] == "unit_mismatch"


def test_doctor_reports_providers_mode(client, monkeypatch):
    monkeypatch.setenv("POST3_FAKE_PROVIDERS", "1")
    assert client.get("/api/doctor").json()["providers"] == "fake"
    monkeypatch.delenv("POST3_FAKE_PROVIDERS")
    body = client.get("/api/doctor").json()
    assert body["providers"] == "real"
    assert all(isinstance(v, bool) for v in body["keys"].values())  # still booleans only


def _dev_mode(**env) -> str:
    script = f'source "{REPO_ROOT}/scripts/providers_mode.sh"; echo "$POST3_PROVIDERS:${{POST3_FAKE_PROVIDERS:-unset}}"'
    base = {k: v for k, v in os.environ.items() if k not in ("POST3_REAL", "POST3_FAKE_PROVIDERS")}
    out = subprocess.run(["bash", "-c", script], env={**base, **env}, check=True, capture_output=True, text=True)
    return out.stdout.strip()


def test_dev_script_is_fake_unless_post3_real_is_set():
    assert _dev_mode() == "fake:1"
    assert _dev_mode(POST3_REAL="0") == "fake:1"
    assert _dev_mode(POST3_REAL="1") == "real:unset"
    assert _dev_mode(POST3_REAL="1", POST3_FAKE_PROVIDERS="1") == "real:unset"  # explicit real wins
    assert "providers_mode.sh" in (REPO_ROOT / "scripts" / "dev.sh").read_text()
