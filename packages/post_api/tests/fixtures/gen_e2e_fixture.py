"""Generate `web/e2e/fixtures/basic.json` (and, with `--large`, `large.json`): real
`post_api` responses for a small project (one shoot/source/transcript/cut), for Playwright
to replay via `page.route` mocking.
Run with the post_api venv: `.venv/bin/python tests/fixtures/gen_e2e_fixture.py [--large]`.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fastapi.testclient import TestClient  # noqa: E402

from post_api.app import create_app  # noqa: E402

WEB_FIXTURES = Path(__file__).resolve().parents[4] / "web" / "e2e" / "fixtures"


def _lavfi_clip(tmp_path: Path) -> Path:
    out = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=25:d=2",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-shortest",
         "-c:v", "libx264", "-c:a", "aac", str(out)],
        check=True, capture_output=True,
    )
    return out


_FILLER_VOCAB = ["So", "um", "today", "we're", "going", "to", "talk", "about", "the", "launch", "basically", "like", "and", "yeah"]


def _words_payload(n: int) -> list[dict]:
    return [{"text": _FILLER_VOCAB[i % len(_FILLER_VOCAB)], "start": i * 0.3, "end": i * 0.3 + 0.25} for i in range(n)]


def _all_words(client, pid: str, transcript_id: str) -> dict:
    """Page through `/words` (server caps a page at 2000) and stitch one full payload, the
    shape `web/e2e/largeMockApi.ts` replays for the 20k-word scroll performance test."""
    out: list[dict] = []
    offset = 0
    total = None
    while total is None or offset < total:
        r = client.get(f"/api/projects/{pid}/transcripts/{transcript_id}/words", params={"offset": offset, "limit": 2000})
        page = r.json()
        total = page["total"]
        out.extend(page["words"])
        offset += len(page["words"]) or 2000
        if not page["words"]:
            break
    return {"transcript_id": transcript_id, "total": total, "offset": 0, "limit": total, "words": out}


def _build(client, tmp_path: Path, *, word_count: int) -> dict:
    root = tmp_path / f"proj-{word_count}"
    r = client.post("/api/projects", json={"root": str(root), "name": "Demo"})
    pid = r.json()["id"]

    clip = _lavfi_clip(tmp_path)
    r = client.post(f"/api/projects/{pid}/sources", json={"path": str(clip), "role": "a_roll"})
    body = r.json()
    source_id, sync_group_id = body["source_id"], body["sync_group_id"]

    transcript_path = tmp_path / f"t-{word_count}.json"
    transcript_path.write_text(json.dumps(_words_payload(word_count)))
    r = client.post(f"/api/projects/{pid}/ingest/import-transcript", json={
        "shoot": body["shoot_id"], "sync_group": sync_group_id, "path": str(transcript_path), "format": "json",
    })
    transcript_id = r.json()["transcript_id"]

    r = client.post(f"/api/projects/{pid}/cuts", json={
        "transcript": transcript_id, "angle": source_id, "aspect": "16:9",
    })
    cut_id = r.json()["cut_id"]

    return {
        "pid": pid,
        "source_id": source_id,
        "sync_group_id": sync_group_id,
        "transcript_id": transcript_id,
        "cut_id": cut_id,
        "projects": client.get("/api/projects").json(),
        "shoots": client.get(f"/api/projects/{pid}/shoots").json(),
        "cutList": client.get(f"/api/projects/{pid}/cuts").json(),
        "cut": client.get(f"/api/projects/{pid}/cuts/{cut_id}").json(),
        "timeline": client.get(f"/api/projects/{pid}/cuts/{cut_id}/timeline").json(),
        "transcript": client.get(f"/api/projects/{pid}/transcripts/{transcript_id}").json(),
        "words": _all_words(client, pid, transcript_id) if word_count > 500 else client.get(f"/api/projects/{pid}/transcripts/{transcript_id}/words").json(),
        "suggestions": client.get(f"/api/projects/{pid}/transcripts/{transcript_id}/suggestions").json(),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--large", action="store_true", help="also write large.json (20k words, for the scroll-perf test)")
    args = ap.parse_args()

    WEB_FIXTURES.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        registry_path = tmp_path / "registry.json"
        app = create_app(registry_path)
        with TestClient(app) as client:
            fixture = _build(client, tmp_path, word_count=11)
            (WEB_FIXTURES / "basic.json").write_text(json.dumps(fixture, indent=2))
            print(f"wrote {WEB_FIXTURES / 'basic.json'}")

            if args.large:
                large = _build(client, tmp_path, word_count=20_000)
                (WEB_FIXTURES / "large.json").write_text(json.dumps(large, indent=2))
                print(f"wrote {WEB_FIXTURES / 'large.json'}")


if __name__ == "__main__":
    main()
