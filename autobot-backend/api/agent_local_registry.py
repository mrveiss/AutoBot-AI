# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Local orchestration registry agents for /agents/available (#6828; split out of api/agent.py)."""

from typing import List


def local_registry_agents() -> List[dict]:
    """Agents from the canonical in-process AgentCapabilityRegistry (#6828).

    Exposes the orchestration profiles (capabilities + specializations) through
    the same response shape as AI Stack agents so /agents/available is the one
    unified "find an agent that can do X" entry point.
    """
    from orchestration.agent_registry import get_default_capability_registry

    agents = []
    for profile in get_default_capability_registry().get_all().values():
        capabilities = sorted({c.value for c in profile.capabilities} | set(profile.specializations))
        agents.append(
            {
                "name": profile.agent_id,
                "description": f"Local orchestration agent ({profile.agent_type})",
                "capabilities": capabilities,
                "status": profile.availability_status,
            }
        )
    return agents
