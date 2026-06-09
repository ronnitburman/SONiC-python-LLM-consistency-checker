"""SonicV2Reader — multi-DB access via swsssdk.SonicV2Connector."""

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


class RemoteSonicV2Reader:
    """Access SONiC Redis DBs via SonicV2Connector *inside* the container.

    Same remote-execution pattern as ``RemoteConfigDbReader`` — serialises
    the SDK call, ships it via ``orb exec → docker exec python3 -c``, and
    parses the JSON result.
    """

    def __init__(self, redis_client: SonicRedisClient) -> None:
        self._client = redis_client

    def _run_sdk_code(self, code: str) -> dict[str, Any]:
        """Execute *code* remotely and return the parsed JSON result.

        If the remote container lacks ``swsssdk`` the error is caught and
        returned as ``{available: False, error: ...}``.
        """
        try:
            raw = self._client.run_python_remote(code)
            return json.loads(raw)
        except SonicRedisError as exc:
            return {
                "available": False,
                "method": "SonicV2Connector (remote)",
                "arguments": {},
                "result": {},
                "error": str(exc),
            }

    def keys(self, db_name: str, pattern: str = "*") -> dict[str, Any]:
        """Scan keys in *db_name* matching *pattern* (remote).

        Tries ``swsscommon`` first, falls back to ``swsssdk``.
        """
        code = f'''\
import json
try:
    from swsscommon import swsscommon as _sdk
    _lib = "swsscommon"
except ImportError:
    import swsssdk as _sdk
    _lib = "swsssdk"
c = _sdk.SonicV2Connector()
try:
    result = c.keys("{db_name}", "{pattern}")
except AttributeError:
    result = []
print(json.dumps({{"available": True, "method": f"{{_lib}}.SonicV2Connector.keys (remote)", "arguments": {{"db_name": "{db_name}", "pattern": "{pattern}"}}, "result": result or []}}))'''  # noqa: E501
        return self._run_sdk_code(code)

    def get_all(self, db_name: str, key: str) -> dict[str, Any]:
        """HGETALL-equivalent via SonicV2Connector (remote).

        Tries ``swsscommon`` first, falls back to ``swsssdk``.
        """
        code = f'''\
import json
try:
    from swsscommon import swsscommon as _sdk
    _lib = "swsscommon"
except ImportError:
    import swsssdk as _sdk
    _lib = "swsssdk"
c = _sdk.SonicV2Connector()
try:
    result = c.get_all("{db_name}", "{key}")
except AttributeError:
    result = {{}}
print(json.dumps({{"available": True, "method": f"{{_lib}}.SonicV2Connector.get_all (remote)", "arguments": {{"db_name": "{db_name}", "key": "{key}"}}, "result": result or {{}}}}))'''  # noqa: E501
        return self._run_sdk_code(code)
