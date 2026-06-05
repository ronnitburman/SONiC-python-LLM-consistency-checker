"""API routes for Step 2 — Redis DB Explorer."""

from __future__ import annotations

from fastapi import APIRouter, Query

from sonic_consistency_checker.core.discovery import SonicDiscoveryService
from sonic_consistency_checker.core.models import (
    DbKeysResponse,
    DbSizeSummary,
    KeyTypeResponse,
    SonicDbKey,
)

router = APIRouter(prefix="/api/dbs", tags=["dbs"])

# Shared discovery service — created once at module load
discovery = SonicDiscoveryService()


@router.get("", response_model=list[DbSizeSummary])
async def list_dbs() -> list[DbSizeSummary]:
    """Return DB size summaries for all known SONiC Redis databases."""
    return discovery.list_db_sizes()


@router.get("/{db_name}/keys", response_model=DbKeysResponse)
async def scan_db_keys(
    db_name: str,
    pattern: str = Query("*", description="Key pattern (e.g. PORT*)"),
) -> DbKeysResponse:
    """Scan keys in a SONiC Redis DB matching *pattern*."""
    return discovery.scan_db(db_name, pattern)


@router.get("/{db_name}/key", response_model=SonicDbKey)
async def read_key(
    db_name: str,
    key: str = Query(..., description="Redis key (e.g. PORT|Ethernet0)"),
) -> SonicDbKey:
    """Read a key's type and hash fields (if applicable)."""
    return discovery.read_key(db_name, key)


@router.get("/{db_name}/type", response_model=KeyTypeResponse)
async def key_type(
    db_name: str,
    key: str = Query(..., description="Redis key (e.g. PORT|Ethernet0)"),
) -> KeyTypeResponse:
    """Return the Redis type of a key."""
    return discovery.key_type(db_name, key)
