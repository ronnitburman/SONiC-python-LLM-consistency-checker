"""API routes for Step 5 — SWSS SDK Exploration."""

from __future__ import annotations

import os

from fastapi import APIRouter, Query

from sonic_consistency_checker.core.redis_client import SonicRedisClient
from sonic_consistency_checker.swss.connector import swss_available
from sonic_consistency_checker.swss.config_db import (
    ConfigDbReader,
    RemoteConfigDbReader,
)
from sonic_consistency_checker.swss.sonic_v2 import (
    SonicV2Reader,
    RemoteSonicV2Reader,
)
from sonic_consistency_checker.swss.table_reader import SwssTableReader
from sonic_consistency_checker.swss.table_writer import SwssTableWriter
from sonic_consistency_checker.swss.compare import SwssCompareService

router = APIRouter(prefix="/api/swss", tags=["swss"])


# ── Reader factories (auto-select local vs remote based on .env) ────


def _get_config_reader() -> ConfigDbReader | RemoteConfigDbReader:
    mode = os.getenv("SONIC_CONNECTION_MODE", "")
    if mode in ("docker_exec", "orb_vm_exec"):
        return RemoteConfigDbReader(redis_client=SonicRedisClient())
    return ConfigDbReader()


def _get_v2_reader() -> SonicV2Reader | RemoteSonicV2Reader:
    mode = os.getenv("SONIC_CONNECTION_MODE", "")
    if mode in ("docker_exec", "orb_vm_exec"):
        return RemoteSonicV2Reader(redis_client=SonicRedisClient())
    return SonicV2Reader()


# Shared instances (table reader / writer always work via raw Redis)
table_reader = SwssTableReader()
table_writer = SwssTableWriter()
compare_svc = SwssCompareService()


# ── Check ────────────────────────────────────────────────────────────

@router.get("/check")
async def check_swss() -> dict:
    """Check SWSS SDK availability."""
    return swss_available()


# ── ConfigDBConnector ────────────────────────────────────────────────

@router.get("/config/{table}")
async def config_table(table: str) -> dict:
    """Read a CONFIG_DB table via ConfigDBConnector."""
    return _get_config_reader().get_table(table)


@router.get("/config/{table}/{key}")
async def config_entry(table: str, key: str) -> dict:
    """Read a CONFIG_DB entry via ConfigDBConnector."""
    return _get_config_reader().get_entry(table, key)


# ── SonicV2Connector ─────────────────────────────────────────────────

@router.get("/v2/{db_name}/keys")
async def v2_keys(
    db_name: str,
    pattern: str = Query("*", description="Key pattern"),
) -> dict:
    """Scan keys via SonicV2Connector."""
    return _get_v2_reader().keys(db_name, pattern)


@router.get("/v2/{db_name}/key")
async def v2_hgetall(
    db_name: str,
    key: str = Query(..., description="Redis key"),
) -> dict:
    """HGETALL via SonicV2Connector."""
    return _get_v2_reader().get_all(db_name, key)


# ── Table-oriented reads ─────────────────────────────────────────────

@router.get("/table/{db_name}/{table}")
async def table_keys(db_name: str, table: str) -> dict:
    """List keys in a table via raw Redis."""
    return table_reader.get_table_keys(db_name, table)


@router.get("/table/{db_name}/{table}/{key}")
async def table_entry(db_name: str, table: str, key: str) -> dict:
    """Read a table entry via raw Redis."""
    return table_reader.get_table_entry(db_name, table, key)


# ── Compare ──────────────────────────────────────────────────────────

@router.get("/compare/config/{table}/{key}")
async def compare_config(table: str, key: str) -> dict:
    """Compare raw Redis vs. SWSS SDK for a CONFIG_DB entry."""
    return compare_svc.compare_config_entry(table, key)


# ── Safe write experiments ───────────────────────────────────────────

@router.post("/test-produce")
async def test_produce(request: dict) -> dict:
    """Write a test entry via ProducerStateTable (safe writes only)."""
    return table_writer.produce_test_entry(
        table=request.get("table", ""),
        key=request.get("key", ""),
        values=request.get("values", {}),
        allow_writes=request.get("allow_writes", False),
    )


@router.delete("/test-produce")
async def test_delete(request: dict) -> dict:
    """Delete a test entry via ProducerStateTable (safe writes only)."""
    return table_writer.delete_test_entry(
        table=request.get("table", ""),
        key=request.get("key", ""),
        allow_writes=request.get("allow_writes", False),
    )
