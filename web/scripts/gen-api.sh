#!/usr/bin/env bash
# Regenerate src/api/openapi.json + src/api/schema.ts from the live post_api FastAPI app.
# Run from web/ (via `npm run gen:api`).
set -euo pipefail
cd "$(dirname "$0")/.."

API_DIR="../packages/post_api"
(cd "$API_DIR" && .venv/bin/python -m post_api.openapi) >src/api/openapi.json
npx openapi-typescript src/api/openapi.json -o src/api/schema.ts
