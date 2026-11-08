"""Real-mode HyperFrames CLI calls for `animation_draft_render.py`/`animation_render.py`.
Never exercised by this repo's tests (POST3_FAKE_PROVIDERS=1 always short-circuits first).

UNVERIFIED ASSUMPTION -- a human must check this against a real `hyperframes` install
before the first real animation render: this module assumes `hyperframes render
<composition_dir> --out <path> --width <w> --height <h> --fps <fps> --json` renders the
composition at `composition_dir/index.html` to a single video file at `--out` and prints a
JSON object on success. T12 did not run this command (forbidden: "no hyperframes render of
real projects"); it was written from the `hyperframes-cli` skill's command list, not from
observed output, so the exact flag names/JSON shape need a real, human-run check.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def render(composition_dir: Path, dest: Path, width: int, height: int, fps: int) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "hyperframes", "render", str(composition_dir), "--out", str(dest),
            "--width", str(width), "--height", str(height), "--fps", str(fps), "--json",
        ],
        check=True, capture_output=True, text=True,
    )


__all__ = ["render"]
