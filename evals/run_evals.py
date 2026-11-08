#!/usr/bin/env python3
"""Run editing tasks against the MCP server with a headless Claude Code agent, then check the
project's final state. Each task gets a fresh fixture. The agent can use only this server's
tools (no shell, no file access), so every step it takes is a tool call we can count.

Usage: python evals/run_evals.py <out_dir> [--only T1,T3] [--label baseline]
Writes <out_dir>/<label>/results.json and one transcript per task.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_fixture  # noqa: E402

from post_mcp import server as srv  # noqa: E402


def _cut_by_label(root: str, label: str) -> dict | None:
    for c in srv.get_project(root)["cuts"]:
        if c["label"] == label:
            return srv.read_cut(root, c["cut_id"])
    return None


def _text(cut: dict) -> str:
    return " ".join(p["text"] for p in cut["passages"])


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9'-]+", s.lower())


KEEP = ["Thanks for joining", "CFO got an email", "typed in her password", "flagged a login",
        "locked the account", "never got to the wire transfer", "multi-factor authentication",
        "phishing simulations", "training did more"]


def check_t1(root):
    t = _text(_cut_by_label(root, "main"))
    w = _words(t)
    problems = []
    if "um" in w or "uh" in w:
        problems.append("filler left")
    if "it was, uh," in t.lower() or "it was it was" in " ".join(w):
        problems.append("false start left")
    if "normal tuesday morning" not in t.lower():
        problems.append("removed the real sentence")
    problems += [f"lost: {k}" for k in KEEP if k.lower() not in t.lower()]
    return problems


def check_t2(root):
    t = _text(_cut_by_label(root, "main"))
    problems = ["tangent left"] if "cancun" in t.lower() or "tacos" in t.lower() else []
    problems += [f"lost: {k}" for k in KEEP if k.lower() not in t.lower()]
    return problems


def check_t3(root):
    cut = _cut_by_label(root, "incident-short")
    if not cut:
        return ["no cut labelled incident-short"]
    t = _text(cut).lower()
    problems = []
    if cut["aspect"] != "9:16":
        problems.append(f"aspect {cut['aspect']}")
    for k in ["cfo got an email", "typed in her password", "flagged a login", "locked the account",
              "never got to the wire transfer"]:
        if k not in t:
            problems.append(f"missing: {k}")
    for k in ["cancun", "thanks for joining", "what changed", "multi-factor"]:
        if k in t:
            problems.append(f"should not contain: {k}")
    main = _cut_by_label(root, "main")
    if "cancun" not in _text(main).lower():
        problems.append("changed the main cut (tangent removed from main)")
    return problems


def check_t4(root):
    cut = _cut_by_label(root, "main")
    first = cut["passages"][0]["text"] if cut["passages"] else ""
    problems = [] if first.startswith("Honestly, the training") else [f"first passage is: {first[:50]!r}"]
    t = _text(cut)
    if t.count("Honestly, the training") != 1:
        problems.append("hook duplicated or lost")
    problems += [f"lost: {k}" for k in KEEP if k.lower() not in t.lower()]
    return problems


def check_t5(root):
    cut = _cut_by_label(root, "main")
    problems = []
    if not any("multi-factor" in v["over_words"] for v in cut["visuals"]):
        problems.append("no visual over the MFA sentence")
    beats = {(v["over_words"]) for v in cut["visuals"]}  # picture + overlay of one beat = one visual
    if len(beats) != 1:
        problems.append(f"{len(beats)} visuals, expected 1")
    if not list((Path(root) / "exports").glob("main_*.otio")):
        problems.append("no exported timeline")
    return problems


def check_t6(root):
    cut = _cut_by_label(root, "main")
    texts = [p["text"] for p in cut["passages"]]
    problems = [] if texts and texts[-1].startswith("Thanks for joining") else [f"last passage: {texts[-1][:40]!r}"]
    if "cancun" in _text(cut).lower():
        problems.append("tangent came back")
    return problems


def setup_t6(root, cut_id):
    """Take the first passage id, then make an edit so that id goes stale before the agent starts."""
    stale = srv.read_cut(root, cut_id)["passages"][0]["passage_id"]
    sent = next(x for x in srv.read_transcript(root, srv.get_project(root)["transcripts"][0]["transcript_id"])["sentences"]
                if "Cancun" in x["text"])
    srv.remove_words(root, cut_id, sent["first_word_id"], sent["last_word_id"])
    return {"stale_id": stale}


TASKS = {
    "T1": ("In the cut labelled 'main', remove the filler words (um, uh) and the guest's false start "
           "('It was, uh,' before 'it was a normal Tuesday morning'). Keep every other sentence.", check_t1),
    "T2": ("In the cut labelled 'main', cut the off-topic tangent about the guest's vacation. Keep everything else.",
           check_t2),
    "T3": ("Make a 9:16 short labelled 'incident-short' that tells only the incident story: from the CFO getting "
           "the fake bank email through the attacker never reaching the wire transfer. Leave out the vacation "
           "tangent and the host's lines. Don't change the 'main' cut.", check_t3),
    "T4": ("In the cut labelled 'main', move the guest's line about training doing more than any tool to the very "
           "start, as a hook. Nothing else should change.", check_t4),
    "T5": ("For the cut labelled 'main', get visual suggestions, accept only the one over the multi-factor "
           "authentication sentence, then export the timeline for DaVinci Resolve.", check_t5),
    # Error recovery: the id in the prompt is deliberately stale (an edit happened after it was read).
    "T6": ("In the cut labelled 'main', move passage {stale_id} (the one that starts 'Thanks for joining') "
           "to the end of the cut.", check_t6),
}
SETUP = {"T6": setup_t6}


def run_task(task_id: str, out: Path, python: str) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    fx = out / f"fx_{task_id}"
    root = str(make_fixture.build(fx))
    tid = srv.get_project(root)["transcripts"][0]["transcript_id"]
    main = srv.create_cut(root, tid, label="main")
    prompt, check = TASKS[task_id]
    if task_id in SETUP:
        prompt = prompt.format(**SETUP[task_id](root, main["cut_id"]))
    full = f"Project folder: {root}\n\nTask: {prompt}\n\nWhen done, reply with one line saying what you did."
    mcp_cfg = json.dumps({"mcpServers": {"vlh": {"command": python, "args": ["-m", "post_mcp.server"]}}})
    cmd = ["claude", "-p", full, "--output-format", "stream-json", "--verbose", "--strict-mcp-config",
           "--mcp-config", mcp_cfg, "--tools", "", "--allowedTools", "mcp__vlh__*", "--max-turns", "40"]
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900, cwd=str(fx))
    secs = round(time.time() - t0)
    (out / f"{task_id}.jsonl").write_text(proc.stdout)
    calls, errors, final, cost = [], [], "", None
    for line in proc.stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant":
            for b in ev["message"].get("content", []):
                if b.get("type") == "tool_use":
                    calls.append(b["name"].replace("mcp__vlh__", ""))
        elif ev.get("type") == "user":
            for b in ev["message"].get("content", []):
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error"):
                    c = b.get("content")
                    errors.append(c if isinstance(c, str) else json.dumps(c)[:300])
        elif ev.get("type") == "result":
            final, cost = ev.get("result", ""), ev.get("total_cost_usd")
    problems = check(root)
    return {"task": task_id, "passed": not problems, "problems": problems, "tool_calls": len(calls),
            "calls": calls, "errors": errors, "seconds": secs, "cost_usd": cost, "final": final[:300]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--only", default="")
    ap.add_argument("--label", default="run")
    ap.add_argument("--reps", type=int, default=1, help="run each task this many times")
    args = ap.parse_args()
    out = Path(args.out).resolve() / args.label
    out.mkdir(parents=True, exist_ok=True)
    ids = [t for t in (args.only.split(",") if args.only else TASKS)]
    jobs = [(t, n) for n in range(args.reps) for t in ids]
    with cf.ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda j: {**run_task(j[0], out / f"rep{j[1]}", sys.executable), "rep": j[1]}, jobs))
    (out / "results.json").write_text(json.dumps(results, indent=2))
    for r in results:
        print(f"{r['task']}.{r['rep']}  {'PASS' if r['passed'] else 'FAIL'}  calls={r['tool_calls']:>2}  "
              f"errors={len(r['errors'])}  {r['seconds']}s  {r['problems']}")


if __name__ == "__main__":
    main()
