"""Pydantic models for SONiC consistency checker."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Step 2 models ──────────────────────────────────────────────────────


class DbSizeSummary(BaseModel):
    """Size summary for a single SONiC Redis database.

    When `error` is set, the connection/query failed — `size` will be -1
    and the error message explains why.  A size of 0 means the DB was
    reached successfully but is empty; -1 *without* an error field means
    the legacy path (treat as suspicious).
    """

    db_name: str
    db_id: int
    size: int
    error: str | None = None


class SonicDbKey(BaseModel):
    """Full key info: type, hash fields, and the equivalent redis-cli command."""

    db_name: str
    db_id: int
    key: str
    key_type: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)
    equivalent_redis: str | None = None


class DbKeysResponse(BaseModel):
    """Result of a key scan with pattern."""

    db_name: str
    db_id: int
    pattern: str
    keys: list[str]
    equivalent_redis: str


class KeyTypeResponse(BaseModel):
    """Result of a TYPE query."""

    db_name: str
    key: str
    key_type: str


# ── Step 3 models ──────────────────────────────────────────────────────


class PortView(BaseModel):
    """Normalized cross-DB view of a single SONiC port."""

    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    app: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)
    asic: dict[str, Any] = Field(default_factory=dict)
    counters: dict[str, Any] = Field(default_factory=dict)
    transceiver: dict[str, Any] = Field(default_factory=dict)
    raw_keys: dict[str, list[str]] = Field(default_factory=dict)
    findings: list[Finding] = Field(default_factory=list)


class PortsListResponse(BaseModel):
    """List of discovered port names and their discovery source."""

    ports: list[str]
    source: str


# ── Step 4 models ──────────────────────────────────────────────────────


class Finding(BaseModel):
    """A single consistency finding with evidence."""

    id: str
    severity: Literal["info", "warning", "critical"]
    category: str
    object_type: str
    object_name: str
    summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    possible_causes: list[str] = Field(default_factory=list)
    suggested_commands: list[str] = Field(default_factory=list)


class FindingsResponse(BaseModel):
    """A collection of consistency findings."""

    findings: list[Finding]


# ── Step 4A models (Route / VLAN / LAG / Summary) ────────────────────


class RouteDriftSummary(BaseModel):
    """Summary of route table drift between APPL_DB and ASIC_DB."""

    appl_route_count: int
    asic_route_count: int
    drift: int
    status: Literal["ok", "drift", "unknown"]


class VlanMembershipSummary(BaseModel):
    """Summary of VLAN membership consistency."""

    config_vlan_count: int
    app_vlan_count: int
    vlans_with_mismatch: list[str] = Field(default_factory=list)
    status: Literal["ok", "mismatch", "unknown"]


class LagMemberSummary(BaseModel):
    """Summary of LAG member health."""

    config_lag_count: int
    app_lag_count: int
    lags_with_mismatch: list[str] = Field(default_factory=list)
    status: Literal["ok", "mismatch", "unknown"]


class DiagnosticSummary(BaseModel):
    """Aggregated diagnostic summary / health overview.

    Combines port findings, route drift, VLAN membership, and LAG member
    health into a single dashboard view.  Each subsystem has its own
    status (``ok``, ``warning``, ``critical``) and the overall health
    score is a quick 0–100 grade.
    """

    # Severity counts (across all findings — ports, routes, VLANs, LAGs)
    total_findings: int
    critical_count: int
    warning_count: int
    info_count: int

    # Category groups
    categories: dict[str, int] = Field(default_factory=dict)

    # Subsystem summaries
    port_checks: dict[str, int] = Field(default_factory=dict)
    route_drift: RouteDriftSummary | None = None
    vlan_membership: VlanMembershipSummary | None = None
    lag_member_health: LagMemberSummary | None = None

    # Overall health
    overall_health_score: int = Field(
        default=100,
        ge=0,
        le=100,
        description="0 = critical issues, 100 = all clear",
    )
    overall_status: Literal["healthy", "warning", "critical"] = "healthy"
