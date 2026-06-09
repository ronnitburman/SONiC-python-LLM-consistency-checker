# Step 5 — SWSS SDK Exploration

Adds optional SWSS SDK support on top of the existing Redis explorer. Compares raw Redis access with SONiC-native SDK abstractions where available.

## Quick Start

```bash
# Install (if not done already)
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Check SDK availability
sonic-checker swss check

# Read CONFIG_DB through ConfigDBConnector (local — requires swsssdk installed)
sonic-checker swss config-table PORT
sonic-checker swss config-entry PORT Ethernet0

# OR run remotely through orb VM (no local swsssdk needed!)
sonic-checker swss config-table PORT -m orb_vm_exec
sonic-checker swss config-entry PORT Ethernet0 -m orb_vm_exec
sonic-checker swss v2-keys CONFIG_DB "PORT*" -m orb_vm_exec
sonic-checker swss v2-hgetall CONFIG_DB "PORT|Ethernet0" -m orb_vm_exec

# Table-oriented reads via raw Redis (always works with -m)
sonic-checker swss table CONFIG_DB PORT -m orb_vm_exec
sonic-checker swss table-entry CONFIG_DB PORT Ethernet0 -m orb_vm_exec

# Compare raw Redis vs SWSS SDK — now works remotely!
sonic-checker swss compare-read PORT Ethernet0 -m orb_vm_exec

# Run API (set SONIC_CONNECTION_MODE=orb_vm_exec in .env for remote SDK)
uvicorn sonic_consistency_checker.api.main:app --reload
curl http://localhost:8000/api/swss/check
curl "http://localhost:8000/api/swss/config/PORT?connection_mode=orb_vm_exec"
curl http://localhost:8000/api/swss/compare/config/PORT/Ethernet0
```

---

## Why This Matters

SONiC code doesn't always interact with Redis as raw strings. SONiC has libraries and abstractions:

| Access method | Mental model | Example |
|---|---|---|
| Raw `redis-cli` | DB number + raw key string | `redis-cli -n 4 hgetall "PORT\|Ethernet0"` |
| `redis-py` | Same, programmatic | `r.hgetall("PORT\|Ethernet0")` |
| `ConfigDBConnector` | DB name + table + key | `get_entry("PORT", "Ethernet0")` |
| `SonicV2Connector` | DB name + key pattern | `keys("CONFIG_DB", "PORT*")` |
| `ProducerStateTable` | Producer-consumer pub/sub | `set(key, fvs)` |

The SWSS SDK layer helps you understand the SONiC-native access patterns used by Python utilities and SWSS components.

---

## Important: SDK is Optional (Two Ways to Use It)

SWSS SDK (`swsssdk`, `swsscommon`) may only be available inside the SONiC container. The tool offers **two ways** to use it:

### Option 1: Local (inside SONiC container)

Run the checker from *inside* the SONiC container where `swsssdk` is installed:

```bash
docker exec -it clab-sonic-ai-lab-sonic1 bash
pip install -e /path/to/sonic_consistency_checker
sonic-checker swss config-table PORT
```

### Option 2: Remote (from your Mac / any machine)

Pass `-m orb_vm_exec` (or `-m docker_exec`) to tunnel the SDK calls through the orb VM. The checker ships a small Python script into the container, runs it there, and returns the result — **no local swsssdk install needed**:

```bash
# From your Mac:
sonic-checker swss config-table PORT -m orb_vm_exec
sonic-checker swss v2-keys CONFIG_DB "PORT*" -m orb_vm_exec
sonic-checker swss compare-read PORT Ethernet0 -m orb_vm_exec
```

Under the hood: `orb exec -m <vm> docker exec <container> python3 -c "import swsssdk; ..."`

The tool **never crashes** on local import errors. Instead:

```
SWSS SDK Status

swsssdk:      unavailable
swsscommon:   unavailable

SWSS SDK is not available in this Python environment.
Try running inside the SONiC container, or continue using raw Redis mode.
```

Raw Redis commands (Steps 1–4) remain fully functional regardless.

---

## CLI Commands

### `sonic-checker swss check` — Check SDK availability

```bash
sonic-checker swss check
```

Reports whether `swsssdk` and `swsscommon` are importable.

### `sonic-checker swss config-table` / `config-entry` — ConfigDBConnector

```bash
# Local (requires swsssdk installed in this Python environment)
sonic-checker swss config-table PORT
sonic-checker swss config-entry PORT Ethernet0

# Remote (tunnels through orb VM — no local swsssdk needed)
sonic-checker swss config-table PORT -m orb_vm_exec
sonic-checker swss config-entry PORT Ethernet0 -m orb_vm_exec
```

Reads CONFIG_DB through the SONiC-native `ConfigDBConnector` abstraction. In remote mode, serialises the SDK call, ships it into the container via `orb exec → docker exec python3 -c`, and returns the parsed JSON result.

### `sonic-checker swss v2-keys` / `v2-hgetall` — SonicV2Connector

```bash
# Local
sonic-checker swss v2-keys CONFIG_DB "PORT*"
sonic-checker swss v2-hgetall CONFIG_DB "PORT|Ethernet0"

# Remote
sonic-checker swss v2-keys CONFIG_DB "PORT*" -m orb_vm_exec
sonic-checker swss v2-hgetall CONFIG_DB "PORT|Ethernet0" -m orb_vm_exec
```

Accesses SONiC DBs by logical DB name through `SonicV2Connector`. Same remote execution pattern as ConfigDBConnector.

### `sonic-checker swss table` / `table-entry` — Table-oriented reads

```bash
sonic-checker swss table CONFIG_DB PORT
sonic-checker swss table-entry CONFIG_DB PORT Ethernet0
```

Uses the existing raw Redis client but presents data with a table-oriented mental model (table PORT, key Ethernet0 → raw key `PORT|Ethernet0`). Supports `-m orb_vm_exec`.

### `sonic-checker swss compare-read` — Compare raw Redis vs SDK

```bash
# Local
sonic-checker swss compare-read PORT Ethernet0

# Remote (both raw Redis AND SDK tunnel through orb VM)
sonic-checker swss compare-read PORT Ethernet0 -m orb_vm_exec
```

Reads the same CONFIG_DB entry via both raw Redis and SWSS SDK, then diffs:

```
Compare: PORT/Ethernet0

Raw Redis:
  Key:              PORT|Ethernet0
  Equivalent:       redis-cli -n 4 hgetall "PORT|Ethernet0"
  admin_status: up
  mtu: 9100
  speed: 100000

SWSS SDK:
  admin_status: up
  mtu: 9100
  speed: 100000

Comparison:
  Same fields:       ['admin_status', 'mtu', 'speed']
  Different fields:  []
  Missing in Redis:  []
  Missing in SDK:    []
```

If SDK is unavailable, the SWSS SDK section shows the error but raw Redis still works.

### `sonic-checker swss test-produce` / `test-delete` — Safe write experiments

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

Writes via `ProducerStateTable`. Two safety layers:

1. `--allow-writes` must be explicitly passed
2. Only tables starting with `SONIC_AI_LAB_TEST` are allowed

Blocked tables: `PORT`, `PORT_TABLE`, `ROUTE_TABLE`, `NEIGH_TABLE`, `VLAN`, `ASIC_STATE`, `INTF_TABLE`, `LAG_TABLE`

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/swss/check` | SWSS SDK availability |
| `GET /api/swss/config/{table}` | Read CONFIG_DB table via ConfigDBConnector |
| `GET /api/swss/config/{table}/{key}` | Read CONFIG_DB entry via ConfigDBConnector |
| `GET /api/swss/v2/{db_name}/keys?pattern=*` | Scan keys via SonicV2Connector |
| `GET /api/swss/v2/{db_name}/key?key=...` | HGETALL via SonicV2Connector |
| `GET /api/swss/table/{db_name}/{table}` | Table keys via raw Redis |
| `GET /api/swss/table/{db_name}/{table}/{key}` | Table entry via raw Redis |
| `GET /api/swss/compare/config/{table}/{key}` | Compare raw Redis vs SWSS SDK |
| `POST /api/swss/test-produce` | Safe write (body: `table`, `key`, `values`, `allow_writes`) |
| `DELETE /api/swss/test-produce` | Safe delete (body: `table`, `key`, `allow_writes`) |

---

## Project Structure (Steps 1–5)

```text
sonic_consistency_checker/
  __init__.py
  core/
    __init__.py
    db_constants.py
    db_config_loader.py
    models.py
    redis_client.py
    discovery.py
    diff_engine.py
  sonic/
    __init__.py
    ports.py
  swss/                          # NEW — Step 5 package
    __init__.py
    connector.py                 # Optional import handling
    config_db.py                 # ConfigDbReader
    sonic_v2.py                  # SonicV2Reader
    table_reader.py              # SwssTableReader
    table_writer.py              # SwssTableWriter (safe writes)
    safety.py                    # Write safety validation
    compare.py                   # SwssCompareService
  cli/
    __init__.py
    main.py                      # + swss sub-app with 10 commands
  api/
    __init__.py
    main.py                      # + swss router
    routes_dbs.py
    routes_ports.py
    routes_findings.py
    routes_swss.py               # NEW
```

---

## What This Step Does NOT Do

- React UI (Step 6)
- LLM explanation (Step 7)
- Automatic real-table writes
- Route or neighbor checks
- Advanced OID/optical/FEC analysis
