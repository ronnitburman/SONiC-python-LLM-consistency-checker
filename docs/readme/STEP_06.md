# Step 6 — React UI Demo

Builds a React + TypeScript + Vite UI that talks to the FastAPI backend. All existing backend capabilities are exposed visually across five tabbed pages.

## Quick Start

```bash
# 1. Add custom domain to /etc/hosts (one-time)
echo "127.0.0.1 ronnit-sonic-project.com" | sudo tee -a /etc/hosts

# 2. Free port 80 if macOS Apache is running (one-time)
sudo apachectl stop 2>/dev/null

# 3. Start backend (requires SONiC connection — orb_vm_exec recommended)
source .venv/bin/activate
uvicorn sonic_consistency_checker.api.main:app --reload

# 4. Start UI on port 80 (separate terminal)
cd ui
npm install
sudo npm run dev

# 5. Open http://ronnit-sonic-project.com
```

---

## Why This Matters

The CLI is great for scripting, but a UI is better for demos and visual inspection. This step creates a clean single-page app that calls the same FastAPI backend. It's served under a custom local domain (`ronnit-sonic-project.com` via `/etc/hosts`) instead of `localhost:5173` for a professional demo experience.

> For the full architecture of the custom domain setup (DNS resolution, Vite host checking, CORS), see `docs/CODE_FLOW.md` section 14 or `docs/DESIGN_DECISIONS.md` Step 6.

---

## UI Pages

### Dashboard

One-screen health overview with **onboarding guide** for first-time users:

- Backend status, DB config source, fallback status, SWSS SDK availability
- DB sizes table
- **"Load Summary" button** — runs full health check (route drift, VLAN membership, LAG health)
- Health score (0–100) with color-coded bar and severity counts (Step 4A)
- Subsystem summary cards (Step 4A)

### DB Explorer

- Select DB from dropdown (populated dynamically from SONiC config)
- Enter scan pattern → click **Scan**
- Click a key → see hash fields and equivalent `redis-cli` command

### Port Explorer

- List of discovered ports → click to load
- Cross-DB view: CONFIG_DB, APPL_DB, STATE_DB with key-value tables
- Transceiver, Counters, ASIC_DB with JSON viewer
- Raw keys tracking + findings with structured cards
- Per-port health score and finding counts (Step 4A)

### Findings

- **Extended checks toggle** — include route/VLAN/LAG checks (Step 4A)
- Grouped by severity (critical / warning / info)
- Each finding: evidence, possible causes, suggested commands

### SWSS SDK Explorer

- SWSS SDK availability check
- ConfigDBConnector, SonicV2Connector, Table Reader sections
- **Compare Read** — raw Redis vs SWSS SDK side-by-side

All sections show equivalent Redis commands and raw JSON results.

---

## Connection Setup

The backend auto-detects connection mode from `.env`. For OrbStack VM:

```bash
# .env
SONIC_CONNECTION_MODE=orb_vm_exec
SONIC_CONTAINER_NAME=clab-sonic-ai-lab-sonic1
SONIC_ORB_VM_NAME=sonic-lab
```

Override API base URL for UI if needed:

```bash
# ui/.env
VITE_API_BASE_URL=http://localhost:8000
```

---

## API Endpoints Consumed

| Page | Endpoints | Trigger |
|------|-----------|---------|
| App (shared) | `/health`, `/api/db-config`, `/api/dbs`, `/api/ports`, `/api/swss/check` | On mount |
| Dashboard | `/api/summary` | "Load Summary" button |
| DB Explorer | `/api/dbs/{db}/keys`, `/api/dbs/{db}/key` | Scan / key click |
| Port Explorer | `/api/ports/{port}`, `/api/ports/{port}/summary` | Port click |
| Findings | `/api/findings?extended=...` | "Refresh" button |
| SWSS SDK | Various `/api/swss/*` | Action buttons |

---

## Project Structure

```text
ui/
  package.json              # React 19, Vite 6, TypeScript
  vite.config.ts            # Port 80, custom domain config
  tsconfig.json
  index.html
  src/
    main.tsx                # React entry
    App.tsx                 # Tab nav + shared data + page keep-alive
    api.ts                  # All fetch() wrappers
    types.ts                # TypeScript types (incl. Step 4A models)
    styles.css              # Plain CSS
    pages/
      Dashboard.tsx         # Onboarding guide + lazy summary
      DbExplorer.tsx        # Redis key explorer
      PortExplorer.tsx      # Port cross-DB view
      Findings.tsx          # All findings + extended toggle
      SwssSdkExplorer.tsx   # SDK comparison tool
    components/
      Card.tsx              # White card wrapper
      StatusBadge.tsx       # Color-coded pill badge
      JsonViewer.tsx        # Dark-themed JSON viewer
      FindingCard.tsx       # Finding with evidence/causes/commands
      KeyValueTable.tsx     # Two-column key-value display
      Section.tsx           # Page section header
```

### Backend Change

```text
sonic_consistency_checker/api/main.py  ← CORS middleware
```

---

## What This Step Does NOT Do

- LLM explanation page (Step 7)
- Real LLM API calls
- Authentication
- Write experiments UI
- Topology graph
