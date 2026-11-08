"""`build_cmd`: turn a worker module name + flat kwargs into the argv `cli/context.cmd_for`
already knows how to run (it reads `node.params['cmd']`, a list[str] -- the convention T06
built for exactly this). Kept as one tiny helper so every recipe node type builds its argv
the same way instead of hand-rolling `--flag value` pairs six times.
"""
from __future__ import annotations

import sys
from typing import Any


def build_cmd(worker_module: str, **flags: Any) -> list[str]:
    """`build_cmd("still_generate", node_id="n1", model="x", continuity=["a.png", "b.png"])`
    -> `[python, "-m", "post_core.recipes.workers.still_generate", "--node-id", "n1",
    "--model", "x", "--continuity", "a.png", "--continuity", "b.png"]`. `None` values are
    omitted; `True`/`False` become a bare `--flag` present or absent; a list repeats the
    flag once per item (argparse `action="append"`); anything else is stringified once.
    """
    argv = [sys.executable, "-m", f"post_core.recipes.workers.{worker_module}"]
    for name, value in flags.items():
        flag = "--" + name.replace("_", "-")
        if value is None:
            continue
        if isinstance(value, bool):
            if value:
                argv.append(flag)
            continue
        if isinstance(value, (list, tuple)):
            for item in value:
                argv.extend([flag, str(item)])
            continue
        argv.extend([flag, str(value)])
    return argv


__all__ = ["build_cmd"]
