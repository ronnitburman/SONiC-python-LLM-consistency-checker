"""Pydantic models for SONiC consistency checker."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── Step 2 models ──────────────────────────────────────────────────────


class DbSizeSummary(BaseModel):
    """Size summary for a single SONiC Redis database."""

    db_name: str
    db_id: int
    size: int


class SonicDbKey(BaseModel):
    """Full key info: type, hash fields, and the equivalent redis-cli command."""

    db_name: str
    db_id: int
    key: str
    key_type: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)
    equivalent_redis: str | None = None


class DbKeysResponse(BaseModel):
    """Result of a key scan with pattern."""

    db_name: str
    db_id: int
    pattern: str
    keys: list[str]
    equivalent_redis: str


class KeyTypeResponse(BaseModel):
    """Result of a TYPE query."""

    db_name: str
    key: str
    key_type: str


# ── Step 3 models ──────────────────────────────────────────────────────


class PortView(BaseModel):
    """Normalized cross-DB view of a single SONiC port."""

    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    app: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)
    asic: dict[str, Any] = Field(default_factory=dict)
    counters: dict[str, Any] = Field(default_factory=dict)
    transceiver: dict[str, Any] = Field(default_factory=dict)
    raw_keys: dict[str, list[str]] = Field(default_factory=dict)


class PortsListResponse(BaseModel):
    """List of discovered port names and their discovery source."""

    ports: list[str]
    source: str
