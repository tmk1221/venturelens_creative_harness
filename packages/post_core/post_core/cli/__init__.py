"""`post`: the headless front door (T06). Everything the UI will do is a `post` command
with JSON output; the web API (T10) and coding agents drive the same core functions this
package's commands are thin wrappers over.
"""
from __future__ import annotations
