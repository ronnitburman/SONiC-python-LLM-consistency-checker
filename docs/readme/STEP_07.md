# Step 7 — AI Chat Agent + LangGraph + MCP Tool Calling

Adds a conversational AI diagnostic agent powered by LangGraph that can inspect the SONiC switch, load domain knowledge on demand, and call MCP diagnostic tools.

## Quick Start

```bash
# 1. Start MCP server (terminal 1)
.venv/bin/python sonic_mcp_server.py

# 2. Start backend (terminal 2)
source .venv/bin/activate
uvicorn sonic_consistency_checker.api.main:app --reload

# 3. Configure LLM provider in .env
LLM_PROVIDER=deepseek          # or ollama
DEEPSEEK_API_KEY=sk-xxx

# 4. Chat via CLI
sonic-checker chat
# You: Why is Ethernet0 down?
# Agent: [calls sonic_get_port_view] ...diagnosis...

# 5. Chat via API
curl -X POST http://localhost:8000/api/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Run a full health check"}]}'

# 6. Chat via UI
cd ui && sudo npm run dev
# → http://ronnit-sonic-project.com → AI Chat tab
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  User (CLI / API / UI chat)                             │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│  ChatAgent (LangGraph StateGraph)                       │
│                                                         │
│  ┌──────────┐   ┌──────────┐   ┌──────────────────┐   │
│  │  Agent   │──▶│  Router  │──▶│  Tool Executor   │   │
│  │  Node    │◀──│          │   │                  │   │
│  └──────────┘   └──────────┘   └──────────────────┘   │
│       │              │                  │               │
│       │  System      │  Tool call?      │  Execute      │
│       │  Prompt      │  Y → tools       │  tool,        │
│       │  (lean)      │  N → END         │  return result │
│       │              │                  │               │
│       │  Tools: 11 total                              │
│       │  ├── read_skill / list_skills (skill loader)  │
│       │  └── 9 MCP diagnostic tools                   │
└───────┼──────────────────────────────────────────────┘
        │
┌───────▼──────────────────────────────────────────────┐
│  MCP Server (.venv/bin/python sonic_mcp_server.py)   │
│  sonic_db_config, sonic_get_port_view, etc.          │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│  SonicRedisClient → SONiC Switch (orb VM)            │
└──────────────────────────────────────────────────────┘
```

---

## Skill System

The agent loads domain knowledge on demand — no bloated system prompts:

| Tool | Purpose |
|------|---------|
| `list_skills_tool()` | Discover available skill documents |
| `read_skill_tool("sonic")` | Load SONiC architecture, DB layout, service workflows |

**How it works:**

```
User: "Why is Ethernet0 down?"
Agent:
  1. [calls read_skill_tool("sonic")]  ← loads 17KB SONiC knowledge
  2. [calls sonic_get_port_view("Ethernet0")]
  3. Analyzes: CONFIG_DB admin=up, STATE_DB oper=down
  4. Explains using skill knowledge: "This is a goal-state vs current-state mismatch..."
```

**Adding new skills** — drop a directory under `.pi/skills/`:

```text
.pi/skills/
  sonic/SKILL.md       ← 17KB SONiC knowledge
  bgp/SKILL.md         ← future
  frr/SKILL.md         ← future
```

No code changes needed — `list_skills()` auto-discovers them.

---

## Tools (11 total)

| Tool | Source | Description |
|------|--------|-------------|
| `list_skills_tool` | Skill loader | List available skill documents |
| `read_skill_tool` | Skill loader | Load a skill document on demand |
| `sonic_db_config` | MCP bridge | Dynamic Redis DB configuration |
| `sonic_list_dbs` | MCP bridge | All DBs with key counts |
| `sonic_scan_keys` | MCP bridge | Scan keys in any DB (safe, SCAN-based) |
| `sonic_hget` | MCP bridge | Read hash fields from a key |
| `sonic_key_type` | MCP bridge | Redis key type |
| `sonic_list_ports` | MCP bridge | All discovered port names |
| `sonic_get_port_view` | MCP bridge | **Primary diagnostic** — full cross-DB port view |
| `sonic_check_port` | MCP bridge | Consistency checks on one port |
| `sonic_check_all_ports` | MCP bridge | Switch-wide consistency checks |

---

## Model Providers

| Provider | Config | Use Case |
|----------|--------|----------|
| **DeepSeek** | `LLM_PROVIDER=deepseek` + API key | Cloud — best quality, needs internet |
| **Ollama** | `LLM_PROVIDER=ollama` + local server | Local — fully offline, free |

Both use OpenAI-compatible APIs — configured via `ai/model_provider.py`.

```bash
# .env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_MODEL=deepseek-chat

# Or for Ollama:
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2:latest
```

---

## CLI: `sonic-checker chat`

```bash
sonic-checker chat

SONiC AI Diagnostic Agent
Type /reset to clear, /exit to quit

You: Run a full health check

Agent: [calls sonic_check_all_ports]
       Found 3 issues: ...
You: Why is Ethernet0 down?

Agent: [calls sonic_get_port_view("Ethernet0")]
       Ethernet0 is admin-up but oper-down...
```

Commands inside chat:
- `/reset` — start new conversation
- `/exit` — quit

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/ai/chat` | Send message to agent |
| `POST /api/ai/chat/reset` | Reset conversation |
| `GET /api/ai/explain-port/{port_name}` | Deterministic template explanations |

### Chat Request

```json
{
  "messages": [
    {"role": "user", "content": "Why is Ethernet0 down?"}
  ]
}
```

### Chat Response

```json
{
  "response": "Ethernet0 is configured as admin-up but...",
  "conversation_id": "a1b2c3d4e5f6",
  "tool_calls": [],
  "findings_referenced": []
}
```

---

## Project Structure (Step 7 additions)

```text
sonic_consistency_checker/
  ai/                              # NEW package
    __init__.py
    models.py                      # ChatMessage, ChatResponse, FindingExplanation
    model_provider.py              # get_llm() → DeepSeek or Ollama
    skill_loader.py                # list_skills(), read_skill()
    prompt_templates.py            # Lean system prompt
    mcp_bridge.py                  # call_mcp_tool() → HTTP JSON-RPC
    tools.py                       # 11 LangChain tools
    chat_agent.py                  # LangGraph StateGraph + ChatAgent class
    explanation_agent.py           # DeterministicExplanationAgent (fallback)
  api/
    routes_ai.py                   # /api/ai/chat, /api/ai/explain-port
  cli/
    main.py                        # + chat command
ui/
  src/
    pages/
      Chat.tsx                     # NEW — conversational chat UI
    App.tsx                        # + AI Chat tab
    types.ts                       # + ChatMessage type
```

---

## What This Step Does NOT Do

- Streaming responses (returns full response)
- Multi-conversation support (single agent singleton)
- Write operations (agent cannot modify switch state)
- Automatic remediation (suggests commands, doesn't run them)
