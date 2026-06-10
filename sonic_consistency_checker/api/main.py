"""FastAPI backend for SONiC consistency checker."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sonic_consistency_checker.core.db_config_loader import SonicDbConfigLoader
from sonic_consistency_checker.api.routes_dbs import router as dbs_router
from sonic_consistency_checker.api.routes_ports import router as ports_router
from sonic_consistency_checker.api.routes_findings import router as findings_router
from sonic_consistency_checker.api.routes_swss import router as swss_router
from sonic_consistency_checker.api.routes_ai import router as ai_router

load_dotenv()

# Ensure AI component logs are visible in the uvicorn console.
# (uvicorn only routes its own logger by default; this makes our
# chat_agent, mcp_bridge, and model_provider loggers visible too.)
for _name in (
    "sonic_consistency_checker.ai",
    "sonic_consistency_checker.ai.chat_agent",
    "sonic_consistency_checker.ai.mcp_bridge",
    "sonic_consistency_checker.ai.model_provider",
):
    _lg = logging.getLogger(_name)
    _lg.setLevel(logging.INFO)
    if not _lg.handlers:
        _lg.addHandler(logging.StreamHandler())

app = FastAPI(
    title="SONiC Consistency Checker API",
    version="0.1.0",
)


@app.on_event("startup")
async def _startup_banner() -> None:
    """Print configuration summary on startup."""
    logger = logging.getLogger("uvicorn")
    provider = os.getenv("LLM_PROVIDER", "not set")
    if provider == "deepseek":
        model = os.getenv("DEEPSEEK_MODEL", "not set")
    elif provider == "ollama":
        model = os.getenv("OLLAMA_MODEL", "not set")
    else:
        model = "not set"
    mcp_url = os.getenv("SONIC_MCP_URL", "not set")
    conn_mode = os.getenv("SONIC_CONNECTION_MODE", "not set")
    logger.info("─" * 60)
    logger.info("LLM:       %s → %s", provider, model)
    logger.info("MCP URL:   %s", mcp_url)
    logger.info("Conn mode: %s", conn_mode)
    logger.info("─" * 60)

# Allow the Vite dev server to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://ronnit-sonic-project.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dbs_router)
app.include_router(ports_router)
app.include_router(findings_router)
app.include_router(swss_router)
app.include_router(ai_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/api/db-config")
async def api_db_config() -> JSONResponse:
    """Return the dynamic SONiC Redis database configuration as JSON."""
    loader = SonicDbConfigLoader(
        connection_mode=os.getenv("SONIC_CONNECTION_MODE"),
        container_name=os.getenv("SONIC_CONTAINER_NAME"),
        orb_vm_name=os.getenv("SONIC_ORB_VM_NAME"),
    )
    config = loader.load()

    databases = {
        db_name: {
            "id": db_entry.id,
            "separator": db_entry.separator,
            "instance": db_entry.instance,
        }
        for db_name, db_entry in config.databases.items()
    }

    return JSONResponse(
        content={
            "source": config.source,
            "used_fallback": config.used_fallback,
            "databases": databases,
            "errors": config.errors,
        }
    )
