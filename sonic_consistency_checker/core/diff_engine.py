"""DiffEngine — deterministic SONiC consistency checks.

Compares data across SONiC Redis DBs and produces structured Findings.
Does NOT use an LLM. All checks are deterministic and evidence-based.

Step 4A amends:
- Item 4: APPL_DB write-back path covered for oper_status
- Item 3: Route table drift, VLAN membership, LAG member health checks
- Item 5: Route table scan capability
"""

from __future__ import annotations

import logging
from typing import Any

from sonic_consistency_checker.core.models import Finding, PortView

logger = logging.getLogger(__name__)


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
    # Extended checks (Step 4A) — require RedisClient for broad scanning
    # ------------------------------------------------------------------

    def check_all(
        self,
        ports: list[PortView],
        redis_client: Any = None,
    ) -> list[Finding]:
        """Run ALL checks: port checks + route/VLAN/LAG if redis_client provided."""
        findings = self.check_ports(ports)

        if redis_client is not None:
            findings.extend(self.check_route_drift(redis_client))
            findings.extend(self.check_vlan_membership(redis_client))
            findings.extend(self.check_lag_member_health(redis_client))

        return findings

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

        # Item 4 (Step 4A): Also check APPL_DB for oper_status.
        # natsyncd and other services may write ASIC state changes
        # directly to APPL_DB instead of STATE_DB.
        oper = _first_present(
            port.state, ["oper_status", "oper_state", "status"]
        )
        oper_source = "STATE_DB"
        if oper is None:
            oper = _first_present(
                port.app, ["oper_status", "oper_state", "status"]
            )
            oper_source = "APPL_DB"

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
                    f"{oper_source}.oper_status": oper,
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

    # ══════════════════════════════════════════════════════════════════
    # Step 4A — Non-port consistency checks
    # ══════════════════════════════════════════════════════════════════

    # ── Check 7: ROUTE_TABLE_DRIFT (Item 3 + Item 5) ───────────────

    def check_route_drift(self, redis_client: Any) -> list[Finding]:
        """Compare APPL_DB ROUTE_TABLE key count vs ASIC_DB route entry count.

        This is the #1 SONiC operational inconsistency — route table drift
        after warm reboot or orchagent restart.
        """
        findings: list[Finding] = []

        # Count APPL_DB routes
        try:
            appl_routes = redis_client.scan_keys("APPL_DB", "ROUTE_TABLE:*")
            appl_count = len(appl_routes)
        except Exception as exc:
            logger.warning("Could not scan APPL_DB ROUTE_TABLE: %s", exc)
            appl_count = -1

        # Count ASIC_DB route entries
        try:
            asic_routes = redis_client.scan_keys(
                "ASIC_DB", "*SAI_OBJECT_TYPE_ROUTE_ENTRY*"
            )
            asic_count = len(asic_routes)
        except Exception as exc:
            logger.warning("Could not scan ASIC_DB route entries: %s", exc)
            asic_count = -1

        if appl_count < 0 or asic_count < 0:
            findings.append(
                Finding(
                    id="route_table_drift:system",
                    severity="warning",
                    category="ROUTE_TABLE_DRIFT",
                    object_type="route",
                    object_name="system",
                    summary=(
                        "Could not determine route table drift — "
                        "one or both DBs were unreachable."
                    ),
                    evidence={
                        "APPL_DB route count": appl_count if appl_count >= 0 else "scan failed",
                        "ASIC_DB route count": asic_count if asic_count >= 0 else "scan failed",
                    },
                    possible_causes=[
                        "ASIC_DB or APPL_DB unreachable",
                        "Redis connection issue",
                    ],
                    suggested_commands=[
                        'redis-cli -n 0 keys "ROUTE_TABLE:*" | wc -l',
                        'redis-cli -n 1 keys "*SAI_OBJECT_TYPE_ROUTE_ENTRY*" | wc -l',
                        "show ip route summary",
                    ],
                )
            )
            return findings

        if appl_count != asic_count:
            drift = abs(appl_count - asic_count)
            findings.append(
                Finding(
                    id="route_table_drift:system",
                    severity="critical",
                    category="ROUTE_TABLE_DRIFT",
                    object_type="route",
                    object_name="system",
                    summary=(
                        f"Route table drift detected: "
                        f"APPL_DB has {appl_count} routes, "
                        f"ASIC_DB has {asic_count} routes "
                        f"(drift = {drift})."
                    ),
                    evidence={
                        "APPL_DB ROUTE_TABLE count": appl_count,
                        "ASIC_DB route entry count": asic_count,
                        "drift": drift,
                    },
                    possible_causes=[
                        "Orchagent restart — route reconciliation incomplete",
                        "Warm reboot — ASIC state preserved but APPL_DB routes changed",
                        "BGP session flap — routes withdrawn but ASIC not updated",
                        "syncd backlog — ASIC_DB updates queued",
                        "fpmsyncd lag — kernel routes not yet pushed to APPL_DB",
                    ],
                    suggested_commands=[
                        "show ip route summary",
                        "show ip bgp summary",
                        'redis-cli -n 0 keys "ROUTE_TABLE:*" | wc -l',
                        'redis-cli -n 1 keys "*ROUTE_ENTRY*" | wc -l',
                        "docker exec swss supervisorctl status orchagent",
                    ],
                )
            )

        return findings

    # ── Check 8: VLAN_MEMBERSHIP_MISMATCH (Item 3) ─────────────────

    def check_vlan_membership(self, redis_client: Any) -> list[Finding]:
        """Check VLAN membership consistency between CONFIG_DB and APPL_DB.

        CONFIG_DB VLAN_MEMBER says port X is in VLAN 100, but
        APPL_DB VLAN_TABLE may not reflect it.
        """
        findings: list[Finding] = []

        # Scan CONFIG_DB VLAN members
        try:
            config_vlan_keys = redis_client.scan_keys(
                "CONFIG_DB", "VLAN_MEMBER|*"
            )
        except Exception as exc:
            logger.warning("Could not scan CONFIG_DB VLAN_MEMBER: %s", exc)
            return findings

        # Scan APPL_DB VLAN tables
        try:
            app_vlan_keys = redis_client.scan_keys(
                "APPL_DB", "VLAN_TABLE:*"
            )
        except Exception as exc:
            logger.warning("Could not scan APPL_DB VLAN_TABLE: %s", exc)
            app_vlan_keys = []

        if not config_vlan_keys:
            return findings  # No VLANs configured — nothing to check

        # Build set of (vlan, member) from CONFIG_DB
        config_members: set[tuple[str, str]] = set()
        for key in config_vlan_keys:
            # Key format: VLAN_MEMBER|Vlan100|Ethernet0
            parts = key.split("|")
            if len(parts) >= 3 and parts[0] == "VLAN_MEMBER":
                vlan = parts[1]
                member = parts[2]
                config_members.add((vlan, member))

        # Build set of VLANs and their member ports from APPL_DB
        app_members: set[tuple[str, str]] = set()
        vlans_seen: set[str] = set()
        for key in app_vlan_keys:
            # Key format: VLAN_TABLE:Vlan100 or VLAN_TABLE:Vlan100:Ethernet0
            parts = key.split(":")
            if len(parts) >= 2:
                vlan = parts[1]
                vlans_seen.add(vlan)
                # Read members from APPL_DB
                try:
                    vlan_data = redis_client.hgetall("APPL_DB", key)
                    for field_name in vlan_data:
                        if field_name.startswith("member") or field_name == "members":
                            # Member fields may reference port names
                            pass
                    # Also scan for VLAN_MEMBER keys in APPL_DB
                except Exception:
                    pass

        # Alternative approach: scan APPL_DB for VLAN_MEMBER:*
        try:
            app_vlan_member_keys = redis_client.scan_keys(
                "APPL_DB", "VLAN_MEMBER:*"
            )
            for key in app_vlan_member_keys:
                # Key format: VLAN_MEMBER:Vlan100:Ethernet0
                parts = key.split(":")
                if len(parts) >= 3 and parts[0] == "VLAN_MEMBER":
                    vlan = parts[1]
                    member = parts[2]
                    app_members.add((vlan, member))
        except Exception:
            pass

        # Compare
        missing_in_app = config_members - app_members
        extra_in_app = app_members - config_members

        for vlan, member in sorted(missing_in_app):
            findings.append(
                Finding(
                    id=f"vlan_membership_mismatch:{vlan}:{member}",
                    severity="warning",
                    category="VLAN_MEMBERSHIP_MISMATCH",
                    object_type="vlan",
                    object_name=f"{vlan}/{member}",
                    summary=(
                        f"Port {member} is in VLAN {vlan} per CONFIG_DB "
                        f"but not found in APPL_DB VLAN_MEMBER."
                    ),
                    evidence={
                        "CONFIG_DB VLAN_MEMBER": f"{vlan}|{member}",
                        "APPL_DB VLAN_MEMBER": "missing",
                    },
                    possible_causes=[
                        "vlanmgrd has not processed the VLAN config change yet",
                        "vlanmgrd service is down or restarting",
                        "VLAN creation failed",
                        "Schema/key separator mismatch",
                    ],
                    suggested_commands=[
                        f'redis-cli -n 4 hgetall "VLAN_MEMBER|{vlan}|{member}"',
                        f'redis-cli -n 0 hgetall "VLAN_MEMBER:{vlan}:{member}"',
                        f"show vlan brief",
                        "docker exec swss supervisorctl status vlanmgrd",
                    ],
                )
            )

        for vlan, member in sorted(extra_in_app):
            findings.append(
                Finding(
                    id=f"vlan_membership_extra:{vlan}:{member}",
                    severity="info",
                    category="VLAN_MEMBERSHIP_MISMATCH",
                    object_type="vlan",
                    object_name=f"{vlan}/{member}",
                    summary=(
                        f"Port {member} appears in APPL_DB VLAN_MEMBER "
                        f"for {vlan} but no matching CONFIG_DB entry found."
                    ),
                    evidence={
                        "CONFIG_DB VLAN_MEMBER": "missing",
                        "APPL_DB VLAN_MEMBER": f"{vlan}/{member}",
                    },
                    possible_causes=[
                        "Stale APPL_DB state after VLAN deletion",
                        "Manual Redis write without config",
                        "Schema/key separator mismatch",
                    ],
                    suggested_commands=[
                        f'redis-cli -n 0 keys "VLAN_MEMBER:{vlan}:*"',
                        f"show vlan brief",
                    ],
                )
            )

        return findings

    # ── Check 9: LAG_MEMBER_MISMATCH (Item 3) ──────────────────────

    def check_lag_member_health(self, redis_client: Any) -> list[Finding]:
        """Check LAG member consistency between CONFIG_DB and APPL_DB.

        CONFIG_DB PORTCHANNEL member list vs APPL_DB LAG_TABLE state.
        """
        findings: list[Finding] = []

        # Scan CONFIG_DB PORTCHANNEL
        try:
            config_lag_keys = redis_client.scan_keys(
                "CONFIG_DB", "PORTCHANNEL|*"
            )
        except Exception as exc:
            logger.warning("Could not scan CONFIG_DB PORTCHANNEL: %s", exc)
            return findings

        if not config_lag_keys:
            return findings  # No LAGs configured

        # Scan APPL_DB LAG_TABLE
        try:
            app_lag_keys = redis_client.scan_keys(
                "APPL_DB", "LAG_TABLE:*"
            )
        except Exception as exc:
            logger.warning("Could not scan APPL_DB LAG_TABLE: %s", exc)
            app_lag_keys = []

        for key in config_lag_keys:
            # Key format: PORTCHANNEL|PortChannel001
            parts = key.split("|")
            if len(parts) < 2:
                continue
            lag_name = parts[1]

            # Read CONFIG_DB LAG members
            try:
                config_data = redis_client.hgetall("CONFIG_DB", key)
            except Exception:
                config_data = {}

            config_member_list = config_data.get(
                "members", config_data.get("member", "")
            )
            config_members: set[str] = set()
            if config_member_list:
                config_members = set(
                    m.strip() for m in config_member_list.split(",") if m.strip()
                )

            # Read APPL_DB LAG state
            app_members: set[str] = set()
            for ak in app_lag_keys:
                if lag_name in ak:
                    try:
                        app_data = redis_client.hgetall("APPL_DB", ak)
                        for field_name, field_val in app_data.items():
                            if "member" in field_name.lower():
                                app_members.add(field_val.strip())
                    except Exception:
                        pass

            # Compare
            if config_members and app_members:
                missing = config_members - app_members
                extra = app_members - config_members

                for member in sorted(missing):
                    findings.append(
                        Finding(
                            id=f"lag_member_mismatch:{lag_name}:{member}",
                            severity="warning",
                            category="LAG_MEMBER_MISMATCH",
                            object_type="lag",
                            object_name=f"{lag_name}/{member}",
                            summary=(
                                f"Port {member} is a member of LAG {lag_name} "
                                f"in CONFIG_DB but not found in APPL_DB."
                            ),
                            evidence={
                                f"CONFIG_DB.{key}.members": list(config_members),
                                "APPL_DB LAG_TABLE members": list(app_members),
                                "missing": list(missing),
                            },
                            possible_causes=[
                                "teamsyncd has not processed the LAG config yet",
                                "teamd service is down or restarting",
                                "LAG creation failed — member ports may be down",
                                "Schema/key separator mismatch",
                            ],
                            suggested_commands=[
                                f'redis-cli -n 4 hgetall "{key}"',
                                f'redis-cli -n 0 hgetall "LAG_TABLE:{lag_name}"',
                                f"show interfaces portchannel",
                                "docker exec teamd supervisorctl status teamd",
                            ],
                        )
                    )

                for member in sorted(extra):
                    findings.append(
                        Finding(
                            id=f"lag_member_extra:{lag_name}:{member}",
                            severity="info",
                            category="LAG_MEMBER_MISMATCH",
                            object_type="lag",
                            object_name=f"{lag_name}/{member}",
                            summary=(
                                f"Port {member} appears in APPL_DB LAG_TABLE "
                                f"for {lag_name} but not in CONFIG_DB."
                            ),
                            evidence={
                                f"CONFIG_DB.{key}.members": list(config_members),
                                "APPL_DB LAG_TABLE members": list(app_members),
                                "extra": list(extra),
                            },
                            possible_causes=[
                                "Stale APPL_DB state after LAG member removal",
                                "Manual Redis write without config",
                                "teamsyncd stale state",
                            ],
                            suggested_commands=[
                                f'redis-cli -n 0 keys "LAG_TABLE:{lag_name}*"',
                                f"show interfaces portchannel",
                            ],
                        )
                    )

            elif config_members and not app_members:
                findings.append(
                    Finding(
                        id=f"lag_missing_app:{lag_name}",
                        severity="warning",
                        category="LAG_MEMBER_MISMATCH",
                        object_type="lag",
                        object_name=lag_name,
                        summary=(
                            f"LAG {lag_name} has {len(config_members)} members "
                            f"in CONFIG_DB but no APPL_DB LAG_TABLE state found."
                        ),
                        evidence={
                            f"CONFIG_DB.{key}.members": list(config_members),
                            "APPL_DB LAG_TABLE": "not found",
                        },
                        possible_causes=[
                            "teamd service is not running",
                            "teamsyncd has not processed the LAG config",
                            "LAG has not been created yet",
                        ],
                        suggested_commands=[
                            "show interfaces portchannel",
                            "docker exec teamd supervisorctl status teamd",
                            f'redis-cli -n 0 keys "LAG_TABLE:*"',
                        ],
                    )
                )

        return findings
