"""LangChain tools for the SONiC AI agent.

Two categories:
1. Skill tools — list_skills, read_skill (load domain knowledge on demand)
2. MCP tools — all 9 SONiC diagnostic tools bridged to the MCP server
"""

from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

from sonic_consistency_checker.ai.skill_loader import list_skills, read_skill
from sonic_consistency_checker.ai.mcp_bridge import call_mcp_tool

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Skill tools
# ══════════════════════════════════════════════════════════════════════


@tool
def read_skill_tool(name: str) -> str:
    """Load a SONiC domain knowledge document.

    Use this BEFORE diagnosing SONiC issues if you need to understand:
    - SONiC Redis database layout (which DB stores what, key separators)
    - Container architecture (swss, syncd, bgp, database roles)
    - Service workflows (how config flows from CONFIG_DB → APPL_DB → ASIC_DB)
    - Debugging patterns and common CLI commands

    Available skills are discovered automatically. Call list_skills_tool()
    first to see what's available.

    Args:
        name: Skill name, e.g. "sonic" for the main SONiC knowledge base.
    """
    return read_skill(name)


@tool
def list_skills_tool() -> str:
    """List all available skill documents the agent can load.

    Returns a JSON list with skill names and sizes.
    Use this to discover what domain knowledge is available before calling
    read_skill_tool().
    """
    skills = list_skills()
    if not skills:
        return "No skills found."
    return json.dumps(
        [{"name": s.name, "size_kb": s.size // 1024} for s in skills],
        indent=2,
    )


# ══════════════════════════════════════════════════════════════════════
# MCP diagnostic tools
# ══════════════════════════════════════════════════════════════════════


@tool
def sonic_db_config() -> str:
    """Show the dynamic SONiC Redis database configuration.

    Returns DB IDs, key separators, and instance names from the switch's
    database_config.json.  Use this to understand which DB IDs map to
    which logical names (CONFIG_DB, APPL_DB, STATE_DB, etc.).
    """
    return call_mcp_tool("sonic_db_config", {})


@tool
def sonic_list_dbs() -> str:
    """List all SONiC Redis databases with their key counts.

    Returns a summary of every DB on the switch and how many keys each has.
    Use for a quick overview of switch state density.
    """
    return call_mcp_tool("sonic_list_dbs", {})


@tool
def sonic_scan_keys(db_name: str, pattern: str = "*") -> str:
    """Scan keys in a SONiC Redis DB using SCAN (safe, never blocks).

    Args:
        db_name: SONiC DB name, e.g. CONFIG_DB, APPL_DB, STATE_DB, ASIC_DB.
        pattern: Glob pattern, e.g. "PORT*", "ROUTE*", "VLAN*".

    Use this to discover what keys exist in any DB.
    """
    return call_mcp_tool(
        "sonic_scan_keys", {"db_name": db_name, "pattern": pattern}
    )


@tool
def sonic_hget(db_name: str, key: str) -> str:
    """Read all hash fields from a specific Redis key using HGETALL.

    Args:
        db_name: SONiC DB name, e.g. CONFIG_DB.
        key: Redis key, e.g. "PORT|Ethernet0" or "ROUTE_TABLE:0.0.0.0/0".

    Use after sonic_scan_keys to inspect the contents of discovered keys.
    """
    return call_mcp_tool(
        "sonic_hget", {"db_name": db_name, "key": key}
    )


@tool
def sonic_key_type(db_name: str, key: str) -> str:
    """Show the Redis type of a key (hash, string, set, zset, list, or none).

    Args:
        db_name: SONiC DB name.
        key: Redis key.

    Use to check if a key exists and what kind of data it holds.
    """
    return call_mcp_tool(
        "sonic_key_type", {"db_name": db_name, "key": key}
    )


@tool
def sonic_list_ports() -> str:
    """List all discovered SONiC port names from CONFIG_DB.

    Returns port names like Ethernet0, Ethernet4, etc.
    Use as the first step when exploring switch ports.
    """
    return call_mcp_tool("sonic_list_ports", {})


@tool
def sonic_get_port_view(port_name: str) -> str:
    """Get a FULL cross-DB diagnostic view of a single SONiC port.

    THIS IS THE PRIMARY DIAGNOSTIC TOOL FOR PORTS.  It gathers data from:
    - CONFIG_DB  (desired configuration)
    - APPL_DB    (application intent)
    - STATE_DB   (runtime state)
    - COUNTERS_DB (statistics)
    - ASIC_DB    (hardware programming)
    Plus transceiver info.  Also includes any consistency findings already
    detected for this port.

    Args:
        port_name: Port name, e.g. "Ethernet0".

    Use this whenever a user asks about a specific port's state or health.
    """
    return call_mcp_tool(
        "sonic_get_port_view", {"port_name": port_name}
    )


@tool
def sonic_check_port(port_name: str) -> str:
    """Run consistency checks on a single SONiC port.

    Checks include: admin-up/oper-down mismatch, MTU mismatch, speed
    mismatch, missing counters, missing transceiver.  Each finding
    includes severity, evidence, possible causes, and suggested commands.

    Args:
        port_name: Port name, e.g. "Ethernet0".
    """
    return call_mcp_tool(
        "sonic_check_port", {"port_name": port_name}
    )


@tool
def sonic_check_all_ports() -> str:
    """Run consistency checks on ALL discovered SONiC ports.

    Returns findings for every port, grouped by port name.
    Use for a switch-wide health check.
    """
    return call_mcp_tool("sonic_check_all_ports", {})


# ══════════════════════════════════════════════════════════════════════
# Aggregated tool lists
# ══════════════════════════════════════════════════════════════════════

SKILL_TOOLS = [list_skills_tool, read_skill_tool]

MCP_TOOLS = [
    sonic_db_config,
    sonic_list_dbs,
    sonic_scan_keys,
    sonic_hget,
    sonic_key_type,
    sonic_list_ports,
    sonic_get_port_view,
    sonic_check_port,
    sonic_check_all_ports,
]

ALL_TOOLS = SKILL_TOOLS + MCP_TOOLS
