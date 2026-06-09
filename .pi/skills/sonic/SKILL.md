---
name: sonic
description: Comprehensive SONiC (Software for Open Networking in the Cloud) network operating system knowledge. Covers architecture, Redis database layout, Docker containerization, SAI abstraction, service workflows, BGP, syncd, orchagent, and communication patterns. Use when working with SONiC-based switches, SONiC container environments, Redis-based switch state, or any SONiC development/debugging tasks.
---

# SONiC Knowledge Base

This skill provides comprehensive knowledge of SONiC derived from the [sonic-book](https://r12f.com/sonic-book/1-intro.html), a thorough guide to getting started with SONiC.

## Overview

SONiC is an open-source network operating system (NOS) developed by Microsoft based on Debian, initiated in 2016. It is built on three core principles:

1. **Hardware-Software Decoupling**: Abstracts hardware through the Switch Abstraction Interface (SAI), enabling multi-vendor platform support.
2. **Microservices with Docker Containers**: Main functionalities are divided into individual Docker containers, enabling granular upgrades without full system restarts.
3. **Redis as Central Database**: Configuration and status are stored in a central Redis database (sonic-db), providing pub/sub communication and unified state management.

## Architecture

The core architectural pattern: services communicate through Redis, which acts as both a database and a message bus. The data flow follows:

```
CLI/REST API → CONFIG_DB → *mgrd services → APPL_DB → orchagent → ASIC_DB → syncd → SAI → ASIC Hardware
                                                                                         ↓
STATE_DB ← *syncd services ← netlink/kernel events ←─────────────────────────────────┘
```

Key insight: SONiC maintains the **Goal State** (desired configuration) and **Current State** (actual hardware state). When they diverge, reconciliation re-applies configuration until they are consistent.

---

## Redis Database Layout

SONiC creates a Redis instance named `sonic-db`. The database configuration is at `database_config.json` (`/var/run/redis/sonic-db/database_config.json`). Key databases:

| DB | ID | Separator | Purpose |
|----|-----|-----------|---------|
| **APPL_DB** | 0 | `:` | Internal state info for services — both computed Goal State and ASIC state write-backs |
| **ASIC_DB** | 1 | `:` | Desired state of switch ASIC (ACL, routing, etc.) — designed for ASIC data model |
| **COUNTERS_DB** | 2 | `:` | Statistics and counters |
| **LOGLEVEL_DB** | 3 | `:` | Log level configuration |
| **CONFIG_DB** | 4 | `\|` | User-facing configuration (ports, VLANs, etc.) — the **desired state** as intended by users |
| **PFC_WD_DB** | 5 | `:` | PFC watchdog |
| **FLEX_COUNTER_DB** | 5 | `:` | Flexible counters |
| **STATE_DB** | 6 | `\|` | Current state of switch components — hardware state from *syncd services |
| **SNMP_OVERLAY_DB** | 7 | `\|` | SNMP overlay data |
| **RESTAPI_DB** | 8 | `\|` | REST API data |
| **GB_ASIC_DB** | 9 | `:` | Gearbox ASIC |
| **GB_COUNTERS_DB** | 10 | `:` | Gearbox counters |
| **GB_FLEX_COUNTER_DB** | 11 | `:` | Gearbox flex counters |
| **APPL_STATE_DB** | 14 | `:` | Application state |

### Table Partitioning

Redis has no native table concept, so SONiC embeds the table name in the key with a separator:
- **CONFIG_DB and STATE_DB**: use `|` separator → `PORT|Ethernet0`
- **All other DBs**: use `:` separator → `PORT_TABLE:Ethernet4`

Each "table" is a Redis hash. Example query:
```bash
redis-cli -n 4 hgetall "PORT|Ethernet0"
# Returns: admin_status, mtu, speed, lanes, alias, index, oper_status, description
```

### Inter-Container Access

Redis is accessed via **Unix socket** (`/var/run/redis/redis.sock`). The `/var/run/redis` directory is bind-mounted into all relevant containers.

---

## Core Containers

### database
Contains the central Redis instance. Runs `redis-server 127.0.0.1:6379`.

### swss (SWitch State Service) — THE BRAIN
The most critical container. Runs:
- **orchagent**: The orchestrator — reads states from APPL_DB, computes ASIC configuration, writes to ASIC_DB
- ***syncd services**: Synchronize hardware state to Redis (portsyncd, neighsyncd, fdbsyncd, natsyncd)
- ***mgrd services**: Deploy configuration from Redis to hardware (portmgrd, intfmgrd, vlanmgrd, nbrmgrd, vrfmgrd, buffermgrd, coppmgrd, tunnelmgrd, vxlanmgrd)

### syncd (ASIC Management)
Manages the ASIC via SAI. Runs the `syncd` process that:
- As ***mgrd**: Listens to ASIC_DB changes, calls SAI API to deploy to hardware
- As ***syncd**: Receives ASIC notifications, publishes to Redis for orchagent/*mgrd consumption
- Loads vendor `.so` files (`libsai.so`) implementing the SAI interface

### bgp
Runs FRRouting (FRR) for BGP and other routing protocols. Contains:
- **bgpd**: BGP protocol daemon
- **zebra**: Route selection and kernel synchronization
- **fpmsyncd**: Listens to kernel routing updates, synchronizes to APPL_DB

### lldp
Implements LLDP (Link Layer Discovery Protocol). Contains lldpd, lldpmgrd, lldpsyncd.

### teamd
Implements Link Aggregation (LAG). Contains teamd, teamsyncd.

### snmp
Implements SNMP protocol. Contains snmpd.

### pmon (Platform Monitor)
Monitors hardware: temperature (thermalctld), power supplies (psud), fans, SFP/QSFP transceivers (xcvrd), LEDs (ledd), PCIe (pcied), EEPROM (syseepromd).

### mgmt-framework
Provides REST API (`rest_server`) and gNMI interfaces for programmatic configuration. CLI calls go through this REST API.

### eventd
Event handling container.

### radv
Router advertisement daemon.

---

## Service Categories and Control Flows

### *syncd Services (State Synchronization)
Names ending in `syncd`. Synchronize hardware states **into** Redis (APPL_DB or STATE_DB):
- **portsyncd**: Listens to netlink events, syncs port status to STATE_DB
- **neighsyncd**: Syncs neighbor info
- **fdbsyncd**: Syncs FDB (MAC table)
- **natsyncd**: Syncs NAT states

### *mgrd Services (Configuration Deployment)
Names ending in `mgrd`. Two-part logic:
1. **Configuration Deployment**: Read CONFIG_DB changes, push to hardware (via command lines, netlink, or APPL_DB + notifications)
2. **State Reconciliation**: Listen to STATE_DB changes, compare with expected state, re-deploy if inconsistent

### orchagent
The most important service. Integrates states from all *syncd services, computes ASIC configuration, and deploys to ASIC_DB. Then syncd applies SAI API calls to hardware.

### Feature Implementation Services
Named with `d` suffix (daemon): bgpd, lldpd, snmpd, teamd, fancontrol.

### Configuration Deployment Flow
1. User modifies config via CLI/REST API → writes to CONFIG_DB with Redis pub/sub notification
2. *mgrd services listen to CONFIG_DB changes
3. **Direct path**: *mgrd calls Linux commands/netlink → *syncd detects changes → push to STATE_DB → *mgrd reconciles
4. **Indirect path**: *mgrd pushes to APPL_DB → orchagent computes ASIC_DB state → syncd calls SAI API → hardware

### State Synchronization Flow
1. *syncd services detect hardware changes (netlink, SAI notifications)
2. Push changes to STATE_DB or APPL_DB
3. orchagent and *mgrd services listen and process
4. Re-deploy configuration if needed

---

## SAI (Switch Abstraction Interface)

SAI is the cornerstone of SONiC's hardware-software decoupling. It defines C-language header files in the OCP SAI repository, while vendors provide `.so` implementations.

### Key APIs
- `sai_api_initialize()`: Initialize SAI, set service method table
- `sai_api_query()`: Query API function pointers by type (SAI_API_SWITCH, SAI_API_PORT, SAI_API_BRIDGE, etc.)
- All SAI objects follow a pattern: `create`, `remove`, `set_attribute`, `get_attribute`

### VendorSai Wrapper
Syncd wraps SAI in `VendorSai` class:
- Calls `sai_api_initialize()` then `sai_metadata_apis_query()` to populate all API function pointers
- Two calling patterns:
  1. Via `sai_metadata_get_object_type_info()` → virtual table lookup (succinct)
  2. Via `m_apis` member struct → direct API calls (verbose but explicit)

### SAI Initialization
```cpp
// From Mellanox open-source SAI implementation:
sai_status_t sai_api_initialize(flags, services) {
    // Set global service method table, mark initialized
}
sai_status_t sai_api_query(sai_api_id, api_method_table) {
    // Return the appropriate global API struct based on type
}
```

---

## Syncd Deep Dive

### Startup Sequence
1. Constructor creates: ASIC_DB connector, FlexCounterManager, MDIO IPC server, RedisSelectableChannel, NotificationProcessor
2. Initialize SAI via VendorSai
3. Run main event loop with Select-based event dispatching
4. Process events: create-Switch (first event or WarmBoot), then handle subsequent events

### Main Event Loop
Standard SONiC pattern: register Selectable objects, call `select()` to wait, dispatch events.

### Key Files
- `src/sonic-sairedis/syncd/syncd_main.cpp` — entry point
- `src/sonic-sairedis/syncd/Syncd.cpp` — main class, constructor, run loop
- `src/sonic-sairedis/syncd/VendorSai.cpp` — SAI wrapper

---

## BGP Implementation

SONiC uses FRRouting (FRR) for BGP. Data flow:

```
Peer → bgpd → zebra → Linux Kernel → fpmsyncd → APPL_DB → orchagent → ASIC_DB → syncd → ASIC
```

### FRR Architecture
- **bgpd/ripd/ospfd/etc**: Protocol daemons — receive route updates
- **zebra**: Route selection, best-route calculation, kernel synchronization
- **fpmsyncd**: Forwarding Plane Manager syncd — listens to kernel netlink for route changes, writes to APPL_DB

### Route Update Flow (SONiC side)
1. bgpd receives BGP update from peer
2. bgpd sends route to zebra (internal FRR communication)
3. zebra selects best route, installs in Linux kernel
4. fpmsyncd detects kernel route change via netlink
5. fpmsyncd writes route to APPL_DB
6. orchagent reads APPL_DB, computes ASIC state, writes to ASIC_DB
7. syncd reads ASIC_DB, calls SAI API to program ASIC

---

## Communication Patterns

### Redis-based Channels (in sonic-swss-common)
- **SubscriberStateTable**: Subscribe to Redis keyspace notifications for STATE_DB/CONFIG_DB
- **NotificationProducer/Consumer**: Pub/sub for sending/receiving notifications via Redis channels
- **ProducerTable/ConsumerTable**: Push/pop pattern using Redis lists (LPUSH/BLPOP)
- **ProducerStateTable/ConsumerStateTable**: State-oriented producer/consumer pattern

### Orch Layer
`Orch` base class wraps SubscriberStateTable and ConsumerStateTable:
- For CONFIG_DB/STATE_DB: uses SubscriberStateTable (keyspace notification based)
- For other DBs: uses ConsumerStateTable (Redis list pop based)
- Provides `addConsumer()` and `addExecutor()` for service orchestration

### Kernel-based Communication
- **Command Line Invocation**: Direct `exec` of system commands
- **Netlink**: Linux netlink sockets for kernel communication (used by portsyncd, neighsyncd, fpmsyncd, natsyncd)

### ZMQ-based Channels
Alternative communication mechanism (less commonly used, WIP).

---

## Key CLI Commands (on-switch)

```bash
# Container inspection
docker ps                          # List all SONiC containers
docker exec -it swss bash          # Enter swss container
docker exec -it syncd bash         # Enter syncd container
docker exec -it database bash      # Enter database container

# Redis exploration
redis-cli -n 0 keys "*"            # List all keys in APPL_DB
redis-cli -n 4 hgetall "PORT|Ethernet0"  # Read port config
redis-cli -n 6 hgetall "PORT_TABLE|Ethernet0"  # Read port state
redis-cli -n 0 keys "ROUTE_TABLE:*" # List all routes
redis-cli -n 0 hgetall "ROUTE_TABLE:0.0.0.0/0"  # Read default route

# Show tech support
show interfaces status             # Port status
show ip bgp summary                # BGP summary
show ip route                      # Routing table
show vlan brief                    # VLAN summary
show platform psustatus            # Power supply status
show interface transceiver         # SFP/QSFP info

# Config mode
sudo config interface startup Ethernet0   # Admin-up a port
sudo config vlan add 100                  # Create VLAN 100
```

---

## Boot Process

### Cold Boot
Full initialization: load kernel, start containers, read config files, deploy config to hardware.

### Fast Boot
Skip some initialization steps to reduce boot time (WIP).

### Warm Boot
Preserve ASIC state across restarts. Redis persistence is used (`persistence_for_warm_boot: yes` in database_config.json). Syncd replays ASIC_DB state, and orchagent reconciles differences.

---

## MCP Server — SONiC Diagnostic Tools for AI Agents

This project includes an MCP (Model Context Protocol) server at `sonic_mcp_server.py` that exposes SONiC diagnostic tools for AI agents. When a user asks about SONiC Redis databases, ports, or consistency issues, **use the MCP tools** to query the live switch rather than static documentation.

### Starting the MCP Server

The server must be started before tools can be called. Start it in a separate terminal:

```bash
# From the project root:
cd /Users/burman/projects/SONiC-python-LLM-consistency-checker

# Start the server (streamable-http on port 8100 by default):
.venv/bin/python sonic_mcp_server.py

# Or with a custom host/port:
.venv/bin/python sonic_mcp_server.py --host 127.0.0.1 --port 8100

# Or via stdio (for child-process MCP clients):
.venv/bin/python sonic_mcp_server.py --transport stdio
```

**Prerequisites:** The server needs a `.env` file with valid connection settings (copy from `.env.example`):
```bash
SONIC_CONNECTION_MODE=docker_exec
SONIC_CONTAINER_NAME=clab-sonic-ai-lab-sonic1
```

### Available MCP Tools

All tools accept optional `connection_mode`, `container_name`, and `orb_vm_name` overrides that fall back to `.env` values.

| Tool | Description | Example |
|------|-------------|---------|
| `sonic_db_config` | Load the dynamic Redis DB config from `database_config.json`. Shows DB IDs, separators, and instance names. | `sonic_db_config()` |
| `sonic_list_dbs` | List all SONiC Redis DBs with key counts. | `sonic_list_dbs()` |
| `sonic_scan_keys` | Scan keys in a DB using SCAN (never blocks). Use patterns like `PORT*`, `ROUTE*`, `VLAN*`, or `*`. | `sonic_scan_keys(db_name="CONFIG_DB", pattern="PORT*")` |
| `sonic_hget` | Read all hash fields from a key (HGETALL). Use after scanning to inspect contents. | `sonic_hget(db_name="CONFIG_DB", key="PORT|Ethernet0")` |
| `sonic_key_type` | Show the Redis type of a key (hash, string, set, zset, list, or none). | `sonic_key_type(db_name="APPL_DB", key="PORT_TABLE:Ethernet0")` |
| `sonic_list_ports` | List all discovered SONiC port names from CONFIG_DB. | `sonic_list_ports()` |
| `sonic_get_port_view` | **The primary diagnostic tool.** Get a full cross-DB view of a port from CONFIG_DB, APPL_DB, STATE_DB, COUNTERS_DB, and ASIC_DB, plus transceiver info and consistency findings. | `sonic_get_port_view(port_name="Ethernet0")` |
| `sonic_check_port` | Run consistency checks on a single port: admin-up/oper-down mismatch, MTU mismatch, speed mismatch, missing counters, missing transceiver. | `sonic_check_port(port_name="Ethernet0")` |
| `sonic_check_all_ports` | Run consistency checks on ALL ports. Use for switch-wide health checks. | `sonic_check_all_ports()` |

### When to Use Each Tool

- **Exploring what DBs exist** → `sonic_list_dbs()` or `sonic_db_config()`
- **Discovering keys in a DB** → `sonic_scan_keys(db_name="CONFIG_DB", pattern="*")`
- **Inspecting a key's contents** → `sonic_hget(db_name="CONFIG_DB", key="PORT|Ethernet0")`
- **Checking if a key exists** → `sonic_key_type(db_name="STATE_DB", key="PORT_TABLE|Ethernet0")`
- **Listing all ports** → `sonic_list_ports()`
- **Full port diagnostic** → `sonic_get_port_view(port_name="Ethernet0")`
- **Port health check** → `sonic_check_port(port_name="Ethernet0")`
- **Switch-wide health check** → `sonic_check_all_ports()`

### Typical Diagnostic Workflow

```
1. sonic_list_dbs()                          # See what DBs exist and their sizes
2. sonic_db_config()                         # Confirm DB IDs and separators
3. sonic_list_ports()                        # Discover all port names
4. sonic_get_port_view("Ethernet0")           # Deep inspection of one port
5. sonic_check_all_ports()                   # Find all inconsistencies
6. sonic_scan_keys("CONFIG_DB", "VLAN*")      # Explore specific keys
7. sonic_hget("CONFIG_DB", "VLAN|Vlan100")    # Read specific key contents
```

### Connection Modes

The MCP server supports two connection modes configured via `SONIC_CONNECTION_MODE` in `.env`:

- **docker_exec** (default): Connects via `docker exec` into a container running on local Docker. Set `SONIC_CONTAINER_NAME` to the container name.
- **orb_vm_exec**: Connects via `orb exec` into an OrbStack VM. Set `SONIC_ORB_VM_NAME` to the VM name.

---

## Key Repositories

| Repository | Purpose |
|-----------|---------|
| [sonic-buildimage](https://github.com/sonic-net/sonic-buildimage) | Main build repository |
| [sonic-swss](https://github.com/sonic-net/sonic-swss) | SWSS container services (orchagent, *mgrd, *syncd) |
| [sonic-swss-common](https://github.com/sonic-net/sonic-swss-common) | Shared library for Redis communication wrappers |
| [sonic-sairedis](https://github.com/sonic-net/sonic-sairedis) | Syncd and SAI Redis integration |
| [sonic-frr](https://github.com/sonic-net/sonic-frr) | FRRouting fork for SONiC |
| [sonic-utilities](https://github.com/sonic-net/sonic-utilities) | CLI utilities (show, config, etc.) |
| [SAI](https://github.com/opencomputeproject/SAI) | OCP SAI specification (header files) |
| [sonic-book](https://github.com/r12f/sonic-book) | This knowledge base's source |

---

## References

- [SONiC Architecture](https://github.com/sonic-net/SONiC/wiki/Architecture)
- [SONiC Roadmap](https://github.com/sonic-net/SONiC/wiki/Sonic-Roadmap-Planning)
- [SONiC User Manual](https://github.com/sonic-net/SONiC/blob/master/doc/SONiC-User-Manual.md)
- [SAI API](https://github.com/opencomputeproject/SAI)
- [SONiC Subsystem Interactions](https://github.com/sonic-net/SONiC/wiki/Subsystem-Interactions)
- [FRRouting](https://frrouting.org/)
- [Mellanox SAI Implementation](https://github.com/Mellanox/SAI-Implementation)
