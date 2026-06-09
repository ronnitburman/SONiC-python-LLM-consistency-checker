"""SonicDiscoveryService — service layer for Redis DB exploration.

Wraps SonicRedisClient and returns structured model objects for CLI/API.
"""

from __future__ import annotations

import logging

from sonic_consistency_checker.core.models import (
    DbKeysResponse,
    DbSizeSummary,
    KeyTypeResponse,
    SonicDbKey,
)
from sonic_consistency_checker.core.redis_client import (
    SonicRedisClient,
    SonicRedisError,
)

logger = logging.getLogger(__name__)


class SonicDiscoveryService:
    """High-level service for exploring SONiC Redis DBs.

    All operations use dynamic DB name → ID resolution via SonicRedisClient.
    """

    def __init__(self, redis_client: SonicRedisClient | None = None) -> None:
        self.redis_client = redis_client or SonicRedisClient()

    def list_db_sizes(self) -> list[DbSizeSummary]:
        """Return size (key count) for every known SONiC Redis DB."""
        results: list[DbSizeSummary] = []

        for db_name in sorted(self.redis_client.databases.keys()):
            db_id = self.redis_client.databases[db_name].id
            err_msg: str | None = None
            try:
                size = self.redis_client.dbsize(db_name)
            except (SonicRedisError, ValueError, Exception) as exc:
                logger.warning("Could not read dbsize for %s: %s", db_name, exc)
                size = -1
                err_msg = str(exc).strip()
                if not err_msg:
                    err_msg = type(exc).__name__

            results.append(
                DbSizeSummary(
                    db_name=db_name,
                    db_id=db_id,
                    size=size,
                    error=err_msg,
                )
            )

        return results

    def scan_db(self, db_name: str, pattern: str = "*") -> DbKeysResponse:
        """Scan keys in a DB matching *pattern*."""
        db_id = self.redis_client.get_db_id(db_name)
        keys = self.redis_client.scan_keys(db_name, pattern)
        eq_cmd = self.redis_client.equivalent_scan_command(db_name, pattern)

        return DbKeysResponse(
            db_name=db_name.upper(),
            db_id=db_id,
            pattern=pattern,
            keys=keys,
            equivalent_redis=eq_cmd,
        )

    def read_key(self, db_name: str, key: str) -> SonicDbKey:
        """Read a key's type and hash fields (if applicable)."""
        db_id = self.redis_client.get_db_id(db_name)
        ktype = self.redis_client.key_type(db_name, key)

        fields: dict[str, str] = {}
        if ktype == "hash":
            fields = self.redis_client.hgetall(db_name, key)

        eq_cmd = self.redis_client.equivalent_hgetall_command(db_name, key)

        return SonicDbKey(
            db_name=db_name.upper(),
            db_id=db_id,
            key=key,
            key_type=ktype,
            fields=fields,
            equivalent_redis=eq_cmd,
        )

    def key_type(self, db_name: str, key: str) -> KeyTypeResponse:
        """Return the Redis type of a key."""
        ktype = self.redis_client.key_type(db_name, key)

        return KeyTypeResponse(
            db_name=db_name.upper(),
            key=key,
            key_type=ktype,
        )
