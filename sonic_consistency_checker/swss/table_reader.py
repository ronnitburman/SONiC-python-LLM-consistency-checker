"""SwssTableReader — table-oriented Redis reading.

Treats SONiC Redis keys as table+key pairs. Uses the existing raw Redis
client from Step 2 (not SWSS SDK).
"""

from __future__ import annotations

from typing import Any

from sonic_consistency_checker.core.redis_client import SonicRedisClient


class SwssTableReader:
    """Reads Redis data with a table-oriented mental model.

    e.g. table=PORT, key=Ethernet0 → raw Redis key PORT|Ethernet0
    """

    def __init__(self, redis_client: SonicRedisClient | None = None) -> None:
        self.redis_client = redis_client or SonicRedisClient()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def candidate_key_names(table_name: str, key: str) -> list[str]:
        """Return possible raw Redis keys for given table+key."""
        return [
            f"{table_name}|{key}",
            f"{table_name}:{key}",
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_table_keys(
        self, db_name: str, table_name: str
    ) -> dict[str, Any]:
        """Return all keys matching a table pattern in *db_name*."""
        patterns = [
            f"{table_name}|*",
            f"{table_name}:*",
        ]

        all_keys: list[str] = []
        for pattern in patterns:
            try:
                all_keys.extend(
                    self.redis_client.scan_keys(db_name, pattern)
                )
            except Exception:
                continue

        unique_keys = sorted(set(all_keys))

        return {
            "db_name": db_name,
            "table_name": table_name,
            "patterns": patterns,
            "keys": unique_keys,
            "equivalent_redis": [
                self.redis_client.equivalent_scan_command(db_name, p)
                for p in patterns
            ],
        }

    def get_table_entry(
        self, db_name: str, table_name: str, key: str
    ) -> dict[str, Any]:
        """Read a single table entry, trying both separators."""
        candidates = self.candidate_key_names(table_name, key)

        for candidate in candidates:
            try:
                ktype = self.redis_client.key_type(db_name, candidate)
                if ktype == "hash":
                    fields = self.redis_client.hgetall(db_name, candidate)
                    if fields:
                        return {
                            "db_name": db_name,
                            "table_name": table_name,
                            "key": key,
                            "raw_key": candidate,
                            "key_type": ktype,
                            "fields": fields,
                            "equivalent_redis": (
                                self.redis_client.equivalent_hgetall_command(
                                    db_name, candidate
                                )
                            ),
                        }
            except Exception:
                continue

        return {
            "db_name": db_name,
            "table_name": table_name,
            "key": key,
            "raw_key": None,
            "key_type": "none",
            "fields": {},
            "equivalent_redis": [
                self.redis_client.equivalent_hgetall_command(db_name, c)
                for c in candidates
            ],
        }

    def dump_table(
        self, db_name: str, table_name: str, limit: int = 50
    ) -> dict[str, Any]:
        """Dump up to *limit* entries from a table."""
        table_keys = self.get_table_keys(db_name, table_name)
        keys = table_keys["keys"][:limit]

        entries: dict[str, Any] = {}
        for raw_key in keys:
            try:
                ktype = self.redis_client.key_type(db_name, raw_key)
                fields = (
                    self.redis_client.hgetall(db_name, raw_key)
                    if ktype == "hash"
                    else {}
                )
                entries[raw_key] = {
                    "key_type": ktype,
                    "fields": fields,
                }
            except Exception as exc:
                entries[raw_key] = {"error": str(exc)}

        return {
            "db_name": db_name,
            "table_name": table_name,
            "limit": limit,
            "keys_returned": len(keys),
            "entries": entries,
            "source": table_keys,
        }
