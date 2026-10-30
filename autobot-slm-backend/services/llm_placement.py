# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Where the backend reaches its LLM node, for the wizard's inventory (#19861)."""

from __future__ import annotations

from autobot_shared.ssot_config import config

#: The LLM roles a backend's model calls go to, the GPU one first.
_LLM_ROLES = ("autobot-llm-gpu", "autobot-llm-cpu")


def llm_infra_vars(node_roles: list, node_id_to_ip: dict[str, str]) -> dict:
    """The LLM node as the backend reaches it: loopback only when both roles share a node.

    Unlike _build_infra_vars, "local" here means the backend's node. An LLM on the SLM host with
    the backend elsewhere is not loopback from the backend.
    """
    nodes_by_role = {nr.role_name: nr.node_id for nr in node_roles}
    llm_node = next((nodes_by_role[role] for role in _LLM_ROLES if role in nodes_by_role), None)
    ip = node_id_to_ip.get(llm_node) if llm_node else None
    if not ip:
        return {}
    co_located = llm_node == nodes_by_role.get("backend")
    return {"llm_host": "127.0.0.1" if co_located else ip, "llm_port": config.port.ollama}
