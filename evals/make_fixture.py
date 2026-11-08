#!/usr/bin/env python3
"""Build the eval fixture: a short two-speaker customer interview (an MSP owner describing a
phishing incident), with the fillers, false start and tangent a real recording has. Synthetic
media from ffmpeg lavfi; no real footage, network or paid calls.

Usage: python evals/make_fixture.py <out_dir>   -> prints the project root
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

HOST, GUEST = "SPEAKER_00", "SPEAKER_01"

SCRIPT: list[tuple[str, str]] = [
    (HOST, "Thanks for joining. Tell me about the incident."),
    (GUEST, "Sure. So, um, it was a Tuesday. It was, uh, it was a normal Tuesday morning."),
    (GUEST, "Our client's CFO got an email that looked exactly like their bank."),
    (GUEST, "She clicked the link and typed in her password before anyone noticed."),
    (GUEST, "Funny thing, I was actually on vacation in Cancun that week, great tacos by the way."),
    (GUEST, "Within ten minutes our security operations center flagged a login from overseas."),
    (GUEST, "We locked the account, reset her credentials, and blocked the sender domain."),
    (GUEST, "The attacker never got to the wire transfer, which was the whole point of the attack."),
    (HOST, "What changed after that?"),
    (GUEST, "We rolled out multi-factor authentication for every employee in two weeks."),
    (GUEST, "And we started monthly phishing simulations so people learn to spot the tells."),
    (GUEST, "Honestly, the training did more than any single tool we bought."),
]

WORD_DUR = 0.34


def sh(cmd: list[str]) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def post(*args: str) -> dict:
    return json.loads(sh([shutil.which("post") or "post", *args]))


def build(out_dir: Path) -> Path:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    root, media = out_dir / "project", out_dir / "media"
    root.mkdir(parents=True)
    media.mkdir()

    words, t = [], 0.0
    for speaker, sentence in SCRIPT:
        for w in sentence.split():
            words.append({"text": w, "start": round(t, 3), "end": round(t + WORD_DUR * 0.85, 3), "speaker": speaker})
            t += WORD_DUR
        t += 0.4  # pause between sentences
    duration = t + 1.0

    clip = media / "interview.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"color=c=0x2b3a4a:s=640x360:r=25:d={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=200:duration={duration}",
        "-shortest", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(clip),
    ], check=True, capture_output=True)

    post("init", str(root), "--name", "MSP phishing interview")
    src = post("source", "add", "--root", str(root), "--path", str(clip), "--role", "a_roll")
    post("ingest", "audio", "--root", str(root), "--shoot", src["shoot_id"], "--source-id", src["source_id"])
    tpath = out_dir / "transcript.json"
    tpath.write_text(json.dumps(words))
    imp = post("ingest", "import-transcript", "--root", str(root), "--shoot", src["shoot_id"],
               "--sync-group", src["sync_group_id"], "--path", str(tpath), "--format", "json")
    post("transcript", "speakers", "--root", str(root), imp["transcript_id"],
         "--map", f"{HOST}=Host", "--map", f"{GUEST}=Guest (MSP owner)")
    return root


if __name__ == "__main__":
    print(build(Path(sys.argv[1]).resolve()))
