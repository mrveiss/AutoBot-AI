# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Service actions on a compose node, through the limited Docker proxy (#20629).

A compose node is a container, with no SSH or systemd to reach: the node's id is its container name.
"""

import logging
import os
from typing import Tuple

import aiohttp

from autobot_shared.http_egress_guard import assert_egress_policy

logger = logging.getLogger(__name__)

_ACTION_TIMEOUT_SECONDS = 90


def is_compose_node(node) -> bool:
    from services.compose_fleet import _SELF_MANAGED_NODE_IDS

    return node.node_id in _SELF_MANAGED_NODE_IDS


async def run_compose_service_action(node, service_name: str, action: str) -> Tuple[bool, str]:
    """Run start, stop or restart on the node's container. Returns (success, message)."""
    url = f"{os.getenv('AUTOBOT_DOCKER_PROXY_URL', '')}/containers/{node.node_id}/{action}"
    headers = {"X-Docker-Proxy-Token": os.getenv("AUTOBOT_DOCKER_PROXY_TOKEN", "")}
    timeout = aiohttp.ClientTimeout(total=_ACTION_TIMEOUT_SECONDS)
    try:
        await assert_egress_policy(url)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, allow_redirects=False) as response:
                if response.status == 200:
                    logger.info("Container %s %s completed", node.node_id, action)
                    return True, f"Service {service_name} {action} completed"
                logger.error("Docker proxy refused %s on %s: HTTP %s", action, node.node_id, response.status)
                return False, f"Failed to {action} service: the Docker proxy answered {response.status}"
    except Exception as exc:
        logger.error("Docker proxy unreachable for %s on %s: %s", action, node.node_id, exc)
        return False, f"Failed to {action} service: the Docker proxy could not be reached"
