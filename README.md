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
| 5 | SWSS SDK Explorer | *(coming)* |
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
