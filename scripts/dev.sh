#!/usr/bin/env bash
# Starts post_api + the web dev server against the T19 demo project (ffmpeg lavfi media +
# a generated transcript, no real footage, no network, no paid calls -- see
# scripts/make_demo_project.py). Wired as `make dev` / `make demo` (the latter also opens a
# browser tab straight into the editor). Ctrl-C stops both processes.
#
# Providers are FAKE (POST3_FAKE_PROVIDERS=1, nothing spends) unless POST3_REAL=1 is set
# -- see scripts/providers_mode.sh (T31).
#
# Usage: scripts/dev.sh [--open]        POST3_REAL=1 scripts/dev.sh  (real providers, spends)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=providers_mode.sh
source "$REPO_ROOT/scripts/providers_mode.sh"
POST_CORE_VENV="$REPO_ROOT/packages/post_core/.venv"
POST_API_DIR="$REPO_ROOT/packages/post_api"
POST_API_VENV="$POST_API_DIR/.venv"
DEMO_DIR="${POST_DEMO_DIR:-$REPO_ROOT/.demo}"   # POST_DEMO_DIR=.demo-acme for the real-footage project
PROJECT_NAME="${POST_DEMO_NAME:-Demo}"
API_PORT="${POST_API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"
OPEN_BROWSER=0
[[ "${1:-}" == "--open" ]] && OPEN_BROWSER=1

if [[ ! -x "$POST_CORE_VENV/bin/post" ]]; then
  echo "packages/post_core/.venv is missing its 'post' CLI -- build the venv first (see docs/HANDOFF.md)" >&2
  exit 1
fi
if [[ ! -x "$POST_API_VENV/bin/uvicorn" ]]; then
  echo "packages/post_api/.venv is missing uvicorn -- build the venv first (see docs/HANDOFF.md)" >&2
  exit 1
fi
if [[ ! -d "$REPO_ROOT/web/node_modules" ]]; then
  echo "web/node_modules is missing -- run 'npm ci' in web/ first" >&2
  exit 1
fi

if [[ -z "${POST_DEMO_DIR:-}" && ! -d "$DEMO_DIR/project" ]]; then
  echo "== building demo project =="
  "$POST_CORE_VENV/bin/python" "$REPO_ROOT/scripts/make_demo_project.py"
fi

PIDS=()
cleanup() {
  echo ""
  echo "== stopping =="
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" >/dev/null 2>&1 || true
  done
  wait >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

if [[ "$POST3_PROVIDERS" == "real" ]]; then
  echo "== REAL providers (POST3_REAL=1): generation spends credits =="
else
  echo "== fake providers (POST3_FAKE_PROVIDERS=1): placeholder media, nothing spends =="
fi
echo "== starting post_api on :$API_PORT =="
(
  cd "$POST_API_DIR"
  export PYTHONPATH="$POST_API_DIR:${PYTHONPATH:-}"
  export POST_API_REGISTRY="$DEMO_DIR/registry.json"
  exec "$POST_API_VENV/bin/uvicorn" post_api.serve:app_factory --factory --port "$API_PORT" --host 127.0.0.1
) &
PIDS+=("$!")

echo "== waiting for post_api =="
for _ in $(seq 1 50); do
  if curl -sf "http://127.0.0.1:$API_PORT/api/projects" >/dev/null 2>&1; then break; fi
  sleep 0.2
done
if ! curl -sf "http://127.0.0.1:$API_PORT/api/projects" >/dev/null 2>&1; then
  echo "post_api never came up on :$API_PORT" >&2
  exit 1
fi

echo "== registering the demo project =="
DEMO_META="$DEMO_DIR/meta.json"
if [[ -f "$DEMO_META" ]]; then
  PROJECT_ROOT="$("$POST_CORE_VENV/bin/python" -c "import json; print(json.load(open('$DEMO_META'))['project_root'])")"
  CUT_ID="$("$POST_CORE_VENV/bin/python" -c "import json; print(json.load(open('$DEMO_META'))['cut_id'])")"
else  # a project dir without meta.json: the dir is the project root; open its first cut
  PROJECT_ROOT="$DEMO_DIR"
  CUT_ID="$(ls "$DEMO_DIR/.post3/cuts" | grep -v -e undo -e lock | head -1 | sed 's/\.json$//')"
fi
PID="$(curl -sf -X POST "http://127.0.0.1:$API_PORT/api/projects" \
  -H 'Content-Type: application/json' \
  -d "{\"root\": \"$PROJECT_ROOT\", \"name\": \"$PROJECT_NAME\"}" | \
  "$POST_CORE_VENV/bin/python" -c "import json,sys; print(json.load(sys.stdin)['id'])")"

EDIT_URL="http://127.0.0.1:$WEB_PORT/p/$PID/edit/$CUT_ID"
echo "== starting vite on :$WEB_PORT =="
echo "edit: $EDIT_URL"
(
  cd "$REPO_ROOT/web"
  export POST_API_PORT="$API_PORT"
  exec npx vite --port "$WEB_PORT" --host 127.0.0.1
) &
PIDS+=("$!")

if [[ "$OPEN_BROWSER" == "1" ]]; then
  for _ in $(seq 1 50); do
    if curl -sf "http://127.0.0.1:$WEB_PORT" >/dev/null 2>&1; then break; fi
    sleep 0.2
  done
  # T27 item 3: a cache-busting query param forces a fresh navigation/fetch instead of the
  # browser reusing an existing tab/bfcache entry already open on this exact URL from a
  # previous run (the vite dev server itself now also sends `Cache-Control: no-store`, see
  # web/vite.config.ts).
  FRESH_URL="$EDIT_URL?t=$(date +%s)"
  echo "opening: $FRESH_URL"
  if command -v open >/dev/null 2>&1; then open "$FRESH_URL"; fi
fi

wait
