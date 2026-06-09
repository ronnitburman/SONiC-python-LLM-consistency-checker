"""SonicRedisClient — Redis operations using dynamic DB config from Step 1.

Supports docker_exec (redis-cli inside SONiC container) and local_redis (redis-py direct).
All Redis operations resolve DB IDs dynamically via get_db_id().
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

import redis

from sonic_consistency_checker.core.db_config_loader import (
    SonicDbConfig,
    SonicDbConfigLoader,
)


class SonicRedisError(RuntimeError):
    """Raised when a Redis operation fails."""


class SonicRedisClient:
    """Redis client that uses dynamic SONiC DB config for ID resolution.

    Connection modes:
      - docker_exec: runs redis-cli inside the SONiC container via docker exec
      - local_redis: connects directly using redis-py
    """

    def __init__(
        self,
        connection_mode: str | None = None,
        container_name: str | None = None,
        orb_vm_name: str | None = None,
        redis_host: str | None = None,
        redis_port: int | None = None,
        db_config: SonicDbConfig | None = None,
    ) -> None:
        from dotenv import load_dotenv

        load_dotenv()

        self.connection_mode = connection_mode or os.getenv(
            "SONIC_CONNECTION_MODE", "docker_exec"
        )
        self.container_name = container_name or os.getenv(
            "SONIC_CONTAINER_NAME", "clab-sonic-ai-lab-sonic1"
        )
        self.orb_vm_name = orb_vm_name or os.getenv("SONIC_ORB_VM_NAME", "")
        self.redis_host = redis_host or os.getenv(
            "SONIC_REDIS_HOST", "localhost"
        )
        raw_port = os.getenv("SONIC_REDIS_PORT", "6379")
        self.redis_port = redis_port if redis_port is not None else int(raw_port)

        # Load dynamic DB config if not provided
        if db_config is not None:
            self.db_config = db_config
        else:
            self.db_config = SonicDbConfigLoader(
                connection_mode=self.connection_mode,
                container_name=self.container_name,
                orb_vm_name=self.orb_vm_name,
            ).load()

        self.databases = self.db_config.databases

    # ------------------------------------------------------------------
    # DB ID resolution
    # ------------------------------------------------------------------

    def get_db_id(self, db_name: str) -> int:
        """Resolve a SONiC DB name to its numeric Redis DB ID."""
        normalized = db_name.upper()
        if normalized not in self.databases:
            available = ", ".join(sorted(self.databases.keys()))
            raise ValueError(
                f"Unknown DB name: {db_name}. Available DBs: {available}"
            )
        return self.databases[normalized].id

    # ------------------------------------------------------------------
    # Public Redis operations
    # ------------------------------------------------------------------

    def dbsize(self, db_name: str) -> int:
        """Return the number of keys in the given DB."""
        db_id = self.get_db_id(db_name)

        if self.connection_mode in ("docker_exec", "orb_vm_exec"):
            output = self._run_redis_cli(db_id, ["dbsize"])
            try:
                return int(output.strip())
            except ValueError:
                return -1

        r = self._redis(db_id)
        try:
            return r.dbsize()
        except redis.RedisError:
            return -1

    def scan_keys(self, db_name: str, pattern: str = "*") -> list[str]:
        """Scan keys matching *pattern* using SCAN (never KEYS)."""
        db_id = self.get_db_id(db_name)

        if self.connection_mode in ("docker_exec", "orb_vm_exec"):
            return self._scan_keys_cli(db_id, pattern)

        r = self._redis(db_id)
        keys: list[str] = []
        for key in r.scan_iter(match=pattern, count=100):
            keys.append(key)
        return keys

    def hgetall(self, db_name: str, key: str) -> dict[str, str]:
        """Get all fields from a Redis hash."""
        db_id = self.get_db_id(db_name)

        if self.connection_mode in ("docker_exec", "orb_vm_exec"):
            output = self._run_redis_cli(db_id, ["hgetall", key])
            return self._parse_hgetall_output(output)

        r = self._redis(db_id)
        try:
            raw = r.hgetall(key)
            return {k: v for k, v in raw.items()}
        except redis.RedisError:
            return {}

    def key_type(self, db_name: str, key: str) -> str:
        """Get the Redis type of a key (hash, string, set, zset, list, none)."""
        db_id = self.get_db_id(db_name)

        if self.connection_mode in ("docker_exec", "orb_vm_exec"):
            output = self._run_redis_cli(db_id, ["type", key])
            return output.strip()

        r = self._redis(db_id)
        try:
            return r.type(key)
        except redis.RedisError:
            return "none"

    # ------------------------------------------------------------------
    # Equivalent redis-cli command helpers
    # ------------------------------------------------------------------

    def equivalent_scan_command(self, db_name: str, pattern: str) -> str:
        """Build a human-readable equivalent redis-cli command."""
        db_id = self.get_db_id(db_name)
        return f'redis-cli -n {db_id} scan 0 match "{pattern}" count 100'

    def equivalent_hgetall_command(self, db_name: str, key: str) -> str:
        """Build a human-readable equivalent redis-cli command."""
        db_id = self.get_db_id(db_name)
        return f'redis-cli -n {db_id} hgetall "{key}"'

    def equivalent_type_command(self, db_name: str, key: str) -> str:
        """Build a human-readable equivalent redis-cli command."""
        db_id = self.get_db_id(db_name)
        return f'redis-cli -n {db_id} type "{key}"'

    # ------------------------------------------------------------------
    # Remote Python execution (for SWSS SDK inside the container)
    # ------------------------------------------------------------------

    def run_python_remote(self, code: str) -> str:
        """Execute Python *code* inside the SONiC container and return stdout.

        Used by the SWSS SDK layer (Step 5) to run ``ConfigDBConnector``,
        ``SonicV2Connector``, etc. inside the container where those
        libraries actually exist.  Follows the same ``orb exec → docker
        exec`` tunnel pattern as ``_run_redis_cli()``.

        The *code* must ``print()`` a single JSON line to stdout.
        Runtime errors inside the container are caught, serialised as
        ``{"__error__": true, "message": "..."}``, and raised as
        ``SonicRedisError`` on this side.
        """
        # Wrap user code so exceptions inside the container become
        # structured JSON instead of a traceback the caller can't parse.
        wrapped = (
            "import json, sys, traceback\n"
            "try:\n"
            + "\n".join(f"    {line}" for line in code.strip().split("\n"))
            + "\n"
            "except Exception as _sonic_exc:\n"
            "    print(json.dumps({'__error__': True, "
            "'message': str(_sonic_exc), "
            "'traceback': traceback.format_exc()}))\n"
            "    sys.exit(1)\n"
        )

        if self.connection_mode == "orb_vm_exec":
            vm = self.orb_vm_name or self._detect_orb_vm()
            if not vm:
                raise SonicRedisError(
                    "orb_vm_exec mode but no Orb VM detected"
                )
            command = [
                "orb", "exec", "-m", vm,
                "docker", "exec", self.container_name,
                "python3", "-c", wrapped,
            ]
        else:
            command = [
                "docker", "exec", self.container_name,
                "python3", "-c", wrapped,
            ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            # Try to extract the structured error from stdout.
            try:
                err_data = json.loads(result.stdout.strip())
                if err_data.get("__error__"):
                    raise SonicRedisError(err_data.get("message", "unknown"))
            except (json.JSONDecodeError, KeyError):
                pass
            raise SonicRedisError(
                result.stderr.strip() or "python3 remote execution failed"
            )

        return result.stdout

    # ------------------------------------------------------------------
    # Private helpers — local_redis mode
    # ------------------------------------------------------------------

    def _redis(self, db_id: int) -> redis.Redis:
        """Return a redis-py connection for the given DB ID."""
        return redis.Redis(
            host=self.redis_host,
            port=self.redis_port,
            db=db_id,
            decode_responses=True,
        )

    # ------------------------------------------------------------------
    # Private helpers — docker_exec / orb_vm_exec mode
    # ------------------------------------------------------------------

    def _run_redis_cli(self, db_id: int, args: list[str]) -> str:
        """Run a redis-cli command inside the SONiC container.

        In docker_exec mode uses plain `docker exec`.
        In orb_vm_exec mode tunnels through `orb exec -m <vm> docker exec`.
        """
        redis_args = [
            "redis-cli",
            "-n",
            str(db_id),
            *args,
        ]

        if self.connection_mode == "orb_vm_exec":
            vm = self.orb_vm_name or self._detect_orb_vm()
            if not vm:
                raise SonicRedisError(
                    "orb_vm_exec mode but no Orb VM name configured and no running VMs detected"
                )
            command = [
                "orb", "exec", "-m", vm,
                "docker", "exec", self.container_name,
                *redis_args,
            ]
        else:
            command = [
                "docker", "exec", self.container_name,
                *redis_args,
            ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise SonicRedisError(
                result.stderr.strip() or "redis-cli command failed"
            )

        return result.stdout

    @staticmethod
    def _detect_orb_vm() -> str:
        """Auto-detect the first running OrbStack VM name."""
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

    def _scan_keys_cli(self, db_id: int, pattern: str) -> list[str]:
        """Scan keys via redis-cli with cursor iteration."""
        keys: list[str] = []
        cursor = "0"

        while True:
            stdout = self._run_redis_cli(
                db_id, ["scan", cursor, "match", pattern, "count", "100"]
            )
            lines = stdout.strip().split("\n")

            if not lines:
                break

            # First line is the next cursor
            cursor = lines[0].strip()

            # Subsequent lines are keys
            for line in lines[1:]:
                stripped = line.strip()
                if stripped:
                    keys.append(stripped)

            if cursor == "0":
                break

        return keys

    @staticmethod
    def _parse_hgetall_output(output: str) -> dict[str, str]:
        """Parse redis-cli hgetall output (alternating field/value lines).

        Empty values are preserved (they appear as blank lines in redis-cli output).
        Empty/non-existent hashes return an empty dict silently.
        """
        lines = output.strip().split("\n")

        # redis-cli returns a single empty line for empty/non-existent hashes
        if len(lines) == 1 and lines[0] == "":
            return {}

        result: dict[str, str] = {}
        for i in range(0, len(lines) - 1, 2):
            result[lines[i]] = lines[i + 1]

        # If odd number of lines, log a warning but don't crash
        if len(lines) % 2 != 0:
            import logging
            logging.getLogger(__name__).warning(
                "hgetall returned odd number of lines (%d) — last field ignored",
                len(lines),
            )

        return result
