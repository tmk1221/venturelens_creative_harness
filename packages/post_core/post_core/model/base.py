"""Shared base classes for the v3 data model.

Every persisted object carries an `id` (opaque string, caller/store assigns it) and a
`schema_version` (int, bumped whenever a model's on-disk shape changes incompatibly).
"""
from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


def new_id() -> str:
    return uuid.uuid4().hex


class Entity(BaseModel):
    """Base for every top-level persisted model."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: str = Field(default_factory=new_id, min_length=1)
    schema_version: int = 1


class Value(BaseModel):
    """Base for nested, non-identified value objects (no `id`/`schema_version`)."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)
