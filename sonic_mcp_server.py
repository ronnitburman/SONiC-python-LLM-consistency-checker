"""
SONiC MCP Server — exposes sonic-checker diagnostic tools as MCP tools.

Run:  uv run sonic-mcp-server
  or:  python sonic_mcp_server.py

Pi MCP config (in ~/.pi/mcp.json):
{
  "mcpServers": {
    "sonic-checker": {
      "command": "python",
      "args": ["sonic_mcp_server.py"],
      "cwd": "/Users/burman/projects/SONiC-python-LLM-consistency-checker"
    }
  }
}
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from sonic_consistency_checker.core.db_config_loader import SonicDbConfigLoader
from sonic_consistency_checker.core.discovery import SonicDiscoveryService
from sonic_consistency_checker.core.models import Finding
from sonic_consistency_checker.core.redis_client import SonicRedisClient
from sonic_consistency_checker.sonic.ports import PortService

# ── Logging ──────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MCP] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    name="sonic-checker",
    instructions=(
        "SONiC network OS diagnostic tools. "
        "Use these tools to explore SONiC Redis databases, inspect port state, "
        "and run consistency checks across CONFIG_DB, APPL_DB, STATE_DB, "
        "COUNTERS_DB, and ASIC_DB."
    ),
)


# ── helpers ────────────────────────────────────────────────────────────


def _make_client(
    connection_mode: str | None = None,
    container_name: str | None = None,
    orb_vm_name: str | None = None,
) -> SonicRedisClient:
    """Build a SonicRedisClient from optional overrides, falling back to env."""
    from dotenv import load_dotenv
    load_dotenv()

    mode = connection_mode or os.getenv("SONIC_CONNECTION_MODE")
    logger.debug("MCP tool request: mode=%s container=%s", mode, container_name)

    return SonicRedisClient(
        connection_mode=connection_mode or os.getenv("SONIC_CONNECTION_MODE"),
        container_name=container_name or os.getenv("SONIC_CONTAINER_NAME"),
        orb_vm_name=orb_vm_name or os.getenv("SONIC_ORB_VM_NAME"),
    )


def _finding_to_dict(f: Finding) -> dict[str, Any]:
    """Flatten a Finding into a JSON-serialisable dict."""
    return {
        "id": f.id,
        "severity": f.severity,
        "category": f.category,
        "object_type": f.object_type,
        "object_name": f.object_name,
        "summary": f.summary,
        "evidence": f.evidence,
        "possible_causes": f.possible_causes,
        "suggested_commands": f.suggested_commands,
    }


def _build_status(client: SonicRedisClient) -> dict[str, Any]:
    """Return a status blob so the model can tell real data from fallback.

    When ``used_fallback`` is True every result below comes from hard-coded
    defaults — the switch was NOT reached.  The ``warning`` field tells the
    model exactly what to do (pass connection_mode='orb_vm_exec', etc.).
    """
    db_config = client.db_config
    status: dict[str, Any] = {
        "connected_to_switch": not db_config.used_fallback,
        "connection_mode": client.connection_mode,
    }
    if db_config.used_fallback:
        status["warning"] = (
            "FALLBACK DATA — Could not connect to the SONiC switch. "
            "All values below are hardcoded defaults, NOT live switch data. "
            "To reach the switch pass connection_mode='orb_vm_exec' "
            "(for remote lab VMs) or connection_mode='docker_exec' "
            "(for a local Docker SONiC container)."
        )
    if db_config.errors:
        status["config_errors"] = db_config.errors
    return status


# ── Step 1: DB Config ──────────────────────────────────────────────────


@mcp.tool(
    name="sonic_db_config",
    description=(
        "Load and display the dynamic SONiC Redis database configuration "
        "(database_config.json). Shows which DB IDs map to which names "
        "(CONFIG_DB, APPL_DB, STATE_DB, etc.) and their key separators. "
        "Connection mode (connection_mode): 'docker_exec' (local Docker, default), "
        "'orb_vm_exec' (remote SONiC lab VM via orb CLI — use for lab VMs), "
        "'local_redis' (direct Redis), or 'local_filesystem' (JSON dump files). "
        "When querying a remote SONiC lab VM, ALWAYS pass connection_mode='orb_vm_exec'."
    ),
)
def sonic_db_config(
    connection_mode: str | None = None,
    container_name: str | None = None,
    orb_vm_name: str | None = None,
) -> str:
    """Show the SONiC DB configuration."""
    loader = SonicDbConfigLoader(
        connection_mode=connection_mode,
        container_name=container_name,
        orb_vm_name=orb_vm_name,
    )
    config = loader.load()

    result: dict[str, Any] = {
        "_status": {
            "connected_to_switch": not config.used_fallback,
            "connection_mode": loader.connection_mode,
        },
        "source": config.source,
        "used_fallback": config.used_fallback,
        "errors": config.errors,
        "databases": {},
    }
    if config.used_fallback:
        result["_status"]["warning"] = (
            "FALLBACK DATA — Could not connect to the SONiC switch. "
            "All values below are hardcoded defaults, NOT live switch data. "
            "To reach the switch pass connection_mode='orb_vm_exec'."
        )
    if config.errors:
        result["_status"]["config_errors"] = config.errors
    for db_name, db_entry in config.databases.items():
        result["databases"][db_name] = {
            "id": db_entry.id,
            "separator": db_entry.separator,
            "instance": db_entry.instance,
        }

    return json.dumps(result, indent=2)


# ── Step 2: Redis DB Explorer ──────────────────────────────────────────


@mcp.tool(
    name="sonic_list_dbs",
    description=(
        "List all SONiC Redis databases with their key counts. "
        "Returns DB names, IDs, and the number of keys in each. "
        "Connection mode (connection_mode): 'docker_exec' (local Docker, default), "
        "'orb_vm_exec' (remote SONiC lab VM via orb CLI — use for lab VMs), "
        "'local_redis' (direct Redis), or 'local_filesystem' (JSON dump files). "
        "When querying a remote SONiC lab VM, ALWAYS pass connection_mode='orb_vm_exec'."
    ),
)
def sonic_list_dbs(
    connection_mode: str | None = None,
    container_name: str | None = None,
    orb_vm_name: str | None = None,
) -> str:
    """Show all SONiC Redis DBs with sizes."""
    client = _make_client(connection_mode, container_name, orb_vm_name)
    svc = SonicDiscoveryService(redis_client=client)
    sizes = svc.list_db_sizes()
    result: dict[str, Any] = {
        "_status": _build_status(client),
        "databases": [
            {
                "db_name": s.db_name,
                "db_id": s.db_id,
                "size": s.size,
                **({"error": s.error} if s.error else {}),
            }
            for s in sizes
        ],
    }
    return json.dumps(result, indent=2)


@mcp.tool(
    name="sonic_scan_keys",
    description=(
        "Scan keys in a SONiC Redis DB using the SCAN command (safe, never blocks). "
        "Use this to discover what keys exist in any DB. "
        "Common patterns: 'PORT*', 'ROUTE*', 'VLAN*', '*Ethernet0*', or just '*'. "
        "Connection mode (connection_mode): 'docker_exec' (local Docker, default), "
        "'orb_vm_exec' (remote SONiC lab VM via orb CLI — use for lab VMs), "
        "'local_redis' (direct Redis), or 'local_filesystem' (JSON dump files). "
        "When querying a remote SONiC lab VM, ALWAYS pass connection_mode='orb_vm_exec'."
    ),
)
def sonic_scan_keys(
    db_name: str,
    pattern: str = "*",
    connection_mode: str | None = None,
    container_name: str | None = None,
    orb_vm_name: str | None = None,
) -> str:
    """Scan keys in a SONiC DB."""
    client = _make_client(connection_mode, container_name, orb_vm_name)
    svc = SonicDiscoveryService(redis_client=client)
    result = svc.scan_db(db_name, pattern)
    return json.dumps({
        "_status": _build_status(client),
        "db_name": result.db_name,
        "db_id": result.db_id,
        "pattern": result.pattern,
        "keys": result.keys,
        "equivalent_redis": result.equivalent_redis,
    }, indent=2)


@mcp.tool(
    name="sonic_hget",
    description=(
        "Read all hash fields from a specific Redis key using HGETALL. "
        "Returns the key type and all field/value pairs. "
        "Use after sonic_scan_keys to inspect the contents of discovered keys. "
        "Connection mode (connection_mode): 'docker_exec' (local Docker, default), "
        "'orb_vm_exec' (remote SONiC lab VM via orb CLI — use for lab VMs), "
        "'local_redis' (direct Redis), or 'local_filesystem' (JSON dump files). "
        "When querying a remote SONiC lab VM, ALWAYS pass connection_mode='orb_vm_exec'."
    ),
)
def sonic_hget(
    db_name: str,
    key: str,
    connection_mode: str | None = None,
    container_name: str | None = None,
    orb_vm_name: str | None = None,
) -> str:
    """Read all fields from a key."""
    client = _make_client(connection_mode, container_name, orb_vm_name)
    svc = SonicDiscoveryService(redis_client=client)
    result = svc.read_key(db_name, key)
    return json.dumps({
        "_status": _build_status(client),
        "db_name": result.db_name,
        "db_id": result.db_id,
        "key": result.key,
        "key_type": result.key_type,
        "fields": result.fields,
        "equivalent_redis": result.equivalent_redis,
    }, indent=2)


@mcp.tool(
    name="sonic_key_type",
    description=(
        "Show the Redis type of a key (hash, string, set, zset, list, or none). "
        "Use to check if a key exists and what kind of data it holds. "
        "Connection mode (connection_mode): 'docker_exec' (local Docker, default), "
        "'orb_vm_exec' (remote SONiC lab VM via orb CLI — use for lab VMs), "
        "'local_redis' (direct Redis), or 'local_filesystem' (JSON dump files). "
        "When querying a remote SONiC lab VM, ALWAYS pass connection_mode='orb_vm_exec'."
    ),
)
def sonic_key_type(
    db_name: str,
    key: str,
    connection_mode: str | None = None,
    container_name: str | None = None,
    orb_vm_name: str | None = None,
) -> str:
    """Get the type of a key."""
    client = _make_client(connection_mode, container_name, orb_vm_name)
    svc = SonicDiscoveryService(redis_client=client)
    result = svc.key_type(db_name, key)
    return json.dumps({
        "_status": _build_status(client),
        "db_name": result.db_name,
        "key": result.key,
        "key_type": result.key_type,
    }, indent=2)


# ── Step 3: Normalized Port Views ──────────────────────────────────────


@mcp.tool(
    name="sonic_list_ports",
    description=(
        "List all discovered SONiC port names from CONFIG_DB. "
        "Returns port names like Ethernet0, Ethernet4, etc. "
        "Connection mode (connection_mode): 'docker_exec' (local Docker, default), "
        "'orb_vm_exec' (remote SONiC lab VM via orb CLI — use for lab VMs), "
        "'local_redis' (direct Redis), or 'local_filesystem' (JSON dump files). "
        "When querying a remote SONiC lab VM, ALWAYS pass connection_mode='orb_vm_exec'."
    ),
)
def sonic_list_ports(
    connection_mode: str | None = None,
    container_name: str | None = None,
    orb_vm_name: str | None = None,
) -> str:
    """List all ports."""
    client = _make_client(connection_mode, container_name, orb_vm_name)
    svc = PortService(redis_client=client)
    result = svc.list_config_ports()
    return json.dumps({
        "_status": _build_status(client),
        "ports": result.ports,
        "source": result.source,
    }, indent=2)


@mcp.tool(
    name="sonic_get_port_view",
    description=(
        "Get a normalized cross-DB view of a single SONiC port. "
        "Gathers data from CONFIG_DB, APPL_DB, STATE_DB, COUNTERS_DB, "
        "ASIC_DB, plus transceiver info. "
        "This is THE primary diagnostic tool for a port. "
        "It returns: config, app, state, asic, counters, transceiver, "
        "raw_keys, and any consistency findings. "
        "Connection mode (connection_mode): 'docker_exec' (local Docker, default), "
        "'orb_vm_exec' (remote SONiC lab VM via orb CLI — use for lab VMs), "
        "'local_redis' (direct Redis), or 'local_filesystem' (JSON dump files). "
        "When querying a remote SONiC lab VM, ALWAYS pass connection_mode='orb_vm_exec'."
    ),
)
def sonic_get_port_view(
    port_name: str,
    connection_mode: str | None = None,
    container_name: str | None = None,
    orb_vm_name: str | None = None,
) -> str:
    """Get full port view with all cross-DB data."""
    client = _make_client(connection_mode, container_name, orb_vm_name)
    svc = PortService(redis_client=client)
    view = svc.get_port_view(port_name)

    # Build a clean JSON-serialisable dict (avoid nested non-serialisable objects)
    result: dict[str, Any] = {
        "_status": _build_status(client),
        "name": view.name,
        "config": view.config,
        "app": view.app,
        "state": view.state,
        "asic": {k: v for k, v in view.asic.items()},
        "counters": {k: v for k, v in view.counters.items()},
        "transceiver": {k: v for k, v in view.transceiver.items()},
        "raw_keys": view.raw_keys,
        "findings": [_finding_to_dict(f) for f in view.findings],
    }
    return json.dumps(result, indent=2)


# ── Step 4: Consistency Checks ─────────────────────────────────────────


@mcp.tool(
    name="sonic_check_port",
    description=(
        "Run consistency checks on a single SONiC port. "
        "Checks include: missing state, admin-up/oper-down mismatch, "
        "MTU mismatch, speed mismatch, missing counters, missing transceiver. "
        "Each finding includes severity, evidence, possible causes, and "
        "suggested diagnostic commands. "
        "Connection mode (connection_mode): 'docker_exec' (local Docker, default), "
        "'orb_vm_exec' (remote SONiC lab VM via orb CLI — use for lab VMs), "
        "'local_redis' (direct Redis), or 'local_filesystem' (JSON dump files). "
        "When querying a remote SONiC lab VM, ALWAYS pass connection_mode='orb_vm_exec'."
    ),
)
def sonic_check_port(
    port_name: str,
    connection_mode: str | None = None,
    container_name: str | None = None,
    orb_vm_name: str | None = None,
) -> str:
    """Run consistency checks on one port."""
    client = _make_client(connection_mode, container_name, orb_vm_name)
    svc = PortService(redis_client=client)
    view = svc.get_port_view(port_name)
    findings = [_finding_to_dict(f) for f in view.findings]
    return json.dumps({
        "_status": _build_status(client),
        "port": port_name,
        "findings": findings,
    }, indent=2)


@mcp.tool(
    name="sonic_check_all_ports",
    description=(
        "Run consistency checks on ALL discovered SONiC ports. "
        "Returns findings for every port, grouped by port name. "
        "Use this for an overall health check of the switch. "
        "Connection mode (connection_mode): 'docker_exec' (local Docker, default), "
        "'orb_vm_exec' (remote SONiC lab VM via orb CLI — use for lab VMs), "
        "'local_redis' (direct Redis), or 'local_filesystem' (JSON dump files). "
        "When querying a remote SONiC lab VM, ALWAYS pass connection_mode='orb_vm_exec'."
    ),
)
def sonic_check_all_ports(
    connection_mode: str | None = None,
    container_name: str | None = None,
    orb_vm_name: str | None = None,
) -> str:
    """Run consistency checks on all ports."""
    client = _make_client(connection_mode, container_name, orb_vm_name)
    svc = PortService(redis_client=client)
    port_views = svc.list_port_views()

    all_findings: dict[str, list[dict[str, Any]]] = {}
    for pv in port_views:
        all_findings[pv.name] = [_finding_to_dict(f) for f in pv.findings]

    total = sum(len(f) for f in all_findings.values())
    return json.dumps({
        "_status": _build_status(client),
        "total_ports": len(all_findings),
        "total_findings": total,
        "findings_by_port": all_findings,
    }, indent=2)


# ── main ────────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point: run the MCP server.

    Transport is controlled by SONIC_MCP_TRANSPORT env var or --transport flag.
    Default: streamable-http on port 9100.

    Usage:
      python sonic_mcp_server.py                          # streamable-http :9100
      python sonic_mcp_server.py --transport stdio        # stdio (for child process)
      python sonic_mcp_server.py --transport streamable-http --port 9100
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="SONiC MCP Server — diagnostic tools for AI agents"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=os.getenv("SONIC_MCP_TRANSPORT", "streamable-http"),
        help="Transport protocol (default: streamable-http)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("SONIC_MCP_PORT", "9100")),
        help="Port for sse/streamable-http transports (default: 9100)",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("SONIC_MCP_HOST", "127.0.0.1"),
        help="Host to bind (default: 127.0.0.1)",
    )
    args = parser.parse_args()

    # ── Startup banner ──────────────────────────────────────────────
    conn_mode = os.getenv("SONIC_CONNECTION_MODE", "not set")
    container = os.getenv("SONIC_CONTAINER_NAME", "not set")
    logger.info("─" * 50)
    logger.info("MCP Server starting on %s:%d [%s]", args.host, args.port, args.transport)
    logger.info("Conn mode: %s  Container: %s", conn_mode, container)
    logger.info("─" * 50)

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        # Override host/port on the mcp instance for HTTP transports
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
