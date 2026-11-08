"""post_api: FastAPI HTTP layer over post_core. Every route is a thin call into a
post_core function; business logic lives in post_core, never here (AGENTS.md/T10)."""
