#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
AutoBot Dynamic Inventory Generator
Generates Ansible inventory from Redis service registry database

Usage:
    python generate_inventory.py --list
    python generate_inventory.py --host <hostname>

Environment variables:
    REDIS_HOST: Redis server address (default: localhost)
    REDIS_PORT: Redis server port (default: 6379)
    AUTOBOT_REDIS_DB_MAIN: Redis database number (default: main in redis-databases.yaml)
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

try:
    import redis
except ImportError:
    sys.stderr.write("ERROR: redis-py not installed. Install: pip install redis\n")
    sys.exit(1)


#: The one name -> number table (#19232), read with plain PyYAML: this script runs under
#: Ansible's interpreter without autobot_shared (#1086), so it cannot use database_number().
#: The tree beside this one is code_source's checkout or the install; the install's copy is never
#: updated (#20578), so code_source's wins when present. Pinned equal to infrastructure_dir() by a test.
_ROOT = Path(__file__).resolve().parents[4]
_INFRA = next(
    (c for c in (_ROOT / "code_source" / "autobot-infrastructure", _ROOT / "autobot-infrastructure") if c.is_dir()),
    _ROOT / "code_source" / "autobot-infrastructure",
)
_DATABASES_YAML = _INFRA / "shared" / "config" / "redis-databases.yaml"
#: The override contract, mirrored from database_overrides.py (pinned equal to the Python and
#: shell readers by redis_single_source_19232_test.py): AUTOBOT_REDIS_DB_<NAME>, trimmed ASCII
#: digits within 0..15, refused (YAML number kept) when invalid or when two databases collide.
_MAX_DATABASE_INDEX = 15
_LEGACY_ENV_NAMES = {"AUTOBOT_REDIS_DB_TASKS": "workflows"}


class DatabasesUnreadable(Exception):
    """redis-databases.yaml is missing or malformed, so no Redis database number is known."""


def _declared_databases() -> Dict[str, int]:
    """Every database redis-databases.yaml declares; :class:`DatabasesUnreadable` when it cannot be read.

    Fail-closed for Redis: no YAML, no Redis query -- never a guessed number. The caller
    (:meth:`AutoBotInventory.connect_redis`) turns that into the static fallback inventory.
    """
    try:
        with open(_DATABASES_YAML, encoding="utf-8") as f:
            declared = yaml.safe_load(f)["redis_databases"]
        return {name: int(cfg["db"]) for name, cfg in declared.items() if "db" in cfg}
    except (OSError, KeyError, TypeError, ValueError, AttributeError, yaml.YAMLError) as exc:
        raise DatabasesUnreadable(f"cannot read Redis databases from {_DATABASES_YAML}: {exc}") from exc


def _override_number(raw: str) -> Optional[int]:
    """database_overrides._parse: trimmed ASCII digits within 0.._MAX_DATABASE_INDEX, else None."""
    text = raw.strip()
    if not text.isascii() or not text.isdigit() or int(text) > _MAX_DATABASE_INDEX:
        return None
    return int(text)


def _accepted_overrides(declared: Dict[str, int]) -> Dict[str, int]:
    """The valid AUTOBOT_REDIS_DB_* overrides (legacy TASKS included); a refusal goes to stderr."""
    accepted: Dict[str, int] = {}
    names = {f"AUTOBOT_REDIS_DB_{n.upper()}": n for n in declared}
    # A blank value (VAR=) is no request, as in database_overrides._requested.
    requested = {name: os.environ[var] for var, name in names.items() if os.environ.get(var, "").strip()}
    for legacy, name in _LEGACY_ENV_NAMES.items():
        if os.environ.get(legacy, "").strip() and name in declared and name not in requested:
            requested[name] = os.environ[legacy]
    for name, raw in requested.items():
        number = _override_number(raw)
        if number is None:
            sys.stderr.write(f"WARNING: refused Redis DB override for {name}={raw!r} (keeping the YAML)\n")
        else:
            accepted[name] = number
    return accepted


def resolved_databases() -> Dict[str, int]:
    """The YAML with every acceptable override applied; colliding overrides are refused."""
    declared = _declared_databases()
    accepted = _accepted_overrides(declared)
    while True:
        merged = {**declared, **accepted}
        clashing = {n for n in accepted if any(o != n and merged[o] == merged[n] for o in merged)}
        if not clashing:
            return merged
        for name in clashing:
            sys.stderr.write(f"WARNING: refused Redis DB override for {name}: collides (keeping the YAML)\n")
            del accepted[name]


class AutoBotInventory:
    """Generate Ansible inventory from AutoBot service registry"""

    def __init__(self):
        self.redis_host = os.getenv("REDIS_HOST", os.getenv("AUTOBOT_REDIS_HOST", "localhost"))
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_db: Optional[int] = None  # resolved by connect_redis, from the YAML
        self.inventory = {"_meta": {"hostvars": {}}}

    def connect_redis(self):
        """Connect to Redis server, or None -- the static fallback inventory then answers.

        The database is resolved here, not in ``__init__`` (#19232): without
        redis-databases.yaml the Redis path is skipped (fail-closed, no guessed number)
        and the static fallback still runs.

        Issue #1086: Direct redis.Redis() required — Ansible dynamic inventory
        script runs standalone without access to autobot_shared.
        """
        try:
            self.redis_db = resolved_databases()["main"]
        except DatabasesUnreadable as exc:
            sys.stderr.write(f"ERROR: {exc}; skipping Redis, using the static fallback inventory\n")
            return None
        try:
            client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            client.ping()
            return client
        except Exception as e:
            sys.stderr.write(f"ERROR: Cannot connect to Redis at {self.redis_host}:{self.redis_port}\n")
            sys.stderr.write(f"       {str(e)}\n")
            return None

    def get_hosts_from_redis(self, redis_client) -> Dict[str, Any]:
        """Fetch host information from Redis service registry"""
        hosts = {}

        try:
            # Issue #614: Fix N+1 pattern - collect all keys first, then batch fetch
            # Scan for all host keys in Redis
            host_keys = list(redis_client.scan_iter(match="autobot:host:*"))

            if not host_keys:
                return hosts

            # Use pipeline to batch all hgetall operations
            pipe = redis_client.pipeline()
            for key in host_keys:
                pipe.hgetall(key)

            # Execute all commands in single round-trip
            results = pipe.execute()

            # Process results
            for key, host_data in zip(host_keys, results):
                if host_data:
                    hostname = key.split(":")[-1]
                    hosts[hostname] = {
                        "ansible_host": host_data.get("ip", "127.0.0.1"),
                        "vm_role": host_data.get("role", "unknown"),
                        "vm_hostname": hostname,
                        "services": (host_data.get("services", "").split(",") if host_data.get("services") else []),
                        "status": host_data.get("status", "unknown"),
                        "last_seen": host_data.get("last_seen", "never"),
                    }
        except Exception as e:
            sys.stderr.write(f"WARNING: Error fetching hosts from Redis: {e}\n")

        return hosts

    def build_inventory_from_redis(self, redis_client):
        """Build inventory structure from Redis data"""
        hosts = self.get_hosts_from_redis(redis_client)

        if not hosts:
            sys.stderr.write("WARNING: No hosts found in Redis, using fallback static inventory\n")
            return self.build_fallback_inventory()

        # Group hosts by role
        groups = {}
        for hostname, host_data in hosts.items():
            role = host_data.get("vm_role", "unknown")

            if role not in groups:
                groups[role] = {"hosts": [], "vars": {}}

            groups[role]["hosts"].append(hostname)
            self.inventory["_meta"]["hostvars"][hostname] = host_data

        # Add groups to inventory
        for group_name, group_data in groups.items():
            self.inventory[group_name] = group_data

        return self.inventory

    def build_fallback_inventory(self) -> Dict[str, Any]:
        """Fallback to static inventory structure if Redis is unavailable"""
        return {
            "_meta": {"hostvars": {}},
            "frontend": {"hosts": ["autobot-frontend"], "vars": {}},
            "database": {"hosts": ["autobot-database"], "vars": {}},
            "npu": {"hosts": ["autobot-npu"], "vars": {}},
            "aiml": {"hosts": ["autobot-aiml"], "vars": {}},
            "browser": {"hosts": ["autobot-browser"], "vars": {}},
            "backend": {"hosts": ["autobot-host"], "vars": {}},
        }

    def list_inventory(self) -> str:
        """Generate full inventory list"""
        redis_client = self.connect_redis()

        if redis_client:
            self.build_inventory_from_redis(redis_client)
        else:
            self.inventory = self.build_fallback_inventory()

        return json.dumps(self.inventory, indent=2)

    def host_vars(self, hostname: str) -> str:
        """Get variables for a specific host"""
        redis_client = self.connect_redis()

        if redis_client:
            self.build_inventory_from_redis(redis_client)
        else:
            self.inventory = self.build_fallback_inventory()

        hostvars = self.inventory["_meta"]["hostvars"].get(hostname, {})
        return json.dumps(hostvars, indent=2)


def main():
    """Main entry point for dynamic inventory script"""
    parser = argparse.ArgumentParser(description="AutoBot Dynamic Inventory Generator")
    parser.add_argument("--list", action="store_true", help="List all hosts")
    parser.add_argument("--host", help="Get variables for specific host")

    args = parser.parse_args()

    inventory = AutoBotInventory()

    if args.list:
        print(inventory.list_inventory())  # noqa: print
    elif args.host:
        print(inventory.host_vars(args.host))  # noqa: print
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
