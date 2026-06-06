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
from sonic_consistency_checker.core.models import Finding
from sonic_consistency_checker.sonic.ports import PortService

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


SEVERITY_STYLES = {
    "critical": "bold red",
    "warning": "yellow",
    "info": "cyan",
}


def _print_finding(finding: Finding) -> None:
    """Print a single Finding with Rich formatting."""
    sev_style = SEVERITY_STYLES.get(finding.severity, "white")
    console.print(
        Text(
            f"[{finding.severity}] {finding.category} — {finding.object_name}",
            style=sev_style,
        )
    )
    console.print(finding.summary)
    console.print()

    if finding.evidence:
        console.print(Text("Evidence:", style="bold"))
        for k, v in finding.evidence.items():
            console.print(f"  {k}: {v}")
        console.print()

    if finding.possible_causes:
        console.print(Text("Possible causes:", style="bold"))
        for cause in finding.possible_causes:
            console.print(f"  - {cause}")
        console.print()

    if finding.suggested_commands:
        console.print(Text("Suggested commands:", style="bold"))
        for cmd in finding.suggested_commands:
            console.print(f"  - {cmd}")
        console.print()


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


# ---------------------------------------------------------------------------
# Step 3 — Normalized Port View
# ---------------------------------------------------------------------------


@app.command(name="ports")
def list_ports(
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
    """List all discovered SONiC port names from CONFIG_DB."""
    svc = PortService(
        redis_client=SonicRedisClient(
            connection_mode=connection_mode,
            container_name=container_name,
            orb_vm_name=orb_vm_name,
        )
    )
    result = svc.list_config_ports()

    console.print()
    console.print(Text("Discovered Ports", style="bold cyan"))
    console.print()
    console.print(f"Source: {result.source}")
    console.print()

    if not result.ports:
        console.print(Text("(no ports found)", style="dim"))
    else:
        console.print(Text("Ports:", style="bold"))
        for port in result.ports:
            console.print(f"  {port}")

    console.print()


@app.command(name="port")
def show_port(
    port_name: str = typer.Argument(..., help="Port name, e.g. Ethernet0"),
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
    """Show a normalized cross-DB view of a single SONiC port."""
    svc = PortService(
        redis_client=SonicRedisClient(
            connection_mode=connection_mode,
            container_name=container_name,
            orb_vm_name=orb_vm_name,
        )
    )
    view = svc.get_port_view(port_name)

    def _print_section(
        title: str,
        data: dict[str, Any],
        raw_keys: list[str] | None = None,
    ) -> None:
        console.print(Text(title, style="bold magenta"))
        if raw_keys:
            for rk in raw_keys:
                console.print(f"  Key: [yellow]{rk}[/yellow]")
        if not data:
            console.print(Text("  No data found.", style="dim"))
        else:
            for k, v in data.items():
                if isinstance(v, dict):
                    # Nested dict (e.g. transceiver key → fields)
                    if v:
                        console.print(f"  [yellow]{k}[/yellow]")
                        for fk, fv in v.items():
                            console.print(f"    {fk}: {fv}")
                    else:
                        console.print(f"  [yellow]{k}[/yellow]")
                        console.print(Text("    (empty hash)", style="dim"))
                else:
                    console.print(f"  {k}: {v}")
        console.print()

    console.print()
    console.print(f"Port: [cyan]{view.name}[/cyan]", style="bold")
    console.print()

    # CONFIG_DB
    _print_section(
        "CONFIG_DB",
        view.config,
        raw_keys=view.raw_keys.get("CONFIG_DB"),
    )

    # APPL_DB
    _print_section(
        "APPL_DB",
        view.app,
        raw_keys=view.raw_keys.get("APPL_DB"),
    )

    # STATE_DB
    _print_section(
        "STATE_DB",
        view.state,
        raw_keys=[
            k for k in view.raw_keys.get("STATE_DB", [])
            if not k.startswith("TRANSCEIVER")
        ] or None,
    )

    # TRANSCEIVER
    tx_keys = [
        k for k in view.raw_keys.get("STATE_DB", [])
        if k.startswith("TRANSCEIVER")
    ]
    _print_section(
        "TRANSCEIVER",
        view.transceiver,
        raw_keys=tx_keys or None,
    )

    # COUNTERS_DB
    _print_section(
        "COUNTERS_DB",
        view.counters,
        raw_keys=view.raw_keys.get("COUNTERS_DB"),
    )

    # ASIC_DB
    _print_section(
        "ASIC_DB",
        view.asic,
        raw_keys=view.raw_keys.get("ASIC_DB"),
    )

    # FINDINGS
    console.print(Text("FINDINGS", style="bold magenta"))
    if not view.findings:
        console.print(Text("  No findings.", style="dim"))
    else:
        console.print()
        for finding in view.findings:
            _print_finding(finding)


# ---------------------------------------------------------------------------
# Step 4 — Consistency Checks
# ---------------------------------------------------------------------------


@app.command(name="findings")
def all_findings(
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
    """Run consistency checks on all discovered ports."""
    svc = PortService(
        redis_client=SonicRedisClient(
            connection_mode=connection_mode,
            container_name=container_name,
            orb_vm_name=orb_vm_name,
        )
    )
    port_views = svc.list_port_views()

    all_f: list[Finding] = []
    for pv in port_views:
        all_f.extend(pv.findings)

    console.print()
    console.print(Text("Findings", style="bold cyan"))
    console.print()

    if not all_f:
        console.print(Text("No findings found.", style="dim"))
    else:
        for finding in all_f:
            _print_finding(finding)

    console.print()


@app.command(name="check-port")
def check_port(
    port_name: str = typer.Argument(..., help="Port name, e.g. Ethernet0"),
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
    """Run consistency checks on a single port."""
    svc = PortService(
        redis_client=SonicRedisClient(
            connection_mode=connection_mode,
            container_name=container_name,
            orb_vm_name=orb_vm_name,
        )
    )
    view = svc.get_port_view(port_name)

    console.print()
    console.print(
        Text(f"Findings for {view.name}", style="bold cyan")
    )
    console.print()

    if not view.findings:
        console.print(Text(f"No findings for {view.name}.", style="dim"))
    else:
        for finding in view.findings:
            _print_finding(finding)

    console.print()


if __name__ == "__main__":
    app()
