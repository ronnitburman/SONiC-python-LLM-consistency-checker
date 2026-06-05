"""FastAPI backend for SONiC consistency checker."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from sonic_consistency_checker.core.db_config_loader import SonicDbConfigLoader
from sonic_consistency_checker.api.routes_dbs import router as dbs_router

load_dotenv()

app = FastAPI(
    title="SONiC Consistency Checker API",
    version="0.1.0",
)

app.include_router(dbs_router)


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
