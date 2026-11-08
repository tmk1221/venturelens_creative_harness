from __future__ import annotations

import hashlib
import os
import stat
import sys
import threading
import time
from pathlib import Path

import pytest

from post_core.workers import contract, runner

PY = sys.executable


def write_worker(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_success_with_verified_artifact(tmp_path):
    out_file = tmp_path / "out.txt"
    worker = write_worker(tmp_path, "ok_worker.py", f"""
import json
out = {str(out_file)!r}
with open(out, "w") as f:
    f.write("hello")
import hashlib
sha = hashlib.sha256(open(out, "rb").read()).hexdigest()
print("##POST " + json.dumps({{"kind": "step", "label": "writing"}}), flush=True)
print("##POST " + json.dumps({{"kind": "artifact", "path": out, "role": "output", "sha256": sha}}), flush=True)
print("##POST " + json.dumps({{"kind": "result", "ok": True, "detail": "done"}}), flush=True)
""")
    events = []
    result = runner.run([PY, str(worker)], cwd=tmp_path, on_event=events.append)
    assert result.outcome == runner.OK
    assert result.ok is True
    assert result.exit_code == 0
    assert len(result.artifacts) == 1
    assert any(e["kind"] == "step" for e in events)


def test_zero_exit_without_result_is_failed(tmp_path):
    worker = write_worker(tmp_path, "silent_worker.py", "print('did something, but no result event')\n")
    result = runner.run([PY, str(worker)], cwd=tmp_path)
    assert result.exit_code == 0
    assert result.outcome == runner.FAILED


def test_missing_declared_artifact_is_failed(tmp_path):
    missing = tmp_path / "never_written.bin"
    worker = write_worker(tmp_path, "missing_worker.py", f"""
import json
print("##POST " + json.dumps({{"kind": "artifact", "path": {str(missing)!r}, "role": "output", "sha256": "deadbeef"}}), flush=True)
print("##POST " + json.dumps({{"kind": "result", "ok": True}}), flush=True)
""")
    result = runner.run([PY, str(worker)], cwd=tmp_path)
    assert result.outcome == runner.FAILED
    assert result.exit_code == 0


def test_sha_mismatch_is_failed(tmp_path):
    out_file = tmp_path / "out.bin"
    worker = write_worker(tmp_path, "sha_worker.py", f"""
import json
with open({str(out_file)!r}, "w") as f:
    f.write("real content")
print("##POST " + json.dumps({{"kind": "artifact", "path": {str(out_file)!r}, "role": "output", "sha256": "0"*64}}), flush=True)
print("##POST " + json.dumps({{"kind": "result", "ok": True}}), flush=True)
""")
    result = runner.run([PY, str(worker)], cwd=tmp_path)
    assert result.outcome == runner.FAILED


def test_exit_3_reports_retry_later_with_retry_at(tmp_path):
    worker = write_worker(tmp_path, "retry_worker.py", """
import json, sys
print("##POST " + json.dumps({"kind": "result", "ok": False, "detail": "rate limited", "retry_at": "2026-09-22T00:00:00Z"}), flush=True)
sys.exit(3)
""")
    result = runner.run([PY, str(worker)], cwd=tmp_path)
    assert result.outcome == runner.RETRY_LATER
    assert result.exit_code == 3
    assert result.retry_at == "2026-09-22T00:00:00Z"


def test_exit_4_reports_needs_human(tmp_path):
    worker = write_worker(tmp_path, "human_worker.py", """
import sys
sys.exit(4)
""")
    result = runner.run([PY, str(worker)], cwd=tmp_path)
    assert result.outcome == runner.NEEDS_HUMAN
    assert result.exit_code == 4


def test_exit_1_is_failed(tmp_path):
    worker = write_worker(tmp_path, "fail_worker.py", "import sys\nsys.exit(1)\n")
    result = runner.run([PY, str(worker)], cwd=tmp_path)
    assert result.outcome == runner.FAILED
    assert result.exit_code == 1


def test_timeout_kills_children(tmp_path):
    pidfile = tmp_path / "child.pid"
    worker = write_worker(tmp_path, "spawn_worker.py", f"""
import subprocess, time
p = subprocess.Popen(["sleep", "50"])
with open({str(pidfile)!r}, "w") as f:
    f.write(str(p.pid))
time.sleep(50)
""")
    finalized = []
    result = runner.run([PY, str(worker)], cwd=tmp_path, timeout=1.0,
                         finalizer=lambda: finalized.append(True))
    assert result.outcome == runner.INTERRUPTED
    assert finalized == [True]
    child_pid = int(pidfile.read_text())
    time.sleep(0.3)  # let the SIGTERM/SIGKILL land
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


def test_cancel_interrupts_a_long_running_worker(tmp_path):
    worker = write_worker(tmp_path, "long_worker.py", "import time\ntime.sleep(30)\n")
    cancel = threading.Event()
    holder = {}

    def go():
        holder["result"] = runner.run([PY, str(worker)], cwd=tmp_path, cancel=cancel)

    t = threading.Thread(target=go)
    t.start()
    time.sleep(0.3)
    cancel.set()
    t.join(timeout=10)
    assert not t.is_alive()
    assert holder["result"].outcome == runner.INTERRUPTED


def test_finalizer_runs_on_every_path(tmp_path):
    calls = []

    ok_worker = write_worker(tmp_path, "ok2.py", """
import json
print("##POST " + json.dumps({"kind": "result", "ok": True}), flush=True)
""")
    fail_worker = write_worker(tmp_path, "fail2.py", "import sys\nsys.exit(1)\n")

    runner.run([PY, str(ok_worker)], cwd=tmp_path, finalizer=lambda: calls.append("ok"))
    runner.run([PY, str(fail_worker)], cwd=tmp_path, finalizer=lambda: calls.append("fail"))
    runner.run(["/no/such/binary-xyz"], cwd=tmp_path, finalizer=lambda: calls.append("launch_error"))

    assert calls == ["ok", "fail", "launch_error"]


def test_finalizer_exception_does_not_mask_result(tmp_path):
    ok_worker = write_worker(tmp_path, "ok3.py", """
import json
print("##POST " + json.dumps({"kind": "result", "ok": True}), flush=True)
""")

    def boom():
        raise RuntimeError("cleanup blew up")

    result = runner.run([PY, str(ok_worker)], cwd=tmp_path, finalizer=boom)
    assert result.outcome == runner.OK
    assert "cleanup blew up" in result.tail


def test_stalled_heartbeat_does_not_kill(tmp_path):
    worker = write_worker(tmp_path, "slow_worker.py", """
import json, time
time.sleep(0.4)
print("##POST " + json.dumps({"kind": "result", "ok": True}), flush=True)
""")
    stalled_events = []
    result = runner.run([PY, str(worker)], cwd=tmp_path, timeout=5.0, heartbeat=0.15,
                         on_event=lambda e: stalled_events.append(e) if e.get("kind") == "stalled" else None)
    assert result.outcome == runner.OK
    assert len(stalled_events) >= 1


def test_non_utf8_output_does_not_crash(tmp_path):
    worker = write_worker(tmp_path, "badbytes_worker.py", """
import sys, json
sys.stdout.buffer.write(b"garbled: \\xff\\xfe not utf8\\n")
sys.stdout.buffer.flush()
print("##POST " + json.dumps({"kind": "result", "ok": True}), flush=True)
""")
    result = runner.run([PY, str(worker)], cwd=tmp_path)
    assert result.outcome == runner.OK
    assert "garbled" in result.tail


def test_cost_events_are_totalled(tmp_path):
    worker = write_worker(tmp_path, "cost_worker.py", """
import json
print("##POST " + json.dumps({"kind": "cost", "amount": 1.5, "unit": "usd", "provider": "higgsfield"}), flush=True)
print("##POST " + json.dumps({"kind": "cost", "amount": 0.5, "unit": "usd", "provider": "higgsfield"}), flush=True)
print("##POST " + json.dumps({"kind": "result", "ok": True}), flush=True)
""")
    result = runner.run([PY, str(worker)], cwd=tmp_path)
    assert result.cost_total == {"usd": 2.0}
