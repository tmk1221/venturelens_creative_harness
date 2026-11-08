#!/usr/bin/env python3
"""T30d: seeds the enrich e2e's spans (one per recipe kind the graph-node acceptance test
needs -- video/anim/provided/overlay) against a *running* post_api, over plain HTTP (the same
path a browser takes), then writes `web/e2e/.enrich-fixture.json` for the Playwright spec to
read. Split out of `enrich_e2e_up.sh` (bash) because five ops calls plus per-recipe workflow
instantiation is far less error-prone in Python than shell+heredoc string interpolation.
Idempotent by `Span.kind` (each kind used here is unique on this cut), so re-running
`enrich_e2e_up.sh` against an already-seeded `.demo-enrich-e2e` project is a safe no-op past
the first run. No network, no paid provider -- the caller sets `POST3_FAKE_PROVIDERS=1` on
the post_api process this talks to.

Usage: python3 _enrich_e2e_seed.py <api_base> <pid> <cut_id> <meta.json path> <api_port> <fixture.json out path>
"""
from __future__ import annotations

import json
import sys
import urllib.request

API_BASE, PID, CUT_ID, META_PATH, API_PORT, FIXTURE_PATH = sys.argv[1:7]


def call(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(f"{API_BASE}{path}", data=data, method=method, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def get_cut() -> dict:
    return call("GET", f"/api/projects/{PID}/cuts/{CUT_ID}")


meta = json.load(open(META_PATH, encoding="utf-8"))
word_ids: list[str] = meta["word_ids"]
sync_group_id: str = meta["sync_group_id"]

# Non-overlapping word-index ranges on the one 20-word passage `make_enrich_e2e_project.py`
# builds -- indices 15-19 ("we also want to show") are left unclaimed for the live
# select-words -> Add visual -> Open in graph dialog flow the Playwright spec drives directly
# (the focusNodeId acceptance check), so they're not assigned here.
PICTURE_RANGES = {
    "video": (0, 4, "video", "a still shot"),
    "anim": (5, 7, "anim", "explain it with a quick motion graphic"),
    "provided": (8, 10, "provided", "office B-roll we already have"),
}
OVERLAY_RANGE = (11, 12)  # "what shipped" -- overlay-only span, in_front/lower-band.

span_ids: dict[str, str] = {}

existing = {s["kind"]: s["id"] for s in get_cut()["cut"].get("spans", [])}

for name, (start_i, end_i, kind, note) in PICTURE_RANGES.items():
    if kind in existing:
        span_ids[name] = existing[kind]
        continue
    rev = get_cut()["revision"]
    call("POST", f"/api/projects/{PID}/cuts/{CUT_ID}/ops", {
        "name": "add_span", "expected_rev": rev,
        "args": {
            "sync_group_id": sync_group_id, "start_word_id": word_ids[start_i], "end_word_id": word_ids[end_i],
            "layer": "picture", "kind": kind, "note": note,
        },
    })
    span_ids[name] = next(s["id"] for s in get_cut()["cut"]["spans"] if s["kind"] == kind)

if "overlay" in existing:
    span_ids["overlay"] = existing["overlay"]
else:
    rev = get_cut()["revision"]
    start_i, end_i = OVERLAY_RANGE
    call("POST", f"/api/projects/{PID}/cuts/{CUT_ID}/ops", {
        "name": "add_beat_spans", "expected_rev": rev,
        "args": {
            "sync_group_id": sync_group_id, "start_word_id": word_ids[start_i], "end_word_id": word_ids[end_i],
            "overlay_depth": "in_front", "overlay_position": "lower-band", "provenance": "human",
        },
    })
    span_ids["overlay"] = next(s["id"] for s in get_cut()["cut"]["spans"] if s["kind"] == "overlay")

# Instantiate every span's workflow up front (idempotent server-side -- a span that already
# carries a workflow_id just returns it) so the card/graph views have real state the moment
# Playwright opens them, instead of racing the card's own on-mount instantiate call.
for span_id in span_ids.values():
    call("POST", f"/api/projects/{PID}/cuts/{CUT_ID}/spans/{span_id}/workflow")

fixture = {
    "pid": PID, "cutId": CUT_ID, "apiPort": int(API_PORT),
    "spanId": span_ids["video"], "animSpanId": span_ids["anim"],
    "providedSpanId": span_ids["provided"], "overlaySpanId": span_ids["overlay"],
}
with open(FIXTURE_PATH, "w", encoding="utf-8") as f:
    json.dump(fixture, f, indent=2)
print(f"seeded spans: {span_ids}")
