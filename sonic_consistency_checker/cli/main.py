"""CLI entry point for sonic-checker."""

from __future__ import annotations

from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.text import Text

from sonic_consistency_checker.core.db_config_loader import SonicDbConfigLoader
from sonic_consistency_checker.core.discovery import SonicDiscoveryService
from sonic_consistency_checker.core.redis_client import SonicRedisClient

load_dotenv()

app = typer.Typer(
    name="sonic-checker",
    help="SONiC consistency checker CLI",
    no_args_is_help=True,
)

console = Console()


@app.callback()
def main_callback() -> None:
    """SONiC consistency checker — Dynamic DB config & Redis explorer."""


# ---------------------------------------------------------------------------
# Step 1 — db-config
# ---------------------------------------------------------------------------

@app.command(name="db-config")
def db_config(
    connection_mode: Optional[str] = typer.Option(
        None,
        "--connection-mode",
        "-m",
        help="Connection mode: docker_exec, orb_vm_exec, or local_filesystem",
    ),
    container_name: Optional[str] = typer.Option(
        None,
        "--container-name",
        "-c",
        help="Docker container name for docker_exec/orb_vm_exec mode",
    ),
    orb_vm_name: Optional[str] = typer.Option(
        None,
        "--orb-vm-name",
        help="OrbStack VM name for orb_vm_exec mode (auto-detected if omitted)",
    ),
) -> None:
    """Load and display the dynamic SONiC Redis database configuration."""
    loader = SonicDbConfigLoader(
        connection_mode=connection_mode,
        container_name=container_name,
        orb_vm_name=orb_vm_name,
    )
    config = loader.load()

    # Header
    console.print()
    console.print(Text("SONiC DB Config", style="bold cyan"))
    console.print()

    # Source and fallback info
    console.print(f"Source: {config.source}")
    console.print(f"Used fallback: {config.used_fallback}")
    console.print()

    # Fallback warning
    if config.used_fallback:
        warning = Text(
            "Warning:\n"
            "  Could not read SONiC database_config.json.\n"
            "  Using fallback default DB IDs.",
            style="yellow",
        )
        console.print(warning)
        console.print()

    # Errors
    if config.errors:
        console.print(Text("Errors:", style="bold red"))
        for err in config.errors:
            console.print(f"  {err}")
        console.print()

    # DB mappings table
    console.print(Text("DB mappings:", style="bold green"))
    console.print()

    table = Table(show_header=True, header_style="bold")
    table.add_column("DB Name", style="cyan")
    table.add_column("ID", style="magenta", justify="right")
    table.add_column("Separator", style="yellow")
    table.add_column("Instance", style="green")

    for db_name, db_entry in config.databases.items():
        table.add_row(
            db_name,
            str(db_entry.id),
            f'"{db_entry.separator}"',
            f'"{db_entry.instance}"',
        )

    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# Step 2 — Redis DB Explorer
# ---------------------------------------------------------------------------

@app.command(name="dbs")
def list_dbs(
    connection_mode: Optional[str] = typer.Option(
        None,
        "--connection-mode",
        "-m",
        help="Connection mode: docker_exec, orb_vm_exec, or local_redis",
    ),
    container_name: Optional[str] = typer.Option(
        None,
        "--container-name",
        "-c",
        help="Docker container name for docker_exec/orb_vm_exec mode",
    ),
    orb_vm_name: Optional[str] = typer.Option(
        None,
        "--orb-vm-name",
        help="OrbStack VM name for orb_vm_exec mode (auto-detected if omitted)",
    ),
) -> None:
    """Show all SONiC Redis DB sizes (key counts)."""
    svc = SonicDiscoveryService(
        redis_client=SonicRedisClient(
            connection_mode=connection_mode,
            container_name=container_name,
            orb_vm_name=orb_vm_name,
        )
    )
    sizes = svc.list_db_sizes()

    console.print()
    console.print(Text("SONiC Redis DBs", style="bold cyan"))
    console.print()

    # Show source info
    db_cfg = svc.redis_client.db_config
    console.print(f"Source: {db_cfg.source}")
    console.print(f"Used fallback: {db_cfg.used_fallback}")
    console.print()

    table = Table(show_header=True, header_style="bold")
    table.add_column("DB Name", style="cyan")
    table.add_column("ID", style="magenta", justify="right")
    table.add_column("Keys", style="green", justify="right")

    for s in sizes:
        size_str = str(s.size) if s.size >= 0 else "err"
        table.add_row(s.db_name, str(s.db_id), size_str)

    console.print(table)
    console.print()


@app.command(name="keys")
def scan_keys(
    db_name: str = typer.Argument(..., help="SONiC DB name, e.g. CONFIG_DB"),
    pattern: str = typer.Argument("*", help="Key pattern, e.g. PORT*"),
    connection_mode: Optional[str] = typer.Option(
        None,
        "--connection-mode",
        "-m",
        help="Connection mode: docker_exec, orb_vm_exec, or local_redis",
    ),
    container_name: Optional[str] = typer.Option(
        None,
        "--container-name",
        "-c",
        help="Docker container name for docker_exec/orb_vm_exec mode",
    ),
    orb_vm_name: Optional[str] = typer.Option(
        None,
        "--orb-vm-name",
        help="OrbStack VM name for orb_vm_exec mode (auto-detected if omitted)",
    ),
) -> None:
    """Scan keys in a SONiC Redis DB using SCAN."""
    svc = SonicDiscoveryService(
        redis_client=SonicRedisClient(
            connection_mode=connection_mode,
            container_name=container_name,
            orb_vm_name=orb_vm_name,
        )
    )
    result = svc.scan_db(db_name, pattern)

    console.print()
    console.print(f"DB: [cyan]{result.db_name}[/cyan]")
    console.print(f"Pattern: [yellow]{result.pattern}[/yellow]")
    console.print()
    console.print(Text("Equivalent Redis:", style="bold"))
    console.print(f"  {result.equivalent_redis}")
    console.print()

    if not result.keys:
        console.print(Text("(no keys found)", style="dim"))
    else:
        console.print(Text("Keys:", style="bold"))
        for key in result.keys:
            console.print(f"  {key}")

    console.print()


@app.command(name="hget")
def hget_key(
    db_name: str = typer.Argument(..., help="SONiC DB name, e.g. CONFIG_DB"),
    key: str = typer.Argument(..., help="Redis key, e.g. PORT|Ethernet0"),
    connection_mode: Optional[str] = typer.Option(
        None,
        "--connection-mode",
        "-m",
        help="Connection mode: docker_exec, orb_vm_exec, or local_redis",
    ),
    container_name: Optional[str] = typer.Option(
        None,
        "--container-name",
        "-c",
        help="Docker container name for docker_exec/orb_vm_exec mode",
    ),
    orb_vm_name: Optional[str] = typer.Option(
        None,
        "--orb-vm-name",
        help="OrbStack VM name for orb_vm_exec mode (auto-detected if omitted)",
    ),
) -> None:
    """Read all hash fields from a key using HGETALL."""
    svc = SonicDiscoveryService(
        redis_client=SonicRedisClient(
            connection_mode=connection_mode,
            container_name=container_name,
            orb_vm_name=orb_vm_name,
        )
    )
    result = svc.read_key(db_name, key)

    console.print()
    console.print(f"DB: [cyan]{result.db_name}[/cyan]")
    console.print(f"Key: [yellow]{result.key}[/yellow]")
    console.print(f"Type: [magenta]{result.key_type}[/magenta]")
    console.print()
    console.print(Text("Equivalent Redis:", style="bold"))
    console.print(f"  {result.equivalent_redis}")
    console.print()

    if not result.fields:
        console.print(Text("No hash fields found.", style="dim"))
    else:
        console.print(Text("Fields:", style="bold"))
        for field_name, field_value in result.fields.items():
            console.print(f"  {field_name}: {field_value}")

    console.print()


@app.command(name="type")
def key_type_cmd(
    db_name: str = typer.Argument(..., help="SONiC DB name, e.g. CONFIG_DB"),
    key: str = typer.Argument(..., help="Redis key, e.g. PORT|Ethernet0"),
    connection_mode: Optional[str] = typer.Option(
        None,
        "--connection-mode",
        "-m",
        help="Connection mode: docker_exec, orb_vm_exec, or local_redis",
    ),
    container_name: Optional[str] = typer.Option(
        None,
        "--container-name",
        "-c",
        help="Docker container name for docker_exec/orb_vm_exec mode",
    ),
    orb_vm_name: Optional[str] = typer.Option(
        None,
        "--orb-vm-name",
        help="OrbStack VM name for orb_vm_exec mode (auto-detected if omitted)",
    ),
) -> None:
    """Show the Redis type of a key."""
    svc = SonicDiscoveryService(
        redis_client=SonicRedisClient(
            connection_mode=connection_mode,
            container_name=container_name,
            orb_vm_name=orb_vm_name,
        )
    )
    result = svc.key_type(db_name, key)

    console.print()
    console.print(f"DB: [cyan]{result.db_name}[/cyan]")
    console.print(f"Key: [yellow]{result.key}[/yellow]")
    console.print(f"Type: [magenta]{result.key_type}[/magenta]")
    console.print()


if __name__ == "__main__":
    app()
