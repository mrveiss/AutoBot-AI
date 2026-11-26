# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Agent errors shared by the board controls (split from controls_service for size, #15907)."""

from ..exceptions import PublicMessageMixin


class AgentNotFoundError(Exception):
    pass


class AgentNotSchedulableError(PublicMessageMixin, Exception):
    """Enabling a heartbeat on an agent whose status means it must never run (#15907)."""

    def __init__(self, agent_id: str, status: str) -> None:
        super().__init__(f"Agent {agent_id} is {status}; its heartbeat cannot be enabled")
        self.status = status
