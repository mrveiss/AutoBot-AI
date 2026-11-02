# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pair every node the SLM assigned the npu-worker role (#19706).

Assigning the role in the SLM deploys a worker, but a worker gets traffic only once it is paired
in the backend's registry, and that was a separate step in another UI. The SLM is the authority on
which nodes hold the role, so a person assigning it should not have to do anything further.

Removing a worker is not automated: an unassigned worker stays registered until someone unpairs it.
"""

import asyncio
from typing import Dict, List

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

logger = get_logger(__name__)

NPU_WORKER_ROLE = "npu-worker"
AUTOPAIR_INTERVAL_S = env_int_clamped("AUTOBOT_NPU_WORKER_AUTOPAIR_INTERVAL_S", 60, min_v=5)

_task: asyncio.Task | None = None


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


async def pair_assigned_workers() -> int:
    """Pair what the SLM assigned and the registry lacks; return how many paired.

    One worker failing to pair must not stop the others, and the next pass retries it.
    """
    from api.npu_workers import _execute_worker_pairing
    from services.fleet_registry import _fetch_registry_nodes
    from services.npu_worker_manager import get_worker_manager

    manager = await get_worker_manager()
    paired_urls = [worker.config.url for worker in await manager.list_workers()]
    missing = unpaired_worker_nodes(await _fetch_registry_nodes(), paired_urls, config.port.npu)
    paired = 0
    for url, hostname in missing.items():
        try:
            await _execute_worker_pairing(url, hostname, True)
            logger.info("Paired NPU worker on %s, assigned in the SLM", hostname)
            paired += 1
        except Exception as exc:
            logger.warning("Could not pair the NPU worker on %s yet: %s", hostname, exc)
    return paired


async def _autopair_loop() -> None:
    while True:
        try:
            await pair_assigned_workers()
        except Exception as exc:  # SLM unreachable or link not up: nothing to act on this pass
            logger.warning("NPU worker auto-pairing skipped this pass: %s", exc)
        await asyncio.sleep(AUTOPAIR_INTERVAL_S)


def start_npu_worker_autopair() -> None:
    """Start the background pass once per process."""
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_autopair_loop(), name="npu-worker-autopair")
