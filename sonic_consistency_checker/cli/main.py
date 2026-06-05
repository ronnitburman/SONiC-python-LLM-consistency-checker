"""CLI entry point for sonic-checker."""

from __future__ import annotations

from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.text import Text

from sonic_consistency_checker.core.db_config_loader import SonicDbConfigLoader

load_dotenv()

app = typer.Typer(
    name="sonic-checker",
    help="SONiC consistency checker CLI",
    no_args_is_help=True,
)

console = Console()


@app.callback()
def main_callback() -> None:
    """SONiC consistency checker — Step 1: Dynamic DB Config Discovery."""


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


if __name__ == "__main__":
    app()
