"""`post` subcommand implementations, one module per command group. Each function here
takes an `argparse.Namespace` and returns a plain/pydantic result for `output.run_command`
to print as JSON -- no command prints anything itself or calls `sys.exit`.
"""
from __future__ import annotations
