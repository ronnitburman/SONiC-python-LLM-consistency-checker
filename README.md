# SONiC Python LLM Consistency Checker

Step-by-step SONiC learning and consistency-checking project.

Reads SONiC's internal Redis DB configuration dynamically, explores Redis state, builds cross-DB views of ports and routes, detects inconsistencies, and uses an LLM-ready explanation layer to support debugging workflows.

## Steps

| Step | Description | README |
|---|---|---|
| 1 | Dynamic DB Config Discovery | [STEP_01.md](docs/readme/STEP_01.md) |
| 2 | Redis DB Explorer | [STEP_02.md](docs/readme/STEP_02.md) |
| 3 | Port View | [STEP_03.md](docs/readme/STEP_03.md) |
| 4 | Consistency Checks | [STEP_04.md](docs/readme/STEP_04.md) |
| 5 | SWSS SDK Explorer | [STEP_05.md](docs/readme/STEP_05.md) |
| 6 | UI Demo | *(coming)* |
| 7 | LLM Explanation Layer | *(coming)* |


## Quick Start

```bash
pip install -e .
sonic-checker db-config
```

See [docs/readme/STEP_01.md](docs/readme/STEP_01.md) for connection mode setup.

---

## Step 2: Redis DB Explorer

This step uses the dynamic DB mapping from Step 1 to inspect Redis DBs by logical SONiC DB name.

### Show DB sizes

```bash
sonic-checker dbs
```

### Scan keys

```bash
sonic-checker keys CONFIG_DB "PORT*"
```

### Read a hash key

```bash
sonic-checker hget CONFIG_DB "PORT|Ethernet0"
```

### Show key type

```bash
sonic-checker type CONFIG_DB "PORT|Ethernet0"
```

### API

```bash
uvicorn sonic_consistency_checker.api.main:app --reload

curl http://localhost:8000/api/dbs
curl "http://localhost:8000/api/dbs/CONFIG_DB/keys?pattern=PORT*"
curl "http://localhost:8000/api/dbs/CONFIG_DB/key?key=PORT%7CEthernet0"
```

---

## Step 3: Normalized Port View

This step builds a cross-DB view of a SONiC port.

### List discovered ports

```bash
sonic-checker ports
```

### Show one port

```bash
sonic-checker port Ethernet0
```

### API

```bash
uvicorn sonic_consistency_checker.api.main:app --reload

curl http://localhost:8000/api/ports
curl http://localhost:8000/api/ports/Ethernet0
```

---

## Step 4: Consistency Checks

This step adds deterministic consistency checks on top of the normalized port view.

### Check all ports

```bash
sonic-checker findings
```

### Check one port

```bash
sonic-checker check-port Ethernet0
```

### Port view with findings

```bash
sonic-checker port Ethernet0
```

### API

```bash
uvicorn sonic_consistency_checker.api.main:app --reload

curl http://localhost:8000/api/findings
curl http://localhost:8000/api/ports/Ethernet0/findings
```

---

## Step 5: SWSS SDK Exploration

This step adds optional SWSS SDK support. The tool compares raw Redis with SONiC-native SDK abstractions.

### Check SWSS SDK availability

```bash
sonic-checker swss check
```

### Read CONFIG_DB table through ConfigDBConnector

```bash
sonic-checker swss config-table PORT
sonic-checker swss config-entry PORT Ethernet0
```

### Use SonicV2Connector-style access

```bash
sonic-checker swss v2-keys CONFIG_DB "PORT*"
sonic-checker swss v2-hgetall CONFIG_DB "PORT|Ethernet0"
```

### Table-oriented Redis read

```bash
sonic-checker swss table CONFIG_DB PORT
sonic-checker swss table-entry CONFIG_DB PORT Ethernet0
```

### Compare raw Redis and SWSS SDK

```bash
sonic-checker swss compare-read PORT Ethernet0
```

### Safe ProducerStateTable experiment

```bash
sonic-checker swss test-produce \
  --table SONIC_AI_LAB_TEST_TABLE \
  --key demo1 \
  --field status \
  --value ok \
  --allow-writes

sonic-checker swss test-delete \
  --table SONIC_AI_LAB_TEST_TABLE \
  --key demo1 \
  --allow-writes
```

Writes are disabled by default and only allowed for `SONIC_AI_LAB_TEST*` tables.

---

## MCP Server — SONiC Diagnostic Tools for AI Agents

An MCP (Model Context Protocol) server that exposes all SONiC diagnostic tools as MCP tools, callable by any MCP-compatible AI agent or coding assistant.

### Tools Exposed

| Tool | Description |
|---|---|
| `sonic_db_config` | Show the dynamic SONiC Redis DB configuration (DB IDs, separators) |
| `sonic_list_dbs` | List all SONiC Redis DBs with key counts |
| `sonic_scan_keys` | Scan keys in any DB (safe, uses SCAN) |
| `sonic_hget` | Read all hash fields from a key (HGETALL) |
| `sonic_key_type` | Show Redis type of a key |
| `sonic_list_ports` | List all discovered SONiC ports |
| `sonic_get_port_view` | Get full cross-DB view of a port (CONFIG_DB → ASIC_DB) |
| `sonic_check_port` | Run consistency checks on a single port |
| `sonic_check_all_ports` | Run consistency checks on ALL ports |

### Running the MCP Server

**Default (streamable HTTP on port 8100):**

```bash
# Terminal 1: start the server (runs as a long-lived service)
.venv/bin/python sonic_mcp_server.py
# Listening on http://127.0.0.1:8100/mcp

# Test with curl:
curl -X POST http://127.0.0.1:8100/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}'
```

**Stdio mode** (for child-process clients, e.g. Claude Desktop):

```bash
.venv/bin/python sonic_mcp_server.py --transport stdio
```

**Custom port:**

```bash
.venv/bin/python sonic_mcp_server.py --port 9000
# Or via env:  SONIC_MCP_PORT=9000 .venv/bin/python sonic_mcp_server.py
```

### Integrating with pi (coding agent)

pi auto-discovers extensions in `.pi/extensions/`. The extension at
`.pi/extensions/sonic-mcp/` connects to the MCP server over HTTP and bridges
all tools as pi custom tools.

**Prerequisites:**

```bash
pip install -e .              # Python dependencies (includes mcp>=1.0.0)
cd .pi/extensions/sonic-mcp
npm install                    # TypeScript MCP client SDK
```

**Workflow:**

```bash
# Terminal 1: Start the MCP server (leave running)
.venv/bin/python sonic_mcp_server.py

# Terminal 2: Start pi in the project root
pi
# Extension auto-connects to http://127.0.0.1:8100/mcp
# All 9 sonic_* tools are now available
```

Then in pi:

> "Use sonic_get_port_view to inspect Ethernet0"
> "Run sonic_check_all_ports to find issues"

### Integrating with Other MCP Clients (stdio transport)

For clients that spawn the server as a child process (e.g., Claude Desktop):

```json
{
  "mcpServers": {
    "sonic-checker": {
      "command": "/path/to/.venv/bin/python",
      "args": ["sonic_mcp_server.py", "--transport", "stdio"],
      "cwd": "/Users/burman/projects/SONiC-python-LLM-consistency-checker"
    }
  }
}
```

### Architecture

```
┌──────────────────────────────────────────────────────┐
│  pi coding agent (or any MCP client)                 │
│                                                      │
│  .pi/extensions/sonic-mcp/index.ts                   │
│    ├─ Connects to MCP server via HTTP                │
│    ├─ StreamableHTTPClientTransport                  │
│    ├─ Discovers tools via tools/list                 │
│    └─ Registers each tool with pi.registerTool()     │
│                                                      │
└──────────────┬───────────────────────────────────────┘
               │ HTTP POST → http://127.0.0.1:8100/mcp
               ▼
┌──────────────────────────────────────────────────────┐
│  sonic_mcp_server.py  (FastMCP server)               │
│  Transport: streamable-http (default) or stdio       │
│                                                      │
│  Wraps sonic_consistency_checker:                    │
│    ├─ SonicRedisClient     → Redis/redis-cli calls  │
│    ├─ SonicDiscoveryService → DB exploration         │
│    ├─ PortService           → Cross-DB port view     │
│    └─ DiffEngine            → Consistency checks     │
│                                                      │
└──────────────┬───────────────────────────────────────┘
               │ docker exec / orb exec / redis-py
               ▼
┌──────────────────────────────────────────────────────┐
│  SONiC Switch (or VM)                                │
│    Redis sonic-db  ───  CONFIG_DB, APPL_DB, etc.     │
└──────────────────────────────────────────────────────┘
```
