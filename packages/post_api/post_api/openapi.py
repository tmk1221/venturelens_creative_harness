"""`python -m post_api.openapi > web/src/api/openapi.json`: print this app's OpenAPI schema.

Frontend TS types (T11+) are generated from that file with `openapi-typescript`, documented
here rather than added as a new `web/` npm script (T10 only touches `packages/post_api/`):

    npx openapi-typescript web/src/api/openapi.json -o web/src/api/schema.ts

A temp registry path is used since generating the schema needs no real project registry --
the schema is static, derived from route/model annotations only, not from disk state.
"""
from __future__ import annotations

import json
import sys
import tempfile

from .app import create_app


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(f"{tmp}/registry.json")
        schema = app.openapi()
    print(json.dumps(schema, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
