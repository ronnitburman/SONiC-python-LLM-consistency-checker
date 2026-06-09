"""API routes for Step 4 + 4A — Consistency Check Findings & Summary."""

from __future__ import annotations

from fastapi import APIRouter, Query

from sonic_consistency_checker.core.models import (
    DiagnosticSummary,
    FindingsResponse,
    Finding,
)
from sonic_consistency_checker.sonic.ports import PortService
from sonic_consistency_checker.core.diff_engine import DiffEngine
from sonic_consistency_checker.core.summary import SummaryEngine
from sonic_consistency_checker.core.redis_client import SonicRedisClient

router = APIRouter(prefix="/api", tags=["findings"])

# Shared port service — created once at module load
port_service = PortService()


def _get_client() -> SonicRedisClient:
    """Get a Redis client using the same connection settings as port_service."""
    return port_service.redis_client


@router.get("/findings", response_model=FindingsResponse)
async def all_findings(
    extended: bool = Query(
        False,
        description="If true, also run route, VLAN, and LAG checks",
    ),
) -> FindingsResponse:
    """Return all consistency findings across all discovered ports.

    Set ``?extended=true`` to include route drift, VLAN membership,
    and LAG member checks (Step 4A).
    """
    port_views = port_service.list_port_views()

    if extended:
        engine = DiffEngine()
        all_f: list[Finding] = engine.check_all(
            port_views, redis_client=_get_client()
        )
        return FindingsResponse(findings=all_f)

    all_f: list[Finding] = []
    for pv in port_views:
        all_f.extend(pv.findings)

    return FindingsResponse(findings=all_f)


@router.get("/summary", response_model=DiagnosticSummary)
async def diagnostic_summary(
    extended: bool = Query(
        True,
        description="If true, include route, VLAN, and LAG checks",
    ),
) -> DiagnosticSummary:
    """Return a diagnostic health summary across all subsystems.

    Aggregates findings from port checks, route drift, VLAN membership,
    and LAG member health into a single dashboard view (Item 8).
    """
    port_views = port_service.list_port_views()

    if extended:
        client = _get_client()
        engine = DiffEngine()
        all_findings: list[Finding] = engine.check_all(
            port_views, redis_client=client
        )
    else:
        all_findings: list[Finding] = []
        for pv in port_views:
            all_findings.extend(pv.findings)

    summary_engine = SummaryEngine()
    return summary_engine.summarize(all_findings)


@router.get("/ports/{port_name}/findings", response_model=FindingsResponse)
async def port_findings(port_name: str) -> FindingsResponse:
    """Return consistency findings for a single port."""
    view = port_service.get_port_view(port_name)
    return FindingsResponse(findings=view.findings)


@router.get(
    "/ports/{port_name}/summary", response_model=DiagnosticSummary
)
async def port_summary(port_name: str) -> DiagnosticSummary:
    """Return a diagnostic summary for a single port (Item 8)."""
    view = port_service.get_port_view(port_name)
    summary_engine = SummaryEngine()
    return summary_engine.summarize(view.findings)
