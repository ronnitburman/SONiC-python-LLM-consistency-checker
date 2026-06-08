"""SwssCompareService — compare raw Redis vs. SWSS SDK reads."""

from __future__ import annotations

from typing import Any

from sonic_consistency_checker.core.redis_client import SonicRedisClient
from sonic_consistency_checker.swss.config_db import ConfigDbReader


class SwssCompareService:
    """Compares raw Redis HGETALL output with SWSS SDK ConfigDBConnector."""

    def __init__(
        self,
        redis_client: SonicRedisClient | None = None,
        config_reader: ConfigDbReader | None = None,
    ) -> None:
        self.redis_client = redis_client or SonicRedisClient()
        self.config_reader = config_reader or ConfigDbReader()

    def compare_config_entry(
        self, table: str, key: str
    ) -> dict[str, Any]:
        """Read a CONFIG_DB entry via raw Redis AND SWSS SDK, then diff."""
        raw_key = f"{table}|{key}"

        # ── Raw Redis read ─────────────────────────────────────────
        raw_result: dict[str, Any] = {}
        raw_error: str | None = None
        try:
            raw_result = self.redis_client.hgetall("CONFIG_DB", raw_key)
        except Exception as exc:
            raw_error = str(exc)

        # ── SWSS SDK read ──────────────────────────────────────────
        swss_result = self.config_reader.get_entry(table, key)
        swss_fields = swss_result.get("result") or {}

        # ── Comparison ─────────────────────────────────────────────
        raw_keys_set = set(raw_result.keys())
        swss_keys_set = (
            set(swss_fields.keys())
            if isinstance(swss_fields, dict)
            else set()
        )

        same_fields = sorted(
            field
            for field in raw_keys_set & swss_keys_set
            if str(raw_result.get(field)) == str(swss_fields.get(field))
        )

        different_fields = sorted(
            field
            for field in raw_keys_set & swss_keys_set
            if str(raw_result.get(field)) != str(swss_fields.get(field))
        )

        return {
            "table": table,
            "key": key,
            "raw_redis": {
                "raw_key": raw_key,
                "equivalent_redis": (
                    self.redis_client.equivalent_hgetall_command(
                        "CONFIG_DB", raw_key
                    )
                ),
                "result": raw_result,
                "error": raw_error,
            },
            "swss_sdk": swss_result,
            "comparison": {
                "same_fields": same_fields,
                "different_fields": different_fields,
                "missing_in_raw_redis": sorted(swss_keys_set - raw_keys_set),
                "missing_in_swss_sdk": sorted(raw_keys_set - swss_keys_set),
            },
        }
