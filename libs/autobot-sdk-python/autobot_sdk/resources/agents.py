# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Agent resource operations."""

from __future__ import annotations

from typing import Any

from ..client import AutoBotClient
from ..models import AgentConfig, AgentHealth, DataResponse


class AgentsResource:
    def __init__(self, client: AutoBotClient) -> None:
        self._c = client

    async def health(self) -> AgentHealth:
        raw = await self._c.get("/health/enhanced")
        return AgentHealth.model_validate(raw)

    async def get_config(self) -> DataResponse[AgentConfig]:
        raw = await self._c.get("/agent/config")
        return DataResponse[AgentConfig].model_validate(raw)

    async def update_config(self, **fields: Any) -> DataResponse[AgentConfig]:
        raw = await self._c.put("/agent/config", fields)
        return DataResponse[AgentConfig].model_validate(raw)

    async def send_command(self, command: str, session_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"command": command}
        if session_id:
            body["session_id"] = session_id
        return await self._c.post("/agent/execute_command", body)
