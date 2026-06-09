"""SummaryEngine — aggregate findings into a diagnostic health overview.

Item 8 (Step 4A): Produces an aggregated summary from a list of Findings,
including severity counts, category grouping, and a quick health score.

Works both for overall switch health AND for individual port-level summaries.
"""

from __future__ import annotations

from typing import Any

from sonic_consistency_checker.core.models import (
    DiagnosticSummary,
    Finding,
    LagMemberSummary,
    RouteDriftSummary,
    VlanMembershipSummary,
)


class SummaryEngine:
    """Aggregates Findings into a structured diagnostic summary.

    The summary includes:
    - Severity counts (critical / warning / info)
    - Category grouping
    - Subsystem summaries (route drift, VLAN, LAG)
    - Overall health score (0–100)

    Usage::

        summary = SummaryEngine().summarize(findings)
        # Or with optional extra subsystem data:
        summary = SummaryEngine().summarize(findings,
            route_drift_data=...,
            vlan_data=...,
            lag_data=...)
    """

    def summarize(
        self,
        findings: list[Finding],
        route_drift_data: dict[str, Any] | None = None,
        vlan_data: dict[str, Any] | None = None,
        lag_data: dict[str, Any] | None = None,
    ) -> DiagnosticSummary:
        """Build a diagnostic summary from a list of findings.

        Args:
            findings: All findings (can span ports, routes, VLANs, LAGs).
            route_drift_data: Optional dict with keys ``appl_route_count``,
                ``asic_route_count``.
            vlan_data: Optional dict with keys ``config_vlan_count``,
                ``app_vlan_count``, ``vlans_with_mismatch``.
            lag_data: Optional dict with keys ``config_lag_count``,
                ``app_lag_count``, ``lags_with_mismatch``.
        """
        # Severity counts
        critical_count = sum(1 for f in findings if f.severity == "critical")
        warning_count = sum(1 for f in findings if f.severity == "warning")
        info_count = sum(1 for f in findings if f.severity == "info")

        # Category groups
        categories: dict[str, int] = {}
        for f in findings:
            categories[f.category] = categories.get(f.category, 0) + 1

        # Port check counts (filter to port-type findings)
        port_checks: dict[str, int] = {}
        for f in findings:
            if f.object_type == "port":
                port_checks[f.category] = port_checks.get(f.category, 0) + 1

        # Subsystem summaries
        route_drift = self._build_route_drift(findings, route_drift_data)
        vlan_membership = self._build_vlan_summary(findings, vlan_data)
        lag_health = self._build_lag_summary(findings, lag_data)

        # Overall health score
        health_score, overall_status = self._compute_health(
            critical_count, warning_count, info_count
        )

        return DiagnosticSummary(
            total_findings=len(findings),
            critical_count=critical_count,
            warning_count=warning_count,
            info_count=info_count,
            categories=categories,
            port_checks=port_checks,
            route_drift=route_drift,
            vlan_membership=vlan_membership,
            lag_member_health=lag_health,
            overall_health_score=health_score,
            overall_status=overall_status,
        )

    # ── Private helpers ──────────────────────────────────────────────

    @staticmethod
    def _build_route_drift(
        findings: list[Finding],
        extra: dict[str, Any] | None,
    ) -> RouteDriftSummary | None:
        """Build route drift summary from findings and/or extra data."""
        drift_findings = [
            f for f in findings if f.category == "ROUTE_TABLE_DRIFT"
        ]

        if not drift_findings and not extra:
            return None

        if extra:
            appl = extra.get("appl_route_count", -1)
            asic = extra.get("asic_route_count", -1)
        elif drift_findings:
            ev = drift_findings[0].evidence
            appl = ev.get("APPL_DB ROUTE_TABLE count", ev.get("APPL_DB route count", -1))
            asic = ev.get("ASIC_DB route entry count", ev.get("ASIC_DB route count", -1))
        else:
            return None

        if appl < 0 or asic < 0:
            return RouteDriftSummary(
                appl_route_count=appl if appl >= 0 else 0,
                asic_route_count=asic if asic >= 0 else 0,
                drift=0,
                status="unknown",
            )

        drift_val = abs(appl - asic)
        status: str = "ok" if drift_val == 0 else "drift"

        return RouteDriftSummary(
            appl_route_count=appl,
            asic_route_count=asic,
            drift=drift_val,
            status=status,  # type: ignore[arg-type]
        )

    @staticmethod
    def _build_vlan_summary(
        findings: list[Finding],
        extra: dict[str, Any] | None,
    ) -> VlanMembershipSummary | None:
        """Build VLAN membership summary from findings and/or extra data."""
        vlan_findings = [
            f for f in findings if f.category == "VLAN_MEMBERSHIP_MISMATCH"
        ]

        if not vlan_findings and not extra:
            return None

        if extra:
            return VlanMembershipSummary(
                config_vlan_count=extra.get("config_vlan_count", 0),
                app_vlan_count=extra.get("app_vlan_count", 0),
                vlans_with_mismatch=extra.get("vlans_with_mismatch", []),
                status=(
                    "ok"
                    if not extra.get("vlans_with_mismatch")
                    else "mismatch"
                ),
            )

        mismatched = list({f.object_name for f in vlan_findings})
        return VlanMembershipSummary(
            config_vlan_count=0,
            app_vlan_count=0,
            vlans_with_mismatch=mismatched,
            status="mismatch" if mismatched else "ok",
        )

    @staticmethod
    def _build_lag_summary(
        findings: list[Finding],
        extra: dict[str, Any] | None,
    ) -> LagMemberSummary | None:
        """Build LAG member summary from findings and/or extra data."""
        lag_findings = [
            f for f in findings if f.category == "LAG_MEMBER_MISMATCH"
        ]

        if not lag_findings and not extra:
            return None

        if extra:
            return LagMemberSummary(
                config_lag_count=extra.get("config_lag_count", 0),
                app_lag_count=extra.get("app_lag_count", 0),
                lags_with_mismatch=extra.get("lags_with_mismatch", []),
                status=(
                    "ok"
                    if not extra.get("lags_with_mismatch")
                    else "mismatch"
                ),
            )

        mismatched = list({f.object_name for f in lag_findings})
        return LagMemberSummary(
            config_lag_count=0,
            app_lag_count=0,
            lags_with_mismatch=mismatched,
            status="mismatch" if mismatched else "ok",
        )

    @staticmethod
    def _compute_health(
        critical: int, warning: int, info: int
    ) -> tuple[int, str]:
        """Compute an overall health score (0–100).

        All severity levels contribute cumulatively:
        - Each critical: -25 points
        - Each warning: -10 points
        - Each info: -3 points
        """
        score = max(0, 100 - critical * 25 - warning * 10 - info * 3)

        if critical > 0:
            return score, "critical"
        if warning > 0:
            return score, "warning"
        return score, "healthy"
