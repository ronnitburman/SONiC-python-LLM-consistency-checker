"""ConfigDbReader — read CONFIG_DB data through SONiC ConfigDBConnector."""

from __future__ import annotations

import json
from typing import Any

from sonic_consistency_checker.core.redis_client import (
    SonicRedisClient,
    SonicRedisError,
)
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


class RemoteConfigDbReader:
    """Read CONFIG_DB through swsssdk.ConfigDBConnector *inside* the container.

    Instead of importing ``swsssdk`` locally (which only works inside the
    SONiC container), this class serialises the SDK call as a small Python
    script, ships it into the container via ``orb exec → docker exec
    python3 -c``, and parses the JSON result.

    This makes ``sonic-checker swss config-table -m orb_vm_exec`` work
    from any machine that can reach the orb VM.
    """

    def __init__(self, redis_client: SonicRedisClient) -> None:
        self._client = redis_client

    def _run_sdk_code(self, code: str) -> dict[str, Any]:
        """Execute *code* remotely and return the parsed JSON result.

        If the remote container lacks ``swsssdk`` the error is caught and
        returned as ``{available: False, error: ...}`` — the same shape
        as the local ``ConfigDbReader``.
        """
        try:
            raw = self._client.run_python_remote(code)
            return json.loads(raw)
        except SonicRedisError as exc:
            return {
                "available": False,
                "method": "ConfigDBConnector (remote)",
                "arguments": {},
                "result": {},
                "error": str(exc),
            }

    def get_table(self, table_name: str) -> dict[str, Any]:
        """Return all entries in a CONFIG_DB table (remote).

        Tries ``swsscommon`` (modern SONiC) first, falls back to
        ``swsssdk`` (legacy).
        """
        code = f'''\
import json
try:
    from swsscommon import swsscommon as _sdk
    c = _sdk.ConfigDBConnector()
    c.connect()
    result = c.get_table("{table_name}")
    _lib = "swsscommon"
except ImportError:
    import swsssdk as _sdk
    c = _sdk.ConfigDBConnector()
    c.connect()
    result = c.get_table("{table_name}")
    _lib = "swsssdk"
print(json.dumps({{"available": True, "method": f"{{_lib}}.ConfigDBConnector.get_table (remote)", "arguments": {{"table": "{table_name}"}}, "result": result or {{}}}}))'''  # noqa: E501
        return self._run_sdk_code(code)

    def get_entry(self, table_name: str, key: str) -> dict[str, Any]:
        """Return a single CONFIG_DB table entry (remote).

        Tries ``swsscommon`` first, falls back to ``swsssdk``.
        """
        code = f'''\
import json
try:
    from swsscommon import swsscommon as _sdk
    c = _sdk.ConfigDBConnector()
    c.connect()
    result = c.get_entry("{table_name}", "{key}")
    _lib = "swsscommon"
except ImportError:
    import swsssdk as _sdk
    c = _sdk.ConfigDBConnector()
    c.connect()
    result = c.get_entry("{table_name}", "{key}")
    _lib = "swsssdk"
print(json.dumps({{"available": True, "method": f"{{_lib}}.ConfigDBConnector.get_entry (remote)", "arguments": {{"table": "{table_name}", "key": "{key}"}}, "result": result or {{}}}}))'''  # noqa: E501
        return self._run_sdk_code(code)
