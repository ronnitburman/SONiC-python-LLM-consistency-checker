"""Write safety — prevents accidental writes to real SONiC tables."""

from __future__ import annotations

PROTECTED_TABLE_PREFIXES: list[str] = [
    "PORT",
    "PORT_TABLE",
    "ROUTE_TABLE",
    "NEIGH_TABLE",
    "VLAN",
    "ASIC_STATE",
    "INTF_TABLE",
    "LAG_TABLE",
]

ALLOWED_TEST_TABLE_PREFIXES: list[str] = [
    "SONIC_AI_LAB_TEST",
]


def validate_write_allowed(table_name: str, allow_writes: bool) -> None:
    """Raise PermissionError unless writes are explicitly enabled
    and the table is an allowed test table."""

    if not allow_writes:
        raise PermissionError(
            "Writes are disabled. Pass --allow-writes to continue."
        )

    if not any(
        table_name.startswith(prefix)
        for prefix in ALLOWED_TEST_TABLE_PREFIXES
    ):
        raise PermissionError(
            f"Refusing to write to table '{table_name}'. "
            "Only SONIC_AI_LAB_TEST* tables are allowed by default."
        )
