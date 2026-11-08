"""T06 acceptance test: drive `post` via subprocess, end to end, against fake node
types/workers, on a temp project. Mirrors the spec's exact flow: init -> add source (lavfi
media) -> import transcript -> new cut -> two ops -> undo -> workflow plan shows cost -> run
refused without authorisation -> run with budget -> states done -> approve -> queue survives
a killed serve and resumes.
"""
from __future__ import annotations

import json
import os
import signal
import sys
import textwrap
import time


def test_cli_end_to_end(tmp_path, run_cli, popen_cli, lavfi_clip, ok_worker_script):
    root = tmp_path / "project"

    # init
    r = run_cli("init", str(root), "--name", "e2e")
    assert r["exit_code"] == 0, r
    assert r["root"] == str(root.resolve())

    # add source (lavfi media)
    r = run_cli("source", "add", "--root", str(root), "--path", str(lavfi_clip), "--role", "a_roll")
    assert r["exit_code"] == 0, r
    shoot_id = r["shoot_id"]
    source_id = r["source_id"]
    sync_group_id = r["sync_group_id"]
    assert r["probe"]["content_fingerprint"]

    # import transcript
    transcript_path = tmp_path / "t.json"
    transcript_path.write_text(json.dumps([
        {"text": "hello", "start": 0.0, "end": 0.2},
        {"text": "there", "start": 0.2, "end": 0.4},
        {"text": "world", "start": 0.4, "end": 0.6},
    ]))
    r = run_cli(
        "ingest", "import-transcript", "--root", str(root), "--shoot", shoot_id,
        "--sync-group", sync_group_id, "--path", str(transcript_path), "--format", "json",
    )
    assert r["exit_code"] == 0, r
    transcript_id = r["transcript_id"]
    assert r["words"] == 3

    # new cut
    r = run_cli(
        "cut", "new", "--root", str(root), "--transcript", transcript_id,
        "--angle", source_id, "--aspect", "16:9",
    )
    assert r["exit_code"] == 0, r
    cut_id = r["cut_id"]

    r = run_cli("cut", "show", "--root", str(root), "--cut", cut_id)
    words = r["cut"]["passages"][0]
    first_word_id = words["start_word_id"]

    # two ops: set_trim then delete a word range, back to back
    r = run_cli(
        "cut", "op", "set_trim", "--root", str(root), "--cut", cut_id,
        "--args", json.dumps({"passage_id": r["cut"]["passages"][0]["id"], "head": 0.05, "tail": 0.0}),
    )
    assert r["exit_code"] == 0, r

    r = run_cli(
        "cut", "op", "delete_words", "--root", str(root), "--cut", cut_id,
        "--args", json.dumps(
            {"sync_group_id": sync_group_id, "start_word_id": first_word_id, "end_word_id": first_word_id}
        ),
    )
    assert r["exit_code"] == 0, r

    r = run_cli("cut", "show", "--root", str(root), "--cut", cut_id)
    assert all(p["start_word_id"] != first_word_id for p in r["cut"]["passages"])

    # undo (undoes the delete_words op)
    r = run_cli("cut", "undo", "--root", str(root), "--cut", cut_id)
    assert r["exit_code"] == 0, r
    r = run_cli("cut", "show", "--root", str(root), "--cut", cut_id)
    assert any(p["start_word_id"] == first_word_id for p in r["cut"]["passages"])

    # workflow new with a fake spending node type, plan shows cost
    worker_cmd = ok_worker_script("spend_worker", "spend_out.bin")
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps({
        "nodes": [{"id": "g1", "type_id": "fake.cli_spend", "params": {"text": "x", "cmd": worker_cmd}}],
        "edges": [],
    }))
    r = run_cli("workflow", "new", "--root", str(root), "--recipe", "e2e-demo", "--graph", str(graph_path))
    assert r["exit_code"] == 0, r
    workflow_id = r["workflow_id"]

    r = run_cli("workflow", "plan", "--root", str(root), "--workflow", workflow_id)
    assert r["exit_code"] == 0, r
    assert r["plan"]["runnable"] == ["g1"]
    assert r["plan"]["needs_authorization"] == ["g1"]
    assert r["plan"]["estimated_cost"] == [{"amount": 2.5, "unit": "usd", "provider": "fake-cli-provider"}]

    # run refused without authorisation
    r = run_cli("run", "--root", str(root), "--workflow", workflow_id)
    assert r["exit_code"] != 0
    assert "error" in r

    # T31: naming a budget that was never set is refused, and `run` never creates one
    r = run_cli("run", "--root", str(root), "--workflow", workflow_id, "--budget", "b1", "--by", "travis")
    assert r["exit_code"] != 0
    assert "unknown budget" in r["error"]
    r = run_cli("budget", "show", "--root", str(root), "--id", "b1")
    assert r["exit_code"] != 0

    # run with an explicitly created budget
    r = run_cli("budget", "set", "--root", str(root), "--id", "b1", "--cap", "10", "--unit", "usd")
    assert r["exit_code"] == 0, r
    r = run_cli("run", "--root", str(root), "--workflow", workflow_id, "--budget", "b1", "--by", "travis")
    assert r["exit_code"] == 0, r
    job_ids = r["job_ids"]
    assert len(job_ids) == 1

    r = run_cli("queue", "serve", "--root", str(root), "--workflow", workflow_id, "--once")
    assert r["exit_code"] == 0, r
    assert r["ran"] == job_ids

    # states done
    r = run_cli("workflow", "states", "--root", str(root), "--workflow", workflow_id)
    assert r["exit_code"] == 0, r
    assert r["states"] == {"g1": "done"}

    # approve
    r = run_cli("approve", "--root", str(root), "some-content-hash", "--by", "travis")
    assert r["exit_code"] == 0, r
    assert r["content_hash"] == "some-content-hash"

    # queue survives a killed serve and resumes
    slow_root = tmp_path / "project_slow"
    r = run_cli("init", str(slow_root))
    assert r["exit_code"] == 0, r
    slow_script = tmp_path / "slow_worker.py"
    slow_out = tmp_path / "slow_out.bin"
    slow_script.write_text(textwrap.dedent(f"""
        import hashlib, json, time
        time.sleep(3)
        out = {str(slow_out)!r}
        open(out, "w").write("done")
        sha = hashlib.sha256(open(out, "rb").read()).hexdigest()
        print("##POST " + json.dumps({{"kind": "artifact", "path": out, "role": "output", "sha256": sha}}), flush=True)
        print("##POST " + json.dumps({{"kind": "result", "ok": True, "detail": "done"}}), flush=True)
    """))
    slow_graph = tmp_path / "slow_graph.json"
    slow_graph.write_text(json.dumps({
        "nodes": [{"id": "g1", "type_id": "fake.cli_spend",
                   "params": {"text": "slow", "cmd": [sys.executable, str(slow_script)]}}],
        "edges": [],
    }))
    r = run_cli("workflow", "new", "--root", str(slow_root), "--recipe", "slow-demo", "--graph", str(slow_graph))
    assert r["exit_code"] == 0, r
    slow_workflow_id = r["workflow_id"]
    r = run_cli("budget", "set", "--root", str(slow_root), "--id", "b1", "--cap", "10", "--unit", "usd")
    assert r["exit_code"] == 0, r
    r = run_cli("run", "--root", str(slow_root), "--workflow", slow_workflow_id, "--budget", "b1", "--by", "travis")
    assert r["exit_code"] == 0, r

    proc = popen_cli("queue", "serve", "--root", str(slow_root), "--workflow", slow_workflow_id)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not slow_out.parent.exists():
        time.sleep(0.05)
    time.sleep(0.8)  # let the worker subprocess actually start running
    os.kill(proc.pid, signal.SIGKILL)
    proc.wait(timeout=10)

    r = run_cli("queue", "list", "--root", str(slow_root))
    assert r["exit_code"] == 0, r
    assert any(j["state"] == "running" for j in r["jobs"])

    r = run_cli("queue", "serve", "--root", str(slow_root), "--workflow", slow_workflow_id, "--once")
    assert r["exit_code"] == 0, r

    r = run_cli("queue", "list", "--root", str(slow_root))
    states = {j["node_id"]: j["state"] for j in r["jobs"]}
    assert "ok" in states.values() or any(
        j["node_id"] == "g1" and j["state"] == "ok" for j in r["jobs"]
    )


def test_doctor_never_leaks_a_secret_value(tmp_path, run_cli, fake_env_file):
    real_secret = "sk-super-secret-do-not-print-1234567890"
    fake_env_file.write_text(f"DEEPGRAM_API_KEY={real_secret}\n")
    root = tmp_path / "project"
    r = run_cli("init", str(root))
    assert r["exit_code"] == 0, r

    r = run_cli("doctor", "--root", str(root))
    assert r["exit_code"] == 0, r
    assert r["keys"]["DEEPGRAM_API_KEY"] is True
    dumped = json.dumps(r)
    assert real_secret not in dumped
