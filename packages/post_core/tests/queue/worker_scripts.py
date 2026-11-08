"""Tiny real (subprocess) fake workers, one function per outcome, plus a manifest-writing
helper for pre-seeding a source node as done. Kept out of conftest.py so test modules can
import these plain functions directly (`from worker_scripts import ...`); this directory
deliberately has no `__init__.py` so it is never importable as a top-level `queue` package
that would shadow the stdlib `queue` module `workers/runner.py` depends on.
"""
from __future__ import annotations

import json
import stat
import sys
import textwrap
from pathlib import Path

PY = sys.executable


def write_manifest(project_root: Path, node_type_id: str, input_hash: str, **extra) -> Path:
    from post_core.graph.state import artifact_dir

    d = artifact_dir(project_root, node_type_id, input_hash)
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps({"outputs": [], "finished_at": 0.0, **extra}))
    return d


def write_ok_worker(
    dir_: Path, name: str, out_name: str = "out.bin", role: str = "output",
    cost: float = 1.5, unit: str = "usd",
) -> list[str]:
    """A worker that writes one artifact, reports `cost` `unit`, and succeeds. Returns the cmd."""
    out_path = dir_ / out_name
    script = dir_ / f"{name}.py"
    script.write_text(textwrap.dedent(f"""
        import hashlib, json
        out = {str(out_path)!r}
        with open(out, "w") as f:
            f.write("payload:{name}")
        sha = hashlib.sha256(open(out, "rb").read()).hexdigest()
        print("##POST " + json.dumps({{"kind": "cost", "amount": {cost!r}, "unit": {unit!r}}}), flush=True)
        print("##POST " + json.dumps({{"kind": "artifact", "path": out, "role": {role!r}, "sha256": sha}}), flush=True)
        print("##POST " + json.dumps({{"kind": "result", "ok": True, "detail": "done"}}), flush=True)
    """))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return [PY, str(script)]


def write_failing_worker(dir_: Path, name: str) -> list[str]:
    script = dir_ / f"{name}.py"
    script.write_text(textwrap.dedent("""
        import json
        print("##POST " + json.dumps({"kind": "err", "text": "boom"}), flush=True)
        print("##POST " + json.dumps({"kind": "result", "ok": False, "detail": "boom"}), flush=True)
        raise SystemExit(1)
    """))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return [PY, str(script)]


def write_retry_later_worker(dir_: Path, name: str, retry_at: str = "") -> list[str]:
    script = dir_ / f"{name}.py"
    detail = f', "retry_at": {retry_at!r}' if retry_at else ""
    script.write_text(textwrap.dedent(f"""
        import json
        print("##POST " + json.dumps({{"kind": "result", "ok": False, "detail": "limited"{detail}}}), flush=True)
        raise SystemExit(3)
    """))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return [PY, str(script)]


def write_needs_human_worker(dir_: Path, name: str) -> list[str]:
    script = dir_ / f"{name}.py"
    script.write_text(textwrap.dedent("""
        import json
        print("##POST " + json.dumps({"kind": "result", "ok": False, "detail": "needs a human"}), flush=True)
        raise SystemExit(4)
    """))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return [PY, str(script)]


def write_retry_then_succeed_worker(
    dir_: Path, name: str, marker: Path, retry_at: str, out_name: str = "out.bin"
) -> list[str]:
    """Exits retry_later once (leaving `marker`), then succeeds on the next attempt."""
    out_path = dir_ / out_name
    script = dir_ / f"{name}.py"
    script.write_text(textwrap.dedent(f"""
        import hashlib, json
        from pathlib import Path
        marker = Path({str(marker)!r})
        if not marker.exists():
            marker.write_text("hit")
            print("##POST " + json.dumps({{"kind": "result", "ok": False, "detail": "limited", "retry_at": {retry_at!r}}}), flush=True)
            raise SystemExit(3)
        out = {str(out_path)!r}
        with open(out, "w") as f:
            f.write("payload:{name}")
        sha = hashlib.sha256(open(out, "rb").read()).hexdigest()
        print("##POST " + json.dumps({{"kind": "artifact", "path": out, "role": "output", "sha256": sha}}), flush=True)
        print("##POST " + json.dumps({{"kind": "result", "ok": True, "detail": "done"}}), flush=True)
    """))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return [PY, str(script)]


def write_sleepy_worker(dir_: Path, name: str, seconds: float, lock_check: Path) -> list[str]:
    """Writes `lock_check` at start and removes it just before exiting, so a test can assert
    two of these never overlap (used for the resolve-lock test)."""
    script = dir_ / f"{name}.py"
    script.write_text(textwrap.dedent(f"""
        import json, time
        from pathlib import Path
        marker = Path({str(lock_check)!r})
        if marker.exists():
            raise SystemExit("overlap detected: " + marker.read_text())
        marker.write_text({name!r})
        time.sleep({seconds})
        marker.unlink()
        print("##POST " + json.dumps({{"kind": "result", "ok": True, "detail": "done"}}), flush=True)
    """))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return [PY, str(script)]
