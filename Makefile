.PHONY: dev demo demo-project demo-script

# Start post_api + the web dev server against the T19 demo project (built on first run).
# Ctrl-C stops both. See scripts/dev.sh / README.md.
dev:
	scripts/dev.sh

# Same as `dev`, but also opens a browser tab straight into the demo editor once it's up.
demo:
	scripts/dev.sh --open

# Just (re)build the demo project on disk under .demo/, without starting any server.
demo-project:
	packages/post_core/.venv/bin/python scripts/make_demo_project.py

# Real-footage demo (T21): the read-only import of the Acme 2026-09-09 shoot. Needs the T7 drive mounted.
demo-acme:
	POST_DEMO_DIR=$(CURDIR)/.demo-acme POST_DEMO_NAME="Acme 2026-09-09" ./scripts/dev.sh --open

# T23 post-picture-lock demo: the Acme Automations script (MEGA-CUT.md) treated as if
# spoken, no video/audio media at all (a virtual Source) -- see scripts/make_acme_script_demo.py.
demo-script:
	packages/post_core/.venv/bin/python scripts/make_acme_script_demo.py
	POST_DEMO_DIR=$(CURDIR)/.demo-script POST_DEMO_NAME="Acme Automations — script demo" ./scripts/dev.sh --open
