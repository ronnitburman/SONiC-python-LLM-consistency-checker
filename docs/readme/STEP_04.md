# Step 4 — Consistency Checks

Adds deterministic, evidence-based consistency checks that compare port data across SONiC Redis databases. Does **not** use an LLM — all checks are rule-based.

## Quick Start

```bash
# Install (if not done already)
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Run checks on all ports
sonic-checker findings

# Check a single port
sonic-checker check-port Ethernet0

# Port view now includes findings
sonic-checker port Ethernet0

# Run API
uvicorn sonic_consistency_checker.api.main:app --reload
curl http://localhost:8000/api/findings
curl http://localhost:8000/api/ports/Ethernet0/findings
```

---

## Why This Matters

SONiC debugging is often about comparing layers. For example, CONFIG_DB might say Ethernet0 is admin-up, but STATE_DB might show oper-down. These mismatches are the core of network debugging.

The consistency checker:

- Compares data across DBs deterministically (no LLM, no guessing)
- Creates structured findings with evidence, possible causes, and suggested next commands
- Uses appropriate severity levels (not every missing piece of data is "critical")

---

## CLI Commands

### `sonic-checker findings` — Check all ports

Runs consistency checks on all ports discovered from CONFIG_DB.

```bash
sonic-checker findings -m orb_vm_exec
```

Example output:

```
Findings

[warning] PORT_ADMIN_UP_OPER_DOWN — Ethernet0
Port is administratively up but operationally down.

Evidence:
  CONFIG_DB.PORT|Ethernet0.admin_status: up
  STATE_DB.oper_status: down
  raw_keys: { ... }

Possible causes:
  - Cable unplugged
  - Transceiver missing or faulty
  - Remote peer down
  - Speed mismatch
  - FEC mismatch
  - Platform driver issue
  - Optical signal issue

Suggested commands:
  - show interfaces status
  - show interfaces transceiver presence
  - show interfaces transceiver eeprom Ethernet0
  - redis-cli -n <CONFIG_DB_ID> hgetall "PORT|Ethernet0"
  - redis-cli -n <STATE_DB_ID> hgetall "PORT_TABLE|Ethernet0"
```

If there are no findings: `No findings found.`

---

### `sonic-checker check-port` — Check one port

```bash
sonic-checker check-port Ethernet0 -m orb_vm_exec
```

Shows findings for a single port only. Same format as above.

---

### `sonic-checker port` — Now includes findings

The existing port command now includes a `FINDINGS` section at the end:

```
FINDINGS
  [warning] PORT_ADMIN_UP_OPER_DOWN
  Port is administratively up but operationally down.

No findings.
```

---

## Checks Implemented

| Check | Severity | Condition |
|---|---|---|
| `PORT_MISSING_IN_STATE_DB` | info | Port in CONFIG_DB but no STATE_DB port state found |
| `PORT_ADMIN_UP_OPER_DOWN` | warning | admin_status=up in CONFIG_DB, oper_status=down in STATE_DB |
| `PORT_MTU_MISMATCH` | warning | MTU differs between CONFIG_DB and APPL_DB |
| `PORT_SPEED_MISMATCH` | warning | Speed differs between CONFIG_DB and APPL_DB |
| `PORT_COUNTERS_MISSING` | info | No COUNTERS_DB data found for the port |
| `TRANSCEIVER_INFO_MISSING` | info | No transceiver info found for the port |

### Severity levels

| Level | Meaning |
|---|---|
| `info` | Informational — likely normal (e.g., no transceiver data in SONiC VS) |
| `warning` | Something may be wrong — needs investigation |
| `critical` | Reserved for clear, confirmed problems (not used in this step yet) |

---

## Finding Structure

Every finding includes:

| Field | Purpose |
|---|---|
| `id` | Stable unique ID, e.g. `port_admin_up_oper_down:Ethernet0` |
| `severity` | `info`, `warning`, or `critical` |
| `category` | Check name, e.g. `PORT_ADMIN_UP_OPER_DOWN` |
| `object_type` | Type of object, e.g. `port` |
| `object_name` | Object name, e.g. `Ethernet0` |
| `summary` | Human-readable one-liner |
| `evidence` | Dict of evidence from the DBs (with dotted paths and raw_keys) |
| `possible_causes` | List of likely causes to investigate |
| `suggested_commands` | List of `show`/`redis-cli` commands to run next |

---

## Connection Modes

Same as previous steps. All three modes supported.

```bash
sonic-checker findings -m docker_exec -c my-container
sonic-checker findings -m orb_vm_exec
sonic-checker check-port Ethernet0 -m local_redis
```

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/findings` | Returns all findings across all discovered ports |
| `GET /api/ports/{port_name}/findings` | Returns findings for a single port |

### `GET /api/findings`

```json
{
  "findings": [
    {
      "id": "port_admin_up_oper_down:Ethernet0",
      "severity": "warning",
      "category": "PORT_ADMIN_UP_OPER_DOWN",
      "object_type": "port",
      "object_name": "Ethernet0",
      "summary": "Port is administratively up but operationally down.",
      "evidence": {
        "CONFIG_DB.PORT|Ethernet0.admin_status": "up",
        "STATE_DB.oper_status": "down",
        "raw_keys": { ... }
      },
      "possible_causes": [
        "Cable unplugged",
        "Transceiver missing or faulty",
        "Remote peer down",
        "Speed mismatch",
        "FEC mismatch",
        "Platform driver issue",
        "Optical signal issue"
      ],
      "suggested_commands": [
        "show interfaces status",
        "show interfaces transceiver presence",
        "show interfaces transceiver eeprom Ethernet0"
      ]
    }
  ]
}
```

### `GET /api/ports/{port_name}/findings`

Same structure, filtered to one port.

---

## Project Structure (Steps 1–4)

```text
sonic_consistency_checker/
  __init__.py
  core/
    __init__.py
    db_constants.py
    db_config_loader.py
    models.py                # + Finding, FindingsResponse; PortView.findings
    redis_client.py
    discovery.py
    diff_engine.py           # NEW — DiffEngine with 6 checks
  sonic/
    __init__.py
    ports.py                 # + list_port_views(), wired DiffEngine
  cli/
    __init__.py
    main.py                  # + findings, check-port; port shows findings
  api/
    __init__.py
    main.py                  # + findings router
    routes_dbs.py
    routes_ports.py
    routes_findings.py       # NEW
```

---

## What This Step Does NOT Do

- LLM-based explanations (Step 7)
- SWSS SDK exploration (Step 5)
- React UI (Step 6)
- Route or neighbor consistency checks
- Advanced ASIC/counter OID mapping
- Automatic remediation

Missing data is informational, not an error.
