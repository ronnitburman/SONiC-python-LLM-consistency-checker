"""DiffEngine — deterministic SONiC consistency checks.

Compares data across SONiC Redis DBs and produces structured Findings.
Does NOT use an LLM. All checks are deterministic and evidence-based.
"""

from __future__ import annotations

from typing import Any

from sonic_consistency_checker.core.models import Finding, PortView


def _norm(value: object) -> str:
    """Normalize a value for case-insensitive comparison."""
    return str(value).strip().lower()


def _finding_id(category: str, object_name: str) -> str:
    """Create a stable, unique finding ID."""
    return f"{category.lower()}:{object_name}"


def _first_present(data: dict[str, Any], keys: list[str]) -> object | None:
    """Return the first key's value found in *data*, or None."""
    for key in keys:
        if key in data:
            return data[key]
    return None


# ── Evidence-only helpers (dry) ─────────────────────────────────────────


def _evidence_db_entry(
    prefix: str, db_data: dict[str, Any], key: str
) -> dict[str, Any]:
    """Build an evidence dict with dotted-path keys like CONFIG_DB.mtu."""
    return {f"{prefix}.{k}": v for k, v in db_data.items()}


class DiffEngine:
    """Runs deterministic consistency checks on PortView objects."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_port(self, port: PortView) -> list[Finding]:
        """Run all checks on a single port view."""
        findings: list[Finding] = []

        findings.extend(self._check_missing_state(port))
        findings.extend(self._check_admin_up_oper_down(port))
        findings.extend(self._check_mtu_mismatch(port))
        findings.extend(self._check_speed_mismatch(port))
        findings.extend(self._check_counters_missing(port))
        findings.extend(self._check_transceiver_missing(port))

        return findings

    def check_ports(self, ports: list[PortView]) -> list[Finding]:
        """Run all checks on a list of port views."""
        all_findings: list[Finding] = []
        for port in ports:
            all_findings.extend(self.check_port(port))
        return all_findings

    # ------------------------------------------------------------------
    # Check 1: PORT_MISSING_IN_STATE_DB
    # ------------------------------------------------------------------

    def _check_missing_state(self, port: PortView) -> list[Finding]:
        if not port.config:
            return []
        if port.state:
            return []

        return [
            Finding(
                id=_finding_id("PORT_MISSING_IN_STATE_DB", port.name),
                severity="info",
                category="PORT_MISSING_IN_STATE_DB",
                object_type="port",
                object_name=port.name,
                summary=(
                    "Port exists in CONFIG_DB but no runtime state "
                    "was found in STATE_DB."
                ),
                evidence={
                    "CONFIG_DB": port.config,
                    "STATE_DB": "No PORT_TABLE state found",
                    "raw_keys": port.raw_keys,
                },
                possible_causes=[
                    "Expected in limited SONiC VS environments",
                    "Runtime state not populated yet",
                    "Port service or platform service issue",
                    "Schema/key separator mismatch",
                ],
                suggested_commands=[
                    f'redis-cli -n <CONFIG_DB_ID> hgetall "PORT|{port.name}"',
                    f'redis-cli -n <STATE_DB_ID> hgetall '
                    f'"PORT_TABLE|{port.name}"',
                    f'redis-cli -n <STATE_DB_ID> hgetall '
                    f'"PORT_TABLE:{port.name}"',
                    "show interfaces status",
                ],
            )
        ]

    # ------------------------------------------------------------------
    # Check 2: PORT_ADMIN_UP_OPER_DOWN
    # ------------------------------------------------------------------

    def _check_admin_up_oper_down(self, port: PortView) -> list[Finding]:
        admin = _norm(port.config.get("admin_status", ""))
        if admin != "up":
            return []

        oper = _first_present(
            port.state, ["oper_status", "oper_state", "status"]
        )
        if _norm(oper) != "down":
            return []

        return [
            Finding(
                id=_finding_id("PORT_ADMIN_UP_OPER_DOWN", port.name),
                severity="warning",
                category="PORT_ADMIN_UP_OPER_DOWN",
                object_type="port",
                object_name=port.name,
                summary=(
                    "Port is administratively up but operationally down."
                ),
                evidence={
                    f"CONFIG_DB.PORT|{port.name}.admin_status": port.config.get(
                        "admin_status"
                    ),
                    "STATE_DB.oper_status": oper,
                    "raw_keys": port.raw_keys,
                },
                possible_causes=[
                    "Cable unplugged",
                    "Transceiver missing or faulty",
                    "Remote peer down",
                    "Speed mismatch",
                    "FEC mismatch",
                    "Platform driver issue",
                    "Optical signal issue",
                ],
                suggested_commands=[
                    "show interfaces status",
                    "show interfaces transceiver presence",
                    f"show interfaces transceiver eeprom {port.name}",
                    f'redis-cli -n <CONFIG_DB_ID> hgetall "PORT|{port.name}"',
                    f'redis-cli -n <STATE_DB_ID> hgetall '
                    f'"PORT_TABLE|{port.name}"',
                ],
            )
        ]

    # ------------------------------------------------------------------
    # Check 3: PORT_MTU_MISMATCH
    # ------------------------------------------------------------------

    def _check_mtu_mismatch(self, port: PortView) -> list[Finding]:
        config_mtu = port.config.get("mtu")
        app_mtu = port.app.get("mtu")

        if config_mtu is None or app_mtu is None:
            return []
        if str(config_mtu) == str(app_mtu):
            return []

        return [
            Finding(
                id=_finding_id("PORT_MTU_MISMATCH", port.name),
                severity="warning",
                category="PORT_MTU_MISMATCH",
                object_type="port",
                object_name=port.name,
                summary="Port MTU differs between CONFIG_DB and APPL_DB.",
                evidence={
                    "CONFIG_DB.mtu": config_mtu,
                    "APPL_DB.mtu": app_mtu,
                    "raw_keys": port.raw_keys,
                },
                possible_causes=[
                    "Configuration has not propagated",
                    "SWSS/orchagent processing delay",
                    "Schema or key mismatch",
                    "Stale DB state",
                ],
                suggested_commands=[
                    f'redis-cli -n <CONFIG_DB_ID> hgetall "PORT|{port.name}"',
                    f'redis-cli -n <APPL_DB_ID> hgetall '
                    f'"PORT_TABLE:{port.name}"',
                    "show interfaces status",
                ],
            )
        ]

    # ------------------------------------------------------------------
    # Check 4: PORT_SPEED_MISMATCH
    # ------------------------------------------------------------------

    def _check_speed_mismatch(self, port: PortView) -> list[Finding]:
        config_speed = port.config.get("speed")
        app_speed = port.app.get("speed")

        if config_speed is None or app_speed is None:
            return []
        if str(config_speed) == str(app_speed):
            return []

        return [
            Finding(
                id=_finding_id("PORT_SPEED_MISMATCH", port.name),
                severity="warning",
                category="PORT_SPEED_MISMATCH",
                object_type="port",
                object_name=port.name,
                summary=(
                    "Port speed differs between CONFIG_DB and APPL_DB."
                ),
                evidence={
                    "CONFIG_DB.speed": config_speed,
                    "APPL_DB.speed": app_speed,
                    "raw_keys": port.raw_keys,
                },
                possible_causes=[
                    "Configuration has not propagated",
                    "Unsupported speed",
                    "Platform limitation",
                    "Transceiver does not support configured speed",
                    "FEC/speed negotiation issue",
                ],
                suggested_commands=[
                    f'redis-cli -n <CONFIG_DB_ID> hgetall "PORT|{port.name}"',
                    f'redis-cli -n <APPL_DB_ID> hgetall '
                    f'"PORT_TABLE:{port.name}"',
                    f"show interfaces transceiver eeprom {port.name}",
                ],
            )
        ]

    # ------------------------------------------------------------------
    # Check 5: PORT_COUNTERS_MISSING
    # ------------------------------------------------------------------

    def _check_counters_missing(self, port: PortView) -> list[Finding]:
        if port.counters:
            return []

        return [
            Finding(
                id=_finding_id("PORT_COUNTERS_MISSING", port.name),
                severity="info",
                category="PORT_COUNTERS_MISSING",
                object_type="port",
                object_name=port.name,
                summary=(
                    "No direct COUNTERS_DB data was found for this port."
                ),
                evidence={
                    "COUNTERS_DB": (
                        "No direct counter keys matched this port name"
                    ),
                    "raw_keys": port.raw_keys,
                },
                possible_causes=[
                    "Expected in some virtual SONiC environments",
                    "Counters may be indexed by OID rather than port name",
                    "Counter service may not be running",
                    "OID mapping not implemented yet in this tool",
                ],
                suggested_commands=[
                    f'redis-cli -n <COUNTERS_DB_ID> scan 0 match '
                    f'"*{port.name}*" count 100',
                    'redis-cli -n <COUNTERS_DB_ID> scan 0 match '
                    '"COUNTERS*" count 100',
                ],
            )
        ]

    # ------------------------------------------------------------------
    # Check 6: TRANSCEIVER_INFO_MISSING
    # ------------------------------------------------------------------

    def _check_transceiver_missing(self, port: PortView) -> list[Finding]:
        if port.transceiver:
            return []

        return [
            Finding(
                id=_finding_id("TRANSCEIVER_INFO_MISSING", port.name),
                severity="info",
                category="TRANSCEIVER_INFO_MISSING",
                object_type="port",
                object_name=port.name,
                summary=(
                    "No transceiver information was found for this port."
                ),
                evidence={
                    "STATE_DB.transceiver": (
                        "No TRANSCEIVER_INFO or DOM sensor keys found"
                    ),
                    "raw_keys": port.raw_keys,
                },
                possible_causes=[
                    "Expected in SONiC VS or virtual environments",
                    "Port may not have a pluggable transceiver",
                    "Platform service may not be publishing transceiver state",
                    "Transceiver may be absent",
                ],
                suggested_commands=[
                    "show interfaces transceiver presence",
                    f"show interfaces transceiver eeprom {port.name}",
                    f'redis-cli -n <STATE_DB_ID> hgetall '
                    f'"TRANSCEIVER_INFO|{port.name}"',
                    f'redis-cli -n <STATE_DB_ID> hgetall '
                    f'"TRANSCEIVER_DOM_SENSOR|{port.name}"',
                ],
            )
        ]
