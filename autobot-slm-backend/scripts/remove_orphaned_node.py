#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Remove orphaned/unreachable nodes from SLM database.

Usage:
    python remove_orphaned_node.py --ip <node-ip>
    python remove_orphaned_node.py --node-id <node_id>
    python remove_orphaned_node.py --list-unreachable

This script removes nodes that appear in inventory but are not enrolled/reachable,
causing warnings during provision runs. See GitHub issue #9285.

Environment variables:
    SLM_API_URL: SLM API base URL (default: http://localhost:8002)
    SLM_API_TOKEN: Authentication token for SLM API
"""

import argparse
import asyncio
import os
import sys
from typing import Optional

try:
    import aiohttp
except ImportError:
    print("ERROR: aiohttp not installed. Install: pip install aiohttp", file=sys.stderr)
    sys.exit(1)

try:
    from autobot_shared.ssot_config import config as _ssot_config

    _DEFAULT_SLM_URL = _ssot_config.slm_url
except Exception:
    _DEFAULT_SLM_URL = os.getenv("SLM_API_URL", "http://localhost:8000")  # canonical: ignore py-hardcoded-url


class SLMClient:
    """Simple SLM API client for node management."""

    def __init__(self, api_url: str, api_token: Optional[str] = None):
        self.api_url = api_url.rstrip("/")
        self.headers = {}
        if api_token:
            self.headers["Authorization"] = f"Bearer {api_token}"

    async def list_nodes(self) -> list[dict]:
        """Fetch all nodes from SLM API."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.api_url}/api/nodes",
                headers=self.headers,
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Failed to list nodes: HTTP {resp.status}")
                data = await resp.json()
                return data.get("nodes", [])

    async def delete_node(self, node_id: str) -> None:
        """Delete a node by ID."""
        async with aiohttp.ClientSession() as session:
            async with session.delete(
                f"{self.api_url}/api/nodes/{node_id}",
                headers=self.headers,
            ) as resp:
                if resp.status not in (204, 200):
                    error_text = await resp.text()
                    raise RuntimeError(f"Failed to delete node {node_id}: HTTP {resp.status}\n{error_text}")

    async def test_node_reachability(self, node_id: str) -> dict:
        """Test SSH reachability of a node."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.api_url}/api/nodes/{node_id}/test-connection",
                headers=self.headers,
                json={},
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"success": False, "error": f"HTTP {resp.status}"}


async def find_node_by_ip(client: SLMClient, ip: str) -> Optional[dict]:
    """Find a node by IP address."""
    nodes = await client.list_nodes()
    for node in nodes:
        if node.get("ip_address") == ip:
            return node
    return None


async def list_unreachable_nodes(client: SLMClient) -> list[dict]:
    """List all nodes and test their reachability."""
    nodes = await client.list_nodes()
    unreachable = []

    print(f"Testing reachability of {len(nodes)} nodes...")
    for node in nodes:
        node_id = node.get("node_id")
        ip = node.get("ip_address")
        hostname = node.get("hostname")

        try:
            result = await client.test_node_reachability(node_id)
            if not result.get("success"):
                unreachable.append(node)
                print(f"  ✗ {hostname} ({ip}) - UNREACHABLE")
            else:
                print(f"  ✓ {hostname} ({ip}) - OK")
        except Exception as e:
            unreachable.append(node)
            print(f"  ✗ {hostname} ({ip}) - ERROR: {e}")

    return unreachable


async def main() -> int:
    parser = argparse.ArgumentParser(description="Remove orphaned/unreachable nodes from SLM database")
    parser.add_argument(
        "--ip",
        help="IP address of node to remove",
    )
    parser.add_argument(
        "--node-id",
        help="Node ID to remove directly",
    )
    parser.add_argument(
        "--list-unreachable",
        action="store_true",
        help="List all unreachable nodes without removing",
    )
    parser.add_argument(
        "--api-url",
        default=os.getenv("SLM_API_URL", _DEFAULT_SLM_URL),
        help="SLM API URL (default: from SLM_API_URL env or SSOT config)",
    )
    parser.add_argument(
        "--api-token",
        default=os.getenv("SLM_API_TOKEN"),
        help="SLM API authentication token (default: from SLM_API_TOKEN env)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt",
    )

    args = parser.parse_args()

    if not any([args.ip, args.node_id, args.list_unreachable]):
        parser.print_help()
        return 1

    client = SLMClient(args.api_url, args.api_token)

    try:
        if args.list_unreachable:
            unreachable = await list_unreachable_nodes(client)
            print(f"\nFound {len(unreachable)} unreachable node(s)")
            if unreachable:
                print("\nTo remove a node, run:")
                for node in unreachable:
                    print(f"  python remove_orphaned_node.py --node-id {node['node_id']}")
            return 0

        # Find node to remove
        if args.ip:
            print(f"Looking for node with IP {args.ip}...")
            node = await find_node_by_ip(client, args.ip)
            if not node:
                print(f"ERROR: No node found with IP {args.ip}", file=sys.stderr)
                return 1
            node_id = node["node_id"]
        else:
            node_id = args.node_id
            nodes = await client.list_nodes()
            node = next((n for n in nodes if n["node_id"] == node_id), None)
            if not node:
                print(
                    f"ERROR: No node found with ID {node_id}",
                    file=sys.stderr,
                )
                return 1

        # Display node info
        hostname = node.get("hostname", "unknown")
        ip = node.get("ip_address", "unknown")
        status = node.get("status", "unknown")

        print("\nNode found:")
        print(f"  ID:       {node_id}")
        print(f"  Hostname: {hostname}")
        print(f"  IP:       {ip}")
        print(f"  Status:   {status}")

        # Confirm deletion
        if not args.force:
            response = input("\nRemove this node? [y/N]: ")
            if response.lower() not in ("y", "yes"):
                print("Aborted.")
                return 0

        # Delete node
        print(f"\nRemoving node {node_id}...")
        await client.delete_node(node_id)
        print(f"✓ Node {hostname} ({ip}) removed successfully")
        print("\nThe node will no longer appear in provision warnings.")
        return 0

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
