# Step 3 — Normalized Port View

Builds a cross-DB normalized view of a SONiC port by gathering related data from CONFIG_DB, APPL_DB, STATE_DB, COUNTERS_DB, ASIC_DB, and transceiver keys.

## Quick Start

```bash
# Install (if not done already)
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# List discovered ports
sonic-checker ports

# Show a normalized port view
sonic-checker port Ethernet0

# Run API
uvicorn sonic_consistency_checker.api.main:app --reload
curl http://localhost:8000/api/ports
curl http://localhost:8000/api/ports/Ethernet0
```

---

## Why This Matters

A SONiC port is not stored in one place. For a single port like `Ethernet0`, related data lives across multiple Redis databases:

| Database | What it holds | Example key |
|---|---|---|
| CONFIG_DB | Desired/admin config | `PORT\|Ethernet0` |
| APPL_DB | Application-level intent | `PORT_TABLE:Ethernet0` |
| STATE_DB | Runtime operational state | `PORT_TABLE\|Ethernet0` |
| STATE_DB | Transceiver info | `TRANSCEIVER_INFO\|Ethernet0` |
| COUNTERS_DB | Traffic statistics | various counter keys |
| ASIC_DB | Hardware/SAI port objects | `ASIC_STATE:SAI_OBJECT_TYPE_PORT:...` |

The normalized port view gathers all this evidence into a single object, so you can see the full picture without running multiple Redis commands manually.

---

## CLI Commands

### `sonic-checker ports` — List discovered ports

Scans `CONFIG_DB` for `PORT|*` keys and extracts port names.

```bash
sonic-checker ports -m orb_vm_exec
```

Example output:

```
Discovered Ports

Source: CONFIG_DB:PORT|*

Ports:
  Ethernet0
  Ethernet4
  Ethernet8
  Ethernet12
```

---

### `sonic-checker port` — Show one port

Gathers all available data for a port across every relevant DB.

```bash
sonic-checker port Ethernet0 -m orb_vm_exec
```

Example output:

```
Port: Ethernet0

CONFIG_DB
  Key: PORT|Ethernet0
  admin_status: up
  mtu: 9100
  speed: 100000
  alias: Ethernet0

APPL_DB
  Key: PORT_TABLE:Ethernet0
  admin_status: up

STATE_DB
  Key: PORT_TABLE|Ethernet0
  oper_status: up

TRANSCEIVER
  No data found.

COUNTERS_DB
  Key: COUNTERS:oid:0x...
    ...

ASIC_DB
  Key: ASIC_STATE:SAI_OBJECT_TYPE_PORT:oid:0x...
    ...
```

If a section has no data, it prints `No data found.` — this is not treated as an error. Different SONiC images may not expose transceiver data or have different key layouts.

---

## Schema Tolerance

SONiC images can use different key separators. For example, APPL_DB might store port data as:

- `PORT_TABLE:Ethernet0` (colon separator)
- `PORT_TABLE|Ethernet0` (pipe separator)

The port view tries **both separators** automatically. If neither key exists, the section is left empty.

The rule is:

> Try likely keys. If missing, leave that section empty. Do not crash.

---

## Connection Modes

Same as Steps 1–2. All three connection modes are supported.

### `docker_exec` (default)

```bash
sonic-checker port Ethernet0 -m docker_exec -c clab-sonic-ai-lab-sonic1
```

### `orb_vm_exec` (recommended for sonic-ai-lab)

```bash
sonic-checker port Ethernet0 -m orb_vm_exec
```

The Orb VM name is auto-detected from `orb list --running --quiet`. Set explicitly:

```bash
sonic-checker port Ethernet0 -m orb_vm_exec --orb-vm-name sonic-lab
```

### `local_redis`

```bash
sonic-checker port Ethernet0 -m local_redis
```

Requires `SONIC_REDIS_HOST` and `SONIC_REDIS_PORT` in `.env`.

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/ports` | Returns list of discovered port names |
| `GET /api/ports/{port_name}` | Returns normalized cross-DB port view |

### `GET /api/ports`

```json
{
  "ports": ["Ethernet0", "Ethernet4", "Ethernet8"],
  "source": "CONFIG_DB:PORT|*"
}
```

### `GET /api/ports/Ethernet0`

```json
{
  "name": "Ethernet0",
  "config": {
    "admin_status": "up",
    "mtu": "9100",
    "speed": "100000"
  },
  "app": {
    "admin_status": "up"
  },
  "state": {
    "oper_status": "up"
  },
  "asic": {
    "ASIC_STATE:SAI_OBJECT_TYPE_PORT:oid:0x1000000000055": {}
  },
  "counters": {
    "COUNTERS:oid:0x1000000000055": {}
  },
  "transceiver": {},
  "raw_keys": {
    "CONFIG_DB": ["PORT|Ethernet0"],
    "APPL_DB": ["PORT_TABLE:Ethernet0"],
    "STATE_DB": ["PORT_TABLE|Ethernet0"],
    "COUNTERS_DB": ["COUNTERS:oid:0x..."],
    "ASIC_DB": ["ASIC_STATE:SAI_OBJECT_TYPE_PORT:oid:0x..."]
  }
}
```

The `raw_keys` field shows exactly which Redis keys were accessed for each DB — useful for debugging and understanding the underlying data layout.

---

## Architecture

```
User runs: sonic-checker port Ethernet0
                │
                ▼
    PortService.get_port_view("Ethernet0")
                │
     ┌──────────┼──────────┬──────────┬──────────┐
     ▼          ▼          ▼          ▼          ▼
  CONFIG_DB  APPL_DB   STATE_DB   COUNTERS   ASIC_DB
  PORT|...   (both      (both      (scan      (scan
             separators) separators) *Eth0*)   *PORT*)
                │
                ▼
    PortView assembled with all gathered data
```

---

## Project Structure (Steps 1–3)

```text
sonic_consistency_checker/
  __init__.py
  core/
    __init__.py
    db_constants.py
    db_config_loader.py
    models.py                # + PortView, PortsListResponse
    redis_client.py
    discovery.py
  sonic/
    __init__.py
    ports.py                 # NEW — PortService
  cli/
    __init__.py
    main.py                  # + ports, port commands
  api/
    __init__.py
    main.py                  # + ports router
    routes_dbs.py
    routes_ports.py          # NEW
```

---

## Important Implementation Rule

All DB access goes through the existing `SonicRedisClient`. No DB IDs are hardcoded.

Bad:
```python
redis.Redis(db=4)
```

Good:
```python
self.redis_client.hgetall("CONFIG_DB", "PORT|Ethernet0")
```

---

## What This Step Does NOT Do

This step **gathers facts only**. It does not:

- Detect inconsistencies or mismatches (Step 4)
- Assign severity or warnings
- Map ASIC OIDs back to port names (future enhancement)
- Map COUNTERS_DB OIDs back to port names (future enhancement)
- Any SWSS SDK, UI, or LLM work

Missing data is shown as `No data found.` — never as an error.
