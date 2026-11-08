"""yaml_io.py — round-trip YAML load/dump for kit *writes* (T20).

Every other module in this package reads a kit with plain `yaml.safe_load` (fine — it
never writes brand.yaml back out). Anything that WRITES a hand-annotated brand.yaml
(`__main__.cmd_init` with `--from`, `derive.accept_style`) must preserve the comments
Travis writes above every field, so it goes through `ruamel.yaml`'s round-trip loader/
dumper instead. Kept in one place so both callers agree on formatting.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.width = 100
_yaml.indent(mapping=2, sequence=2, offset=0)


def load_roundtrip(path: str | Path) -> Any:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        return _yaml.load(f)


def dump_roundtrip(data: Any, path: str | Path) -> None:
    path = Path(path)
    with path.open("w", encoding="utf-8") as f:
        _yaml.dump(data, f)
