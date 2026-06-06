"""PortService — normalized cross-DB SONiC port view.

Builds a PortView that gathers port-related data from CONFIG_DB, APPL_DB,
STATE_DB, COUNTERS_DB, ASIC_DB, and transceiver keys.
"""

from __future__ import annotations

import logging
from typing import Any

from sonic_consistency_checker.core.models import PortView, PortsListResponse
from sonic_consistency_checker.core.redis_client import SonicRedisClient
from sonic_consistency_checker.core.diff_engine import DiffEngine

logger = logging.getLogger(__name__)

# Maximum number of counter/ASIC keys to collect per port
_MAX_BEST_EFFORT_KEYS = 20


def _separator_variants(db_name: str, client: SonicRedisClient) -> list[str]:
    """Return separator candidates for a DB: configured separator first, then the other."""
    configured = client.databases.get(db_name)
    preferred = configured.separator if configured else ":"
    fallback = "|" if preferred == ":" else ":"
    return [preferred, fallback]


class PortService:
    """Builds normalized port views from raw SONiC Redis data.

    Uses the dynamic DB config (Step 1) and Redis explorer (Step 2).
    No DB IDs are hardcoded.
    """

    def __init__(self, redis_client: SonicRedisClient | None = None) -> None:
        self.redis_client = redis_client or SonicRedisClient()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_config_ports(self) -> PortsListResponse:
        """Discover port names by scanning CONFIG_DB PORT|* keys."""
        keys = self.redis_client.scan_keys("CONFIG_DB", "PORT|*")

        ports: list[str] = []
        for key in keys:
            parts = key.split("|", 1)
            if len(parts) == 2 and parts[0] == "PORT":
                ports.append(parts[1])

        ports.sort()
        return PortsListResponse(
            ports=ports,
            source="CONFIG_DB:PORT|*",
        )

    def get_port_view(self, port_name: str) -> PortView:
        """Build a normalized cross-DB view for a single port."""
        raw_keys: dict[str, list[str]] = {}

        # ── CONFIG_DB ──────────────────────────────────────────────
        config_key = f"PORT|{port_name}"
        config = self._safe_hgetall("CONFIG_DB", config_key)
        if config:
            raw_keys.setdefault("CONFIG_DB", []).append(config_key)

        # ── APPL_DB ────────────────────────────────────────────────
        app_key, app = self._first_existing_hash(
            "APPL_DB",
            [f"PORT_TABLE{sep}{port_name}" for sep in _separator_variants("APPL_DB", self.redis_client)],
        )
        if app_key:
            raw_keys.setdefault("APPL_DB", []).append(app_key)

        # ── STATE_DB ───────────────────────────────────────────────
        state_key, state = self._first_existing_hash(
            "STATE_DB",
            [f"PORT_TABLE{sep}{port_name}" for sep in _separator_variants("STATE_DB", self.redis_client)],
        )
        if state_key:
            raw_keys.setdefault("STATE_DB", []).append(state_key)

        # ── Transceiver keys (STATE_DB) ────────────────────────────
        transceiver: dict[str, Any] = {}
        trans_keys = [
            f"TRANSCEIVER_INFO|{port_name}",
            f"TRANSCEIVER_DOM_SENSOR|{port_name}",
            f"TRANSCEIVER_STATUS|{port_name}",
        ]
        for tk in trans_keys:
            fields = self._safe_hgetall("STATE_DB", tk)
            if fields:
                transceiver[tk] = fields
                raw_keys.setdefault("STATE_DB", []).append(tk)

        # ── COUNTERS_DB (best-effort) ──────────────────────────────
        counters: dict[str, Any] = {}
        try:
            counter_keys = self.redis_client.scan_keys(
                "COUNTERS_DB", f"*{port_name}*"
            )
            for ck in counter_keys[:_MAX_BEST_EFFORT_KEYS]:
                fields = self._safe_hgetall("COUNTERS_DB", ck)
                counters[ck] = fields if fields else {}
                raw_keys.setdefault("COUNTERS_DB", []).append(ck)
        except Exception:
            logger.debug("COUNTERS_DB scan skipped for %s", port_name)

        # ── ASIC_DB (best-effort) ─────────────────────────────────
        asic: dict[str, Any] = {}
        try:
            # TODO: Map Ethernet port name to ASIC OID through
            #       COUNTERS_DB/VIDTORID mappings in a later step.
            asic_keys = self.redis_client.scan_keys(
                "ASIC_DB", "*SAI_OBJECT_TYPE_PORT*"
            )
            for ak in asic_keys[:_MAX_BEST_EFFORT_KEYS]:
                fields = self._safe_hgetall("ASIC_DB", ak)
                asic[ak] = fields if fields else {}
                raw_keys.setdefault("ASIC_DB", []).append(ak)
        except Exception:
            logger.debug("ASIC_DB scan skipped for %s", port_name)

        # ── Build view & run consistency checks ───────────────────
        view = PortView(
            name=port_name,
            config=config,
            app=app,
            state=state,
            asic=asic,
            counters=counters,
            transceiver=transceiver,
            raw_keys=raw_keys,
        )
        view.findings = DiffEngine().check_port(view)
        return view

    # ------------------------------------------------------------------
    # Bulk helpers
    # ------------------------------------------------------------------

    def list_port_views(self) -> list[PortView]:
        """Return full PortView objects for all discovered ports."""
        ports_response = self.list_config_ports()
        return [self.get_port_view(port) for port in ports_response.ports]


    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _safe_hgetall(self, db_name: str, key: str) -> dict[str, str]:
        """Read hash fields, returning {} on any error."""
        try:
            return self.redis_client.hgetall(db_name, key)
        except Exception:
            return {}

    def _first_existing_hash(
        self,
        db_name: str,
        candidate_keys: list[str],
    ) -> tuple[str | None, dict[str, str]]:
        """Try each candidate key and return the first hash with fields.

        Returns (key_name, fields) or (None, {}) if none found.
        """
        for key in candidate_keys:
            try:
                ktype = self.redis_client.key_type(db_name, key)
            except Exception:
                continue

            if ktype == "none":
                continue

            if ktype == "hash":
                fields = self._safe_hgetall(db_name, key)
                if fields:
                    return key, fields

        return None, {}
