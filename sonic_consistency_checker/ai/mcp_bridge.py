"""MCP bridge — calls the sonic_mcp_server.py tools via HTTP JSON-RPC.

The MCP server runs as a separate process on http://127.0.0.1:9100/mcp.
Uses FastMCP's streamable-http transport with session management.
"""

from __future__ import annotations

import json
import os
import logging

import httpx

logger = logging.getLogger(__name__)

MCP_URL = os.getenv("SONIC_MCP_URL", "http://127.0.0.1:9100/mcp")

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def _parse_sse_response(text: str) -> dict:
    """Parse a FastMCP SSE response body into a JSON dict.

    FastMCP's streamable-http transport returns::

        event: message
        data: {"jsonrpc":"2.0",...}

    We extract the ``data:`` line and parse it as JSON.
    """
    for line in text.strip().split("\n"):
        if line.startswith("data: "):
            return json.loads(line[6:])
    # Fallback: maybe it's plain JSON
    return json.loads(text)


async def _call_mcp_tool_async(tool_name: str, arguments: dict) -> str:
    """Call an MCP tool via JSON-RPC over HTTP (async).

    Each call is self-contained: creates its own HTTP client, initialises
    an MCP session, calls the tool, and tears down.
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # 1. Initialise session
            init_payload = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "sonic-chat-agent", "version": "1.0.0"},
                },
                "id": 0,
            }
            resp = await client.post(MCP_URL, json=init_payload, headers=HEADERS)
            resp.raise_for_status()
            session_id = resp.headers.get("mcp-session-id", "")

            # 2. Call the tool
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
                "id": 1,
            }
            req_headers = dict(HEADERS)
            if session_id:
                req_headers["mcp-session-id"] = session_id

            response = await client.post(
                MCP_URL,
                json=payload,
                headers=req_headers,
            )
            response.raise_for_status()
            data = _parse_sse_response(response.text)

        if "error" in data:
            logger.warning("MCP tool %s FAILED: %s", tool_name, data["error"])
            return f"MCP error: {data['error']}"

        result = data.get("result", {})
        content = result.get("content", [])

        texts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))

        output = "\n".join(texts) if texts else json.dumps(result, indent=2)
        logger.info("MCP call: %s → %d chars", tool_name, len(output))
        return output

    except httpx.ConnectError:
        return (
            f"ERROR: Cannot connect to MCP server at {MCP_URL}. "
            "Is the server running? Start it with: "
            ".venv/bin/python sonic_mcp_server.py"
        )
    except Exception as exc:
        logger.error("MCP call failed: %s %s → %s", tool_name, arguments, exc)
        return f"ERROR calling {tool_name}: {exc}"


def call_mcp_tool(tool_name: str, arguments: dict) -> str:
    """Synchronous wrapper — always uses asyncio.run() for a clean event loop."""
    import asyncio
    return asyncio.run(_call_mcp_tool_async(tool_name, arguments))
