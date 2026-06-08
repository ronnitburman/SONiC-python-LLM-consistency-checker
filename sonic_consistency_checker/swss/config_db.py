"""ConfigDbReader — read CONFIG_DB data through SONiC ConfigDBConnector."""

from __future__ import annotations

from typing import Any

from sonic_consistency_checker.swss.connector import (
    SwssSdkUnavailable,
    require_swsssdk,
)


class ConfigDbReader:
    """Reads CONFIG_DB tables/entries via swsssdk.ConfigDBConnector.

    If swsssdk is unavailable, every method returns a graceful
    {'available': False, 'error': ...} dict instead of crashing.
    """

    def __init__(self) -> None:
        self.connector: Any | None = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Connect using swsssdk.ConfigDBConnector."""
        swsssdk = require_swsssdk()
        connector = swsssdk.ConfigDBConnector()
        connector.connect()
        self.connector = connector

    def _ensure_connected(self) -> None:
        if self.connector is None:
            self.connect()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_table(self, table_name: str) -> dict[str, Any]:
        """Return all entries in a CONFIG_DB table."""
        eq_redis = (
            f'redis-cli -n <CONFIG_DB_ID> scan 0 match '
            f'"{table_name}|*" count 100'
        )
        try:
            self._ensure_connected()
            result = self.connector.get_table(table_name)  # type: ignore[union-attr]
            return {
                "available": True,
                "method": "ConfigDBConnector.get_table",
                "arguments": {"table": table_name},
                "equivalent_redis": eq_redis,
                "result": result or {},
            }
        except (SwssSdkUnavailable, Exception) as exc:
            return {
                "available": False,
                "method": "ConfigDBConnector.get_table",
                "arguments": {"table": table_name},
                "equivalent_redis": eq_redis,
                "result": {},
                "error": str(exc),
            }

    def get_entry(self, table_name: str, key: str) -> dict[str, Any]:
        """Return a single CONFIG_DB table entry."""
        eq_redis = (
            f'redis-cli -n <CONFIG_DB_ID> hgetall '
            f'"{table_name}|{key}"'
        )
        try:
            self._ensure_connected()
            result = self.connector.get_entry(  # type: ignore[union-attr]
                table_name, key
            )
            return {
                "available": True,
                "method": "ConfigDBConnector.get_entry",
                "arguments": {"table": table_name, "key": key},
                "equivalent_redis": eq_redis,
                "result": result or {},
            }
        except (SwssSdkUnavailable, Exception) as exc:
            return {
                "available": False,
                "method": "ConfigDBConnector.get_entry",
                "arguments": {"table": table_name, "key": key},
                "equivalent_redis": eq_redis,
                "result": {},
                "error": str(exc),
            }

    def list_keys(self, table_name: str) -> dict[str, Any]:
        """Return all keys in a CONFIG_DB table."""
        table_result = self.get_table(table_name)
        result = table_result.get("result") or {}

        if isinstance(result, dict):
            keys = sorted(result.keys())
        else:
            keys = []

        return {
            **table_result,
            "method": "ConfigDBConnector.get_table (keys only)",
            "keys": keys,
        }
