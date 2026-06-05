"""Fallback defaults and common names for SONiC Redis databases.

These are **not** the primary source of truth.
The real DB IDs, separators, and instances come from SONiC's
database_config.json, loaded dynamically by db_config_loader.py.
"""

FALLBACK_DATABASES: dict[str, dict[str, int | str]] = {
    "APPL_DB":      {"id": 0, "separator": ":", "instance": "redis"},
    "ASIC_DB":      {"id": 1, "separator": ":", "instance": "redis"},
    "COUNTERS_DB":  {"id": 2, "separator": ":", "instance": "redis"},
    "CONFIG_DB":    {"id": 4, "separator": "|", "instance": "redis"},
    "STATE_DB":     {"id": 6, "separator": ":", "instance": "redis"},
}

COMMON_DB_NAMES = [
    "APPL_DB",
    "ASIC_DB",
    "COUNTERS_DB",
    "CONFIG_DB",
    "STATE_DB",
]

DEFAULT_DATABASE_CONFIG_PATHS = [
    "/var/run/redis/sonic-db/database_config.json",
    "/etc/sonic/database_config.json",
]
