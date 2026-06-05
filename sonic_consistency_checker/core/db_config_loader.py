"""Dynamic SONiC Redis database configuration loader.

Reads database_config.json from a running SONiC container or local filesystem
and builds a nested databases dict mirroring the source JSON.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any

from sonic_consistency_checker.core.db_constants import (
    DEFAULT_DATABASE_CONFIG_PATHS,
    FALLBACK_DATABASES,
)


@dataclass
class DbEntry:
    """A single SONiC Redis database entry."""

    id: int
    separator: str
    instance: str


@dataclass
class SonicDbConfig:
    """Result of loading SONiC database configuration."""

    databases: dict[str, DbEntry]
    raw_config: dict[str, Any]
    source: str
    used_fallback: bool
    errors: list[str] = field(default_factory=list)


class SonicDbConfigLoader:
    """Loads SONiC Redis database configuration dynamically.

    Supports:
      - docker_exec: read database_config.json via local Docker
      - orb_vm_exec: read via OrbStack VM (orb exec -m <vm> docker exec ...)
      - local_filesystem: read from the local filesystem

    Falls back to FALLBACK_DATABASES only when all dynamic reads fail.
    """

    def __init__(
        self,
        connection_mode: str | None = None,
        container_name: str | None = None,
        orb_vm_name: str | None = None,
        config_paths: list[str] | None = None,
    ) -> None:
        from dotenv import load_dotenv
        load_dotenv()

        self.connection_mode = connection_mode or os.getenv(
            "SONIC_CONNECTION_MODE", "docker_exec"
        )
        self.container_name = container_name or os.getenv(
            "SONIC_CONTAINER_NAME", "clab-sonic-ai-lab-sonic1"
        )
        self.orb_vm_name = orb_vm_name or os.getenv(
            "SONIC_ORB_VM_NAME", ""
        )
        self.config_paths = config_paths or list(DEFAULT_DATABASE_CONFIG_PATHS)

    def load(self) -> SonicDbConfig:
        """Load DB config following the priority chain."""
        errors: list[str] = []

        # Priority 1: orb_vm_exec (tunnel Docker through Orb VM)
        if self.connection_mode == "orb_vm_exec":
            for path in self.config_paths:
                try:
                    raw = self._read_from_orb_vm_container(path)
                    vm = self.orb_vm_name or self._detect_orb_vm()
                    source = f"orb_vm_exec:{vm}:{self.container_name}:{path}"
                    return self._parse_config(raw, source, False, errors)
                except (FileNotFoundError, RuntimeError) as e:
                    errors.append(f"{path}: {e}")

        # Priority 2: docker_exec
        if self.connection_mode == "docker_exec":
            for path in self.config_paths:
                try:
                    raw = self._read_from_container(path)
                    source = f"docker_exec:{self.container_name}:{path}"
                    return self._parse_config(raw, source, False, errors)
                except (FileNotFoundError, RuntimeError) as e:
                    errors.append(f"{path}: {e}")

        # Priority 3: local filesystem
        for path in self.config_paths:
            try:
                raw = self._read_from_local_file(path)
                source = f"local_filesystem:{path}"
                return self._parse_config(raw, source, False, errors)
            except (FileNotFoundError, RuntimeError) as e:
                errors.append(f"{path}: {e}")

        # Priority 4: fallback
        return self._build_fallback(errors)

    def _detect_orb_vm(self) -> str:
        """Auto-detect the first running Orb VM name."""
        try:
            result = subprocess.run(
                ["orb", "list", "--running", "--quiet"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split("\n")[0]
        except FileNotFoundError:
            pass
        return ""

    def _read_from_orb_vm_container(self, path: str) -> dict[str, Any]:
        """Run `orb exec -m <vm> docker exec <container> cat <path>` and parse JSON."""
        vm_name = self.orb_vm_name or self._detect_orb_vm()
        if not vm_name:
            raise RuntimeError(
                "no Orb VM name configured and no running VMs detected"
            )

        result = subprocess.run(
            ["orb", "exec", "-m", vm_name, "docker", "exec",
             self.container_name, "cat", path],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(
                f"orb exec failed (returncode={result.returncode}): {stderr}"
            )

        content = result.stdout.strip()
        if not content:
            raise RuntimeError("empty response from orb vm container")

        return self._validate_and_parse_json(content, path)

    def _read_from_container(self, path: str) -> dict[str, Any]:
        """Run `docker exec <container> cat <path>` and return the parsed JSON."""
        result = subprocess.run(
            ["docker", "exec", self.container_name, "cat", path],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(
                f"docker exec failed (returncode={result.returncode}): {stderr}"
            )

        content = result.stdout.strip()
        if not content:
            raise RuntimeError("empty response from container")

        return self._validate_and_parse_json(content, path)

    def _read_from_local_file(self, path: str) -> dict[str, Any]:
        """Read database_config.json from the local filesystem."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"file not found: {path}")

        with open(path, "r") as f:
            content = f.read()

        if not content.strip():
            raise RuntimeError(f"empty file: {path}")

        return self._validate_and_parse_json(content, path)

    def _validate_and_parse_json(self, content: str, path: str) -> dict[str, Any]:
        """Parse JSON and validate it contains at least one valid DB entry."""
        try:
            raw_config = json.loads(content)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"invalid JSON in {path}: {e}")

        # Validate that DATABASES key exists and has valid entries
        databases: dict[str, Any] = raw_config.get("DATABASES", {})
        if not isinstance(databases, dict) or not databases:
            raise RuntimeError(f"no DATABASES found or empty in {path}")

        # Check at least one entry has a valid 'id'
        has_valid_id = False
        for db_name, db_info in databases.items():
            if isinstance(db_info, dict) and "id" in db_info:
                try:
                    int(db_info["id"])
                    has_valid_id = True
                    break
                except (ValueError, TypeError):
                    pass

        if not has_valid_id:
            raise RuntimeError(f"no valid DB entries with 'id' found in {path}")

        return raw_config

    def _parse_config(
        self,
        raw_config: dict[str, Any],
        source: str,
        used_fallback: bool,
        errors: list[str],
    ) -> SonicDbConfig:
        """Parse raw config dict into SonicDbConfig."""
        databases: dict[str, DbEntry] = {}

        for db_name, db_info in raw_config.get("DATABASES", {}).items():
            try:
                db_id = int(db_info.get("id"))
            except (ValueError, TypeError):
                errors.append(f"invalid id for DB '{db_name}', skipping")
                continue

            db_sep = db_info.get("separator", ":")
            db_inst = db_info.get("instance", "redis")

            # Warn about missing separator/instance defaults
            if "separator" not in db_info:
                errors.append(
                    f"warning: DB '{db_name}' missing 'separator', defaulting to ':'"
                )
            if "instance" not in db_info:
                errors.append(
                    f"warning: DB '{db_name}' missing 'instance', defaulting to 'redis'"
                )

            databases[db_name] = DbEntry(
                id=db_id,
                separator=str(db_sep),
                instance=str(db_inst),
            )

        return SonicDbConfig(
            databases=databases,
            raw_config=raw_config,
            source=source,
            used_fallback=used_fallback,
            errors=errors,
        )

    def _build_fallback(self, errors: list[str]) -> SonicDbConfig:
        """Build a fallback config from FALLBACK_DATABASES."""
        databases: dict[str, DbEntry] = {
            name: DbEntry(
                id=int(entry["id"]),
                separator=str(entry["separator"]),
                instance=str(entry["instance"]),
            )
            for name, entry in FALLBACK_DATABASES.items()
        }

        return SonicDbConfig(
            databases=databases,
            raw_config={"DATABASES": dict(FALLBACK_DATABASES)},
            source="fallback_defaults",
            used_fallback=True,
            errors=errors,
        )
