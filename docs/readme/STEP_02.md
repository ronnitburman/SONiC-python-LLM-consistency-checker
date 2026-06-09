# Step 2 — Redis DB Explorer

Uses the dynamic DB mapping from Step 1 to inspect SONiC Redis databases by logical name (`CONFIG_DB`, `APPL_DB`, etc.) instead of raw numeric Redis DB IDs.

## Quick Start

```bash
# Install (if not done already)
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Show all DB sizes
sonic-checker dbs

# Scan keys
sonic-checker keys CONFIG_DB "PORT*"

# Read a hash key
sonic-checker hget CONFIG_DB "PORT|Ethernet0"

# Show key type
sonic-checker type CONFIG_DB "PORT|Ethernet0"

# Run API
uvicorn sonic_consistency_checker.api.main:app --reload
curl http://localhost:8000/api/dbs
curl "http://localhost:8000/api/dbs/CONFIG_DB/keys?pattern=PORT*"
curl "http://localhost:8000/api/dbs/CONFIG_DB/key?key=PORT%7CEthernet0"
```

---

## CLI Commands

### `sonic-checker dbs` — List DB sizes

Shows every known SONiC Redis DB with its numeric ID and key count.

```bash
sonic-checker dbs -m orb_vm_exec
```

Example output:

```
SONiC Redis DBs

Source: orb_vm_exec:sonic-lab:clab-sonic-ai-lab-sonic1:/var/run/redis/sonic-db/database_config.json
Used fallback: false

┌──────────────┬────┬──────┐
│ DB Name      │ ID │ Keys │
├──────────────┼────┼──────┤
│ APPL_DB      │  0 │  130 │
│ ASIC_DB      │  1 │  500 │
│ CONFIG_DB    │  4 │  245 │
│ COUNTERS_DB  │  2 │  300 │
│ STATE_DB     │  6 │   60 │
└──────────────┴────┴──────┘
```

If a DB cannot be read, its size shows as `err` instead of crashing the entire command.

---

### `sonic-checker keys` — Scan keys

Scans a DB for keys matching a pattern. Uses **SCAN** (not KEYS) to avoid blocking Redis.

```bash
# All keys in CONFIG_DB
sonic-checker keys CONFIG_DB "*"

# Only PORT keys
sonic-checker keys CONFIG_DB "PORT*"
```

Example output:

```
DB: CONFIG_DB
Pattern: PORT*

Equivalent Redis:
  redis-cli -n 4 scan 0 match "PORT*" count 100

Keys:
  PORT|Ethernet0
  PORT|Ethernet4
  PORT|Ethernet8
```

The `Equivalent Redis` line shows exactly which `redis-cli` command the tool ran internally. This is useful for understanding and debugging.

---

### `sonic-checker hget` — Read a hash key

Reads all fields from a hash key using HGETALL.

```bash
sonic-checker hget CONFIG_DB "PORT|Ethernet0"
```

Example output:

```
DB: CONFIG_DB
Key: PORT|Ethernet0
Type: hash

Equivalent Redis:
  redis-cli -n 4 hgetall "PORT|Ethernet0"

Fields:
  admin_status: up
  mtu: 9100
  speed: 100000
  alias: Ethernet0
```

If the key is not a hash, no fields are shown (but the key type is still reported). If the hash is empty, `No hash fields found.` is displayed.

---

### `sonic-checker type` — Show key type

Returns the Redis data type of a key.

```bash
sonic-checker type CONFIG_DB "PORT|Ethernet0"
```

Example output:

```
DB: CONFIG_DB
Key: PORT|Ethernet0
Type: hash
```

Common Redis types in SONiC: `hash`, `string`, `set`, `zset`, `list`, `none`.

---

## Connection Modes

The Redis explorer supports the same connection modes as Step 1, plus `local_redis`.

### 1. `docker_exec` (default)

Runs `redis-cli` inside the SONiC container via `docker exec`.

```bash
sonic-checker dbs -m docker_exec -c clab-sonic-ai-lab-sonic1
```

Env vars:
```env
SONIC_CONNECTION_MODE=docker_exec
SONIC_CONTAINER_NAME=clab-sonic-ai-lab-sonic1
```

---

### 2. `orb_vm_exec`

Tunnels `redis-cli` through OrbStack VM: `orb exec -m <vm> docker exec <container> redis-cli`.

```bash
sonic-checker dbs -m orb_vm_exec
```

Env vars:
```env
SONIC_CONNECTION_MODE=orb_vm_exec
SONIC_CONTAINER_NAME=clab-sonic-ai-lab-sonic1
SONIC_ORB_VM_NAME=sonic-lab
```

The Orb VM name is auto-detected if `SONIC_ORB_VM_NAME` is not set.

**When to use:** Containerlab deployed inside an OrbStack VM. This is the recommended mode for the `sonic-ai-lab` containerlab setup.

---

### 3. `local_redis`

Connects directly to a Redis instance using `redis-py`. Useful if Redis is exposed to the host.

```bash
sonic-checker dbs -m local_redis
```

Env vars:
```env
SONIC_CONNECTION_MODE=local_redis
SONIC_REDIS_HOST=localhost
SONIC_REDIS_PORT=6379
```

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/dbs` | Returns DB size summaries for all known SONiC Redis DBs |
| `GET /api/dbs/{db_name}/keys?pattern=*` | Scans keys matching a pattern |
| `GET /api/dbs/{db_name}/key?key=...` | Reads a key's type and hash fields |
| `GET /api/dbs/{db_name}/type?key=...` | Returns the Redis type of a key |

### `GET /api/dbs`

```json
[
  {"db_name": "APPL_DB",     "db_id": 0, "size": 130},
  {"db_name": "CONFIG_DB",   "db_id": 4, "size": 245},
  {"db_name": "STATE_DB",    "db_id": 6, "size": 60}
]
```

### `GET /api/dbs/CONFIG_DB/keys?pattern=PORT*`

```json
{
  "db_name": "CONFIG_DB",
  "db_id": 4,
  "pattern": "PORT*",
  "keys": ["PORT|Ethernet0", "PORT|Ethernet4"],
  "equivalent_redis": "redis-cli -n 4 scan 0 match \"PORT*\" count 100"
}
```

### `GET /api/dbs/CONFIG_DB/key?key=PORT%7CEthernet0`

```json
{
  "db_name": "CONFIG_DB",
  "db_id": 4,
  "key": "PORT|Ethernet0",
  "key_type": "hash",
  "fields": {
    "admin_status": "up",
    "mtu": "9100",
    "speed": "100000"
  },
  "equivalent_redis": "redis-cli -n 4 hgetall \"PORT|Ethernet0\""
}
```

### `GET /api/dbs/CONFIG_DB/type?key=PORT%7CEthernet0`

```json
{
  "db_name": "CONFIG_DB",
  "key": "PORT|Ethernet0",
  "key_type": "hash"
}
```

---

## Architecture: How DB Name Resolution Works

All Redis operations go through `get_db_id(db_name)` — never hardcoded:

```
User types: sonic-checker hget CONFIG_DB "PORT|Ethernet0"
                │
                ▼
    SonicDiscoveryService.read_key("CONFIG_DB", "PORT|Ethernet0")
                │
                ▼
    SonicRedisClient.get_db_id("CONFIG_DB")  →  4
         (looks up CONFIG_DB in dynamic config from Step 1)
                │
                ▼
    Runs: redis-cli -n 4 hgetall "PORT|Ethernet0"
```

If you type an unknown DB name:

```
Error: Unknown DB name: FOO_DB. Available DBs: APPL_DB, ASIC_DB, CONFIG_DB, ...
```

---

## Project Structure (Steps 1 + 2)

```text
pyproject.toml
.env.example

sonic_consistency_checker/
  __init__.py
  core/
    __init__.py
    db_constants.py          # fallback defaults only — not the source of truth
    db_config_loader.py      # dynamic loader (docker_exec, orb_vm_exec, local, fallback)
    models.py                # Pydantic models: DbSizeSummary, SonicDbKey, DbKeysResponse
    redis_client.py          # SonicRedisClient — Redis operations via docker_exec / orb_vm_exec / local_redis
    discovery.py             # SonicDiscoveryService — service layer returning typed model objects
  cli/
    __init__.py
    main.py                  # CLI: db-config, dbs, keys, hget, type (Typer + Rich)
  api/
    __init__.py
    main.py                  # FastAPI /health, /api/db-config, /api/dbs/...
    routes_dbs.py            # /api/dbs router
```
