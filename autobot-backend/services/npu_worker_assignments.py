# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Nodes the SLM assigned the npu-worker role that have no paired worker (#19706).

Assigning the role deploys a worker, but it gets traffic only once paired. Pairing stays an admin's
act: it sends the worker the Redis credentials, and registering a node and assigning a role in the
SLM take less than an admin. So this only finds the candidates; a person pairs each one.
"""

from typing import Dict, List

from autobot_shared.ssot_config import config

NPU_WORKER_ROLE = "npu-worker"


def unpaired_worker_nodes(nodes: List[dict], paired_urls: List[str], port: int) -> Dict[str, str]:
    """URL -> hostname of each online node holding the role with no paired worker at its URL."""
    paired = {url.rstrip("/") for url in paired_urls}
    found: Dict[str, str] = {}
    for node in nodes:
        if NPU_WORKER_ROLE not in (node.get("roles") or []) or node.get("status") != "online":
            continue
        url = f"http://{node['ip_address']}:{port}"
        if url not in paired:
            found[url] = node.get("hostname") or node["ip_address"]
    return found


async def assigned_unpaired_workers() -> Dict[str, str]:
    """Read the SLM's nodes and the registry. Raises if the SLM cannot be read."""
    from services.fleet_registry import _fetch_registry_nodes
    from services.npu_worker_manager import get_worker_manager

    manager = await get_worker_manager()
    paired_urls = [worker.config.url for worker in await manager.list_workers()]
    return unpaired_worker_nodes(await _fetch_registry_nodes(), paired_urls, config.port.npu)
