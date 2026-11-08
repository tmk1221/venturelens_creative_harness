#!/usr/bin/env bash
# T26/T30d acceptance test infrastructure: builds the `.demo-enrich-e2e` project, starts a
# real post_api (POST3_FAKE_PROVIDERS=1 -- no network, no paid calls) with its own registry,
# seeds one span per recipe kind (`video`/`anim`/`provided`/`overlay`) through the real HTTP
# API (same path a user's browser would take -- see `_enrich_e2e_seed.py`; no budget: since
# T31 every Generate click creates its own, capped at the shown estimate), writes
# `web/e2e/.enrich-fixture.json` for the Playwright spec to read, then starts `vite dev`
# proxied at it. Used as the `webServer.command` of
# `web/playwright.enrich.config.ts`; Playwright kills this whole process group on teardown.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POST_CORE_VENV="$REPO_ROOT/packages/post_core/.venv"
POST_API_DIR="$REPO_ROOT/packages/post_api"
POST_API_VENV="$POST_API_DIR/.venv"
DEMO_DIR="$REPO_ROOT/.demo-enrich-e2e"
API_PORT="${ENRICH_E2E_API_PORT:-8811}"
WEB_PORT="${ENRICH_E2E_WEB_PORT:-5183}"
FIXTURE_JSON="$REPO_ROOT/web/e2e/.enrich-fixture.json"

echo "== building enrich e2e project =="
"$POST_CORE_VENV/bin/python" "$REPO_ROOT/scripts/make_enrich_e2e_project.py"

PIDS=()
cleanup() {
  for pid in "${PIDS[@]:-}"; do kill "$pid" >/dev/null 2>&1 || true; done
  wait >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "== starting post_api on :$API_PORT (POST3_FAKE_PROVIDERS=1) =="
(
  cd "$POST_API_DIR"
  export PYTHONPATH="$POST_API_DIR:${PYTHONPATH:-}"
  export POST_API_REGISTRY="$DEMO_DIR/registry.json"
  export POST3_FAKE_PROVIDERS=1
  exec "$POST_API_VENV/bin/uvicorn" post_api.serve:app_factory --factory --port "$API_PORT" --host 127.0.0.1
) &
PIDS+=("$!")

echo "== waiting for post_api =="
for _ in $(seq 1 50); do
  curl -sf "http://127.0.0.1:$API_PORT/api/projects" >/dev/null 2>&1 && break
  sleep 0.2
done
curl -sf "http://127.0.0.1:$API_PORT/api/projects" >/dev/null 2>&1 || { echo "post_api never came up" >&2; exit 1; }

META="$DEMO_DIR/meta.json"
PROJECT_ROOT="$("$POST_CORE_VENV/bin/python" -c "import json; print(json.load(open('$META'))['project_root'])")"
CUT_ID="$("$POST_CORE_VENV/bin/python" -c "import json; print(json.load(open('$META'))['cut_id'])")"

echo "== registering project =="
PID="$(curl -sf -X POST "http://127.0.0.1:$API_PORT/api/projects" \
  -H 'Content-Type: application/json' \
  -d "{\"root\": \"$PROJECT_ROOT\", \"name\": \"T26 enrich e2e\"}" | \
  "$POST_CORE_VENV/bin/python" -c "import json,sys; print(json.load(sys.stdin)['id'])")"

echo "== seeding video/anim/provided/overlay spans + workflows =="
"$POST_CORE_VENV/bin/python" "$REPO_ROOT/scripts/_enrich_e2e_seed.py" \
  "http://127.0.0.1:$API_PORT" "$PID" "$CUT_ID" "$META" "$API_PORT" "$FIXTURE_JSON"

echo "== starting vite on :$WEB_PORT =="
(
  cd "$REPO_ROOT/web"
  export POST_API_PORT="$API_PORT"
  exec npx vite --port "$WEB_PORT" --host 127.0.0.1 --strictPort
) &
PIDS+=("$!")

wait
