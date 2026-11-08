from __future__ import annotations

import stat
import sys
from pathlib import Path

from post_core.workers import legacy, runner

PY = sys.executable


def write_worker(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def test_legacy_success_when_artifacts_exist_and_are_non_trivial(tmp_path):
    out = tmp_path / "result.mp4"
    worker = write_worker(tmp_path, "legacy_ok.py", f"""
with open({str(out)!r}, "wb") as f:
    f.write(b"not empty")
print("Done! Wrote result.mp4")
""")
    result = legacy.run_legacy([PY, str(worker)], expected_artifacts=[str(out)], cwd=tmp_path)
    assert result.outcome == runner.OK
    assert result.exit_code == 0


def test_legacy_zero_exit_but_no_artifact_is_failed(tmp_path):
    out = tmp_path / "never_written.mp4"
    worker = write_worker(tmp_path, "legacy_lied.py",
                           "print('SKIPPED: nothing to do')\n")  # exits 0 anyway
    result = legacy.run_legacy([PY, str(worker)], expected_artifacts=[str(out)], cwd=tmp_path)
    assert result.outcome == runner.FAILED
    assert result.exit_code == 0


def test_legacy_empty_artifact_counts_as_trivial(tmp_path):
    out = tmp_path / "empty.mp4"
    worker = write_worker(tmp_path, "legacy_empty.py", f"""
open({str(out)!r}, "wb").close()
""")
    result = legacy.run_legacy([PY, str(worker)], expected_artifacts=[str(out)], cwd=tmp_path)
    assert result.outcome == runner.FAILED
    assert "trivial" in result.tail


def test_legacy_nonzero_exit_is_failed_even_with_artifact(tmp_path):
    out = tmp_path / "made_it_anyway.mp4"
    worker = write_worker(tmp_path, "legacy_fail.py", f"""
import sys
with open({str(out)!r}, "wb") as f:
    f.write(b"content")
sys.exit(1)
""")
    result = legacy.run_legacy([PY, str(worker)], expected_artifacts=[str(out)], cwd=tmp_path)
    assert result.outcome == runner.FAILED
    assert result.exit_code == 1


def test_legacy_timeout_reports_interrupted(tmp_path):
    worker = write_worker(tmp_path, "legacy_slow.py", "import time\ntime.sleep(30)\n")
    result = legacy.run_legacy([PY, str(worker)], expected_artifacts=[], cwd=tmp_path, timeout=0.5)
    assert result.outcome == runner.INTERRUPTED
