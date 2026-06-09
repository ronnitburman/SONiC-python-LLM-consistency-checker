# Step 4A — Extended Consistency Checks & Diagnostic Summary

Amends Step 4 with four enhancements from the code review:

1. **APPL_DB write-back path covered** — oper_status checked in both STATE_DB and APPL_DB
2. **Route table drift detection** — compares APPL_DB ROUTE_TABLE count vs ASIC_DB route entry count
3. **VLAN membership and LAG member checks** — finds mismatches between CONFIG_DB and APPL_DB
4. **Diagnostic health summary** — aggregates findings into a one-screen dashboard with health score

## Quick Start

```bash
# Full health dashboard (all subsystems)
sonic-checker summary

# All findings now include route/VLAN/LAG checks + summary
sonic-checker findings

# Per-port check includes per-port summary
sonic-checker check-port Ethernet0

# API — diagnostic summary
uvicorn sonic_consistency_checker.api.main:app --reload
curl http://localhost:8000/api/summary
curl http://localhost:8000/api/ports/Ethernet0/summary
curl http://localhost:8000/api/findings?extended=true
```

---

## New CLI Commands

### `sonic-checker summary` — Diagnostic health dashboard

Runs all checks (ports, routes, VLANs, LAGs) and produces a one-screen health overview.

```bash
sonic-checker summary -m orb_vm_exec
```

Example output:

```
========================================================
Diagnostic Summary
========================================================

  ✓ Overall: 90/100 — WARNING

Findings:
  Critical    0
  Warning     1
  Info        2
  Total       3

By Category:
  PORT_COUNTERS_MISSING       1
  PORT_MISSING_IN_STATE_DB    1
  ROUTE_TABLE_DRIFT           1

Route Table:
  ✓ APPL_DB routes: 42
     ASIC_DB routes: 42

VLAN Membership:
  ✓ Status: OK

LAG Member Health:
  ✓ Status: OK
========================================================
```

### Updated `sonic-checker findings`

Now runs port checks **plus** route drift, VLAN membership, and LAG member checks. Shows a diagnostic summary at the end.

### Updated `sonic-checker check-port`

Port findings are now followed by a per-port mini-summary with severity counts and health score.

---

## New Checks

| Check | Severity | Condition |
|---|---|---|
| `ROUTE_TABLE_DRIFT` | **critical** | APPL_DB ROUTE_TABLE count ≠ ASIC_DB route entry count |
| `VLAN_MEMBERSHIP_MISMATCH` | warning | Port in CONFIG_DB VLAN but not in APPL_DB |
| `VLAN_MEMBERSHIP_MISMATCH` | info | Port in APPL_DB VLAN but not in CONFIG_DB (stale) |
| `LAG_MEMBER_MISMATCH` | warning | LAG member in CONFIG_DB but not in APPL_DB |
| `LAG_MEMBER_MISMATCH` | info | LAG member in APPL_DB but not in CONFIG_DB (stale) |

### Updated Check

| Check | Change |
|---|---|
| `PORT_ADMIN_UP_OPER_DOWN` | Now checks **both** STATE_DB and APPL_DB for oper_status (covers natsyncd write-back path) |

---

## Health Score

| Severity | Deduction |
|----------|-----------|
| critical | −25 points per finding |
| warning | −10 points per finding |
| info | −3 points per finding |

All severities contribute cumulatively. Floor is 0.

- **100**: No findings — all clear
- **90–99**: Info/warning findings only — mostly healthy
- **50–89**: Warnings present — investigate
- **0–49**: Critical issues — immediate action needed

---

## API Endpoints (New/Updated)

| Endpoint | Description |
|---|---|
| `GET /api/summary` | Diagnostic summary across all subsystems |
| `GET /api/summary?extended=false` | Port-only summary |
| `GET /api/ports/{port_name}/summary` | Per-port diagnostic summary |
| `GET /api/findings?extended=true` | All findings including route/VLAN/LAG |

### `GET /api/summary`

```json
{
  "total_findings": 3,
  "critical_count": 0,
  "warning_count": 1,
  "info_count": 2,
  "categories": {
    "PORT_COUNTERS_MISSING": 1,
    "ROUTE_TABLE_DRIFT": 1,
    "PORT_MISSING_IN_STATE_DB": 1
  },
  "port_checks": {
    "PORT_COUNTERS_MISSING": 1,
    "PORT_MISSING_IN_STATE_DB": 1
  },
  "route_drift": {
    "appl_route_count": 42,
    "asic_route_count": 42,
    "drift": 0,
    "status": "ok"
  },
  "vlan_membership": {
    "config_vlan_count": 4,
    "app_vlan_count": 4,
    "vlans_with_mismatch": [],
    "status": "ok"
  },
  "lag_member_health": {
    "config_lag_count": 2,
    "app_lag_count": 2,
    "lags_with_mismatch": [],
    "status": "ok"
  },
  "overall_health_score": 90,
  "overall_status": "warning"
}
```

---

## Connection Modes

Same as previous steps. All modes supported.

```bash
sonic-checker summary -m docker_exec -c my-container
sonic-checker summary -m orb_vm_exec
```

---

## Project Structure (Steps 1–4A)

```text
sonic_consistency_checker/
  __init__.py
  core/
    __init__.py
    db_constants.py
    db_config_loader.py
    models.py                # + DiagnosticSummary, RouteDriftSummary, etc.
    redis_client.py
    discovery.py
    diff_engine.py           # + check_all(), route/VLAN/LAG checks + APPL_DB fix
    summary.py               # NEW — SummaryEngine
  sonic/
    __init__.py
    ports.py
  cli/
    __init__.py
    main.py                  # + summary command; findings/check-port show summary
  api/
    __init__.py
    main.py
    routes_dbs.py
    routes_ports.py
    routes_findings.py       # + summary endpoints, ?extended param
    routes_swss.py
```

---

## What This Step Does NOT Do

- Deep per-route comparison (route count only — full route comparison in future step)
- ACL rule propagation checks
- Neighbor table staleness checks
- Buffer profile drift checks
- PFC watchdog checks
