# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Where the backend and the AI stack reach the LLM node, for the wizard's inventory (#19861).

These names are the clients' own. ``llm_host``/``llm_port`` belong to the LLM role: they are
Ollama's listen address, and an inventory var would outrank that role's default.
"""

from __future__ import annotations

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

logger = get_logger(__name__)

#: The LLM roles model calls go to, the GPU one first.
_LLM_ROLES = ("autobot-llm-gpu", "autobot-llm-cpu")
#: Each client role and the vars it reads the LLM node from.
_CLIENTS = {"backend": "backend_ollama", "ai-stack": "ai_stack_ollama"}


def _llm_node(node_roles: list) -> str | None:
    """The node model calls go to: an active row of either role first, GPU before CPU (#20131).

    The other statuses stay a fallback: on a first run every row is still not_installed.
    """
    for active_only in (True, False):
        for role in _LLM_ROLES:
            nodes = [
                nr.node_id for nr in node_roles if nr.role_name == role and (nr.status == "active" or not active_only)
            ]
            if nodes:
                return min(nodes)
    return None


def llm_infra_vars(node_roles: list, node_id_to_ip: dict[str, str]) -> dict:
    """The LLM node as each client reaches it: loopback only when every node of that client is the LLM node."""
    llm_node = _llm_node(node_roles)
    if llm_node is None:
        return {}
    ip = node_id_to_ip.get(llm_node)
    if not ip:
        logger.warning("LLM role is assigned to node %s, which has no known address", llm_node)
        return {}
    infra_vars: dict = {}
    for role, prefix in _CLIENTS.items():
        client_nodes = {nr.node_id for nr in node_roles if nr.role_name == role}
        infra_vars[f"{prefix}_host"] = "127.0.0.1" if client_nodes == {llm_node} else ip
        infra_vars[f"{prefix}_port"] = config.port.ollama
    return infra_vars
