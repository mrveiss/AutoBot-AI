# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Agent resource operations.

Paths are written without the ``/api`` root — ``AutoBotClient`` adds it.

The agent surface spans two mounts, which is why a blanket prefix would not
have been enough (#15053): the agent router is registered under ``/agent`` and
per-agent configuration under ``/agent_config``, so ``/health/detailed`` is
served at ``/api/agent/health/detailed``, two segments short of where the SDK
used to ask for it.
"""

from __future__ import annotations

from typing import Any

from ..client import AutoBotClient
from ..models import AgentConfig, AgentHealth


class AgentsResource:
    def __init__(self, client: AutoBotClient) -> None:
        self._c = client

    async def health(self) -> AgentHealth:
        raw = await self._c.get("/agent/health/detailed")
        return AgentHealth.model_validate(raw)

    async def get_config(self, agent_id: str) -> AgentConfig:
        """Configuration of one agent.

        The response is a flat document, not a ``DataResponse`` envelope.
        """
        raw = await self._c.get(f"/agent_config/agents/{agent_id}")
        return AgentConfig.model_validate(raw)

    async def set_model(self, agent_id: str, model: str, provider: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"agent_id": agent_id, "model": model}
        if provider:
            body["provider"] = provider
        return await self._c.post(f"/agent_config/agents/{agent_id}/model", body)

    async def set_enabled(self, agent_id: str, enabled: bool) -> dict[str, Any]:
        action = "enable" if enabled else "disable"
        return await self._c.post(f"/agent_config/agents/{agent_id}/{action}")

    async def send_command(self, command: str) -> dict[str, Any]:
        """Run a shell command through the agent (#15527).

        The route reads one field, ``command``. It used to publish
        ``application/x-www-form-urlencoded`` because of a stray ``Form``
        default, so no body this method could build was ever accepted; the
        ``session_id`` it also sent named nothing the route has — there is no
        session behind ``/execute_command`` — and it went with the fix.
        """
        return await self._c.post("/agent/execute_command", {"command": command})
