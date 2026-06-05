# Step 1 — Dynamic SONiC DB Config Discovery

Reads SONiC's `database_config.json` dynamically from a running SONiC container instead of hardcoding DB IDs, separators, and instances.

## Quick Start

```bash
# Install
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Run CLI
sonic-checker db-config

# Run API
uvicorn sonic_consistency_checker.api.main:app --reload
curl http://localhost:8000/api/db-config
```

---

## Connection Modes

The loader supports three connection modes. Set via `--connection-mode` / `-m` flag or `SONIC_CONNECTION_MODE` env var.

### 1. `docker_exec` (default)

Reads from a SONiC container via local Docker.

```bash
sonic-checker db-config -m docker_exec -c <container-name>
```

Env vars:
```env
SONIC_CONNECTION_MODE=docker_exec
SONIC_CONTAINER_NAME=clab-sonic-ai-lab-sonic1
```

**When to use:** Docker Desktop, Docker Engine on Linux, or any setup where `docker exec` works directly from the host.

---

### 2. `orb_vm_exec`

Reads from a SONiC container running inside an OrbStack VM. Tunnels Docker commands through `orb exec`.

```bash
sonic-checker db-config -m orb_vm_exec
```

The Orb VM name is auto-detected from `orb list --running --quiet`. To specify explicitly:

```bash
sonic-checker db-config -m orb_vm_exec --orb-vm-name sonic-lab -c clab-sonic-ai-lab-sonic1
```

Env vars:
```env
SONIC_CONNECTION_MODE=orb_vm_exec
SONIC_CONTAINER_NAME=clab-sonic-ai-lab-sonic1
SONIC_ORB_VM_NAME=sonic-lab
```

**When to use:** Containerlab deployed inside an OrbStack VM (`orb` CLI available on macOS host). This is the recommended mode for the `sonic-ai-lab` containerlab setup.

Verify the VM and container are reachable:
```bash
orb list                          # check VMs
orb exec -m sonic-lab docker ps   # check containers inside VM
```

---

### 3. `local_filesystem`

Reads `database_config.json` directly from the local filesystem.

```bash
sonic-checker db-config -m local_filesystem
```

Searches these paths in order:
- `/var/run/redis/sonic-db/database_config.json`
- `/etc/sonic/database_config.json`

**When to use:** When you have a copy of `database_config.json` on your local machine, or when running the tool directly on a SONiC switch.

---

## Fallback Behavior

If all connection modes fail, the tool falls back to hardcoded defaults and explicitly warns you:

```
Source: fallback_defaults
Used fallback: true

Warning:
  Could not read SONiC database_config.json.
  Using fallback default DB IDs.
```

The fallback is **deliberately limited** to 5 common DBs. If you see this warning, your live SONiC config may have additional databases (e.g. `PFC_WD_DB`, `SNMP_OVERLAY_DB`, `APPL_STATE_DB`, etc.) or different separators that the fallback doesn't cover.

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Health check — returns `{"status": "ok"}` |
| `GET /api/db-config` | Returns dynamic DB config as JSON |

Example response:
```json
{
  "source": "orb_vm_exec:sonic-lab:clab-sonic-ai-lab-sonic1:/var/run/redis/sonic-db/database_config.json",
  "used_fallback": false,
  "databases": {
    "APPL_DB":     {"id": 0, "separator": ":", "instance": "redis"},
    "CONFIG_DB":   {"id": 4, "separator": "|", "instance": "redis"},
    "STATE_DB":    {"id": 6, "separator": "|", "instance": "redis"}
  },
  "errors": []
}
```

---

## Project Structure (Step 1)

```text
pyproject.toml
.env.example

sonic_consistency_checker/
  __init__.py
  core/
    __init__.py
    db_constants.py          # fallback defaults only — not the source of truth
    db_config_loader.py      # dynamic loader (docker_exec, orb_vm_exec, local, fallback)
  cli/
    __init__.py
    main.py                  # sonic-checker db-config CLI (Typer + Rich)
  api/
    __init__.py
    main.py                  # FastAPI /health and /api/db-config
```
