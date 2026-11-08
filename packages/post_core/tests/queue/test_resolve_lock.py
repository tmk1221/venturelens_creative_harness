"""The cross-process Resolve lock actually serialises two independent processes."""
from __future__ import annotations

import multiprocessing
import time


def _hold_lock(project_root: str, marker_path: str, hold_seconds: float, q) -> None:
    from post_core.queue.resolve_lock import resolve_lock

    with resolve_lock(project_root):
        with open(marker_path, "a") as f:
            f.write("enter\n")
        time.sleep(hold_seconds)
        with open(marker_path, "a") as f:
            f.write("exit\n")
    q.put(True)


def test_resolve_lock_serialises_two_processes(tmp_path):
    marker = tmp_path / "marker.log"
    marker.write_text("")
    ctx = multiprocessing.get_context("spawn")
    q = ctx.Queue()
    p1 = ctx.Process(target=_hold_lock, args=(str(tmp_path), str(marker), 0.3, q))
    p2 = ctx.Process(target=_hold_lock, args=(str(tmp_path), str(marker), 0.3, q))
    p1.start()
    time.sleep(0.05)  # give p1 a head start so ordering is deterministic
    p2.start()
    p1.join(timeout=10)
    p2.join(timeout=10)
    assert q.get(timeout=5) is True
    assert q.get(timeout=5) is True

    lines = marker.read_text().splitlines()
    # Never interleaved: each holder's "enter" is immediately followed by its own "exit"
    # before the other one's "enter" -- i.e. lock holds are never concurrent.
    assert lines == ["enter", "exit", "enter", "exit"]
