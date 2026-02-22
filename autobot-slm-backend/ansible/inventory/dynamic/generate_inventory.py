#!/usr/bin/env python3
"""
AutoBot Dynamic Inventory Generator
Generates Ansible inventory from Redis service registry database

Usage:
    python generate_inventory.py --list
    python generate_inventory.py --host <hostname>

Environment variables:
    REDIS_HOST: Redis server address (default: localhost)
    REDIS_PORT: Redis server port (default: 6379)
    REDIS_DB: Redis database number (default: 0)
"""

import argparse
import json
import os
import sys
from typing import Any, Dict

try:
    import redis
except ImportError:
    sys.stderr.write("ERROR: redis-py not installed. Install: pip install redis\n")
    sys.exit(1)


class AutoBotInventory:
    """Generate Ansible inventory from AutoBot service registry"""

    def __init__(self):
        self.redis_host = os.getenv(
            "REDIS_HOST", os.getenv("AUTOBOT_REDIS_HOST", "localhost")
        )
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_db = int(os.getenv("REDIS_DB", "0"))
        self.inventory = {"_meta": {"hostvars": {}}}

    def connect_redis(self):
        """Connect to Redis server.

        Issue #1086: Direct redis.Redis() required — Ansible dynamic inventory
        script runs standalone without access to autobot_shared.
        """
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
            sys.stderr.write(
                f"ERROR: Cannot connect to Redis at {self.redis_host}:{self.redis_port}\n"
            )
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
                        "services": (
                            host_data.get("services", "").split(",")
                            if host_data.get("services")
                            else []
                        ),
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
            sys.stderr.write(
                "WARNING: No hosts found in Redis, using fallback static inventory\n"
            )
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
