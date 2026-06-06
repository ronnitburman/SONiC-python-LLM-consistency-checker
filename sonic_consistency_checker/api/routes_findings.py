"""API routes for Step 4 — Consistency Check Findings."""

from __future__ import annotations

from fastapi import APIRouter

from sonic_consistency_checker.core.models import FindingsResponse
from sonic_consistency_checker.sonic.ports import PortService

router = APIRouter(prefix="/api", tags=["findings"])

# Shared port service — created once at module load
port_service = PortService()


@router.get("/findings", response_model=FindingsResponse)
async def all_findings() -> FindingsResponse:
    """Return all consistency findings across all discovered ports."""
    port_views = port_service.list_port_views()

    all_f: list = []
    for pv in port_views:
        all_f.extend(pv.findings)

    return FindingsResponse(findings=all_f)


@router.get("/ports/{port_name}/findings", response_model=FindingsResponse)
async def port_findings(port_name: str) -> FindingsResponse:
    """Return consistency findings for a single port."""
    view = port_service.get_port_view(port_name)
    return FindingsResponse(findings=view.findings)
