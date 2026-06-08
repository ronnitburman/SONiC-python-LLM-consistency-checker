"""SonicV2Reader — multi-DB access via swsssdk.SonicV2Connector."""

from __future__ import annotations

from typing import Any

from sonic_consistency_checker.swss.connector import (
    SwssSdkUnavailable,
    require_swsssdk,
)


class SonicV2Reader:
    """Accesses SONiC Redis DBs by logical name via SonicV2Connector.

    If swsssdk is unavailable, methods return graceful error dicts.
    """

    def __init__(self) -> None:
        self.connector: Any | None = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Connect using swsssdk.SonicV2Connector."""
        swsssdk = require_swsssdk()
        self.connector = swsssdk.SonicV2Connector()

    def _ensure_connected(self) -> None:
        if self.connector is None:
            self.connect()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def keys(self, db_name: str, pattern: str = "*") -> dict[str, Any]:
        """Scan keys in *db_name* matching *pattern*."""
        eq_redis = (
            f'redis-cli -n <{db_name}_ID> scan 0 match '
            f'"{pattern}" count 100'
        )
        try:
            self._ensure_connected()
            connector = self.connector

            if hasattr(connector, "keys"):
                result: list[str] = connector.keys(  # type: ignore[union-attr]
                    db_name, pattern
                )
            else:
                raise RuntimeError(
                    "SonicV2Connector.keys() is not available."
                )

            return {
                "available": True,
                "method": "SonicV2Connector.keys",
                "arguments": {"db_name": db_name, "pattern": pattern},
                "equivalent_redis": eq_redis,
                "result": result or [],
            }
        except Exception as exc:
            return {
                "available": False,
                "method": "SonicV2Connector.keys",
                "arguments": {"db_name": db_name, "pattern": pattern},
                "equivalent_redis": eq_redis,
                "result": [],
                "error": str(exc),
            }

    def get_all(self, db_name: str, key: str) -> dict[str, Any]:
        """HGETALL-equivalent via SonicV2Connector."""
        eq_redis = (
            f'redis-cli -n <{db_name}_ID> hgetall "{key}"'
        )
        try:
            self._ensure_connected()
            connector = self.connector

            if hasattr(connector, "get_all"):
                result: dict[str, Any] = connector.get_all(  # type: ignore[union-attr]
                    db_name, key
                )
            else:
                raise RuntimeError(
                    "SonicV2Connector.get_all() is not available."
                )

            return {
                "available": True,
                "method": "SonicV2Connector.get_all",
                "arguments": {"db_name": db_name, "key": key},
                "equivalent_redis": eq_redis,
                "result": result or {},
            }
        except Exception as exc:
            return {
                "available": False,
                "method": "SonicV2Connector.get_all",
                "arguments": {"db_name": db_name, "key": key},
                "equivalent_redis": eq_redis,
                "result": {},
                "error": str(exc),
            }

    def get(
        self, db_name: str, key: str, field: str
    ) -> dict[str, Any]:
        """Get a single field via SonicV2Connector."""
        all_result = self.get_all(db_name, key)
        result = all_result.get("result") or {}

        value = None
        if isinstance(result, dict):
            value = result.get(field)

        return {
            **all_result,
            "method": "SonicV2Connector.get",
            "arguments": {
                "db_name": db_name, "key": key, "field": field,
            },
            "result": value,
        }
