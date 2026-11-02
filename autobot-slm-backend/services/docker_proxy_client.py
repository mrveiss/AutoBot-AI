# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Service actions on a compose node, through the limited Docker proxy (#20629).

A compose node is a container, with no SSH or systemd to reach: the node's id is its container name.
"""

import logging
import os
from typing import Iterable, Tuple

import aiohttp

from autobot_shared.egress_allowlist import register_internal_origin_provider
from autobot_shared.http_egress_guard import assert_egress_policy

logger = logging.getLogger(__name__)

_ACTION_TIMEOUT_SECONDS = 90


async def _proxy_origin() -> Iterable[str]:
    """The proxy's address is private and comes from configuration, so egress policy must know it."""
    url = os.getenv("AUTOBOT_DOCKER_PROXY_URL", "")
    return [url] if url else []


register_internal_origin_provider(_proxy_origin)


def is_compose_node(node) -> bool:
    """Only a container this stack seeded. The SLM's own node on a native install isn't one."""
    from services.compose_fleet import _COMPOSE_NODE_SPECS, _compose_nodes_enabled

    return _compose_nodes_enabled() and any(spec["id"] == node.node_id for spec in _COMPOSE_NODE_SPECS)


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
                if response.status == 503:
                    return False, f"Failed to {action} service: Docker isn't answering. Check that Docker is running."
                if response.status == 401:
                    return False, f"Failed to {action} service: the Docker proxy token is missing or doesn't match"
                return False, f"Failed to {action} service: the Docker proxy answered {response.status}"
    except Exception as exc:
        logger.error("Docker proxy unreachable for %s on %s: %s", action, node.node_id, exc)
        return (
            False,
            f"Failed to {action} service: the Docker proxy could not be reached. "
            "Check that Docker and autobot-docker-proxy are running.",
        )
