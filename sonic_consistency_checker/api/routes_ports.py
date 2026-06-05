"""API routes for Step 3 — Normalized Port View."""

from __future__ import annotations

from fastapi import APIRouter

from sonic_consistency_checker.core.models import PortView, PortsListResponse
from sonic_consistency_checker.sonic.ports import PortService

router = APIRouter(prefix="/api/ports", tags=["ports"])

# Shared port service — created once at module load
port_service = PortService()


@router.get("", response_model=PortsListResponse)
async def list_ports() -> PortsListResponse:
    """Return all discovered port names from CONFIG_DB PORT|*."""
    return port_service.list_config_ports()


@router.get("/{port_name}", response_model=PortView)
async def get_port(port_name: str) -> PortView:
    """Return a normalized cross-DB view of a single SONiC port."""
    return port_service.get_port_view(port_name)
