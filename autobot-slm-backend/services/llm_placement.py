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


def llm_infra_vars(node_roles: list, node_id_to_ip: dict[str, str]) -> dict:
    """The LLM node as each client on its own node reaches it: loopback only when they share one."""
    nodes_by_role = {nr.role_name: nr.node_id for nr in node_roles}
    llm_node = next((nodes_by_role[role] for role in _LLM_ROLES if role in nodes_by_role), None)
    if llm_node is None:
        return {}
    ip = node_id_to_ip.get(llm_node)
    if not ip:
        logger.warning("LLM role is assigned to node %s, which has no known address", llm_node)
        return {}
    infra_vars: dict = {}
    for role, prefix in _CLIENTS.items():
        infra_vars[f"{prefix}_host"] = "127.0.0.1" if nodes_by_role.get(role) == llm_node else ip
        infra_vars[f"{prefix}_port"] = config.port.ollama
    return infra_vars
