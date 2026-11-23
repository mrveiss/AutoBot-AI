# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#22141: /agents/available and /agents/status accept the dict shape the AI Stack client really returns."""

from unittest.mock import AsyncMock

import api.agent as agent_api
from api.schemas_agent_roster import AgentStatusData
from services.ai_stack_client import AIStackClient, AIStackError

# The exact shape AIStackClient.list_available_agents builds when Ollama is configured (#6228).
OLLAMA_AGENTS = {
    "agents": [
        {
            "type": "llama3_2_3b",
            "name": "llama3.2:3b",
            "status": "ready",
            "provider": "ollama",
            "parameters": "3.2B",
        }
    ],
    "total": 1,
    "source": "ollama",
}


def _client() -> AsyncMock:
    client = AsyncMock()
    client.list_available_agents = AsyncMock(return_value=OLLAMA_AGENTS)
    client.health_check = AsyncMock(return_value={"status": "healthy"})
    return client


async def _patched(monkeypatch) -> None:
    async def _get_client():
        return _client()

    monkeypatch.setattr(agent_api, "get_ai_stack_client", _get_client)


async def test_available_route_accepts_dict_agents(monkeypatch) -> None:
    await _patched(monkeypatch)
    result = await agent_api.list_available_agents()
    names = {a["name"] for a in result.data["agents"]}
    assert "llama3.2:3b" in names


async def test_status_route_accepts_dict_agents(monkeypatch) -> None:
    await _patched(monkeypatch)
    result = await agent_api.get_agents_status()
    data = AgentStatusData.model_validate(result.data)
    assert data.total_agents == 1
    assert data.available_agents[0].name == "llama3.2:3b"
    assert data.available_agents[0].provider == "ollama"


async def test_client_fallback_returns_same_typed_shape() -> None:
    client = AIStackClient(base_url="http://ai-stack.invalid", enabled=False)
    client._ollama_url = None
    client._make_request = AsyncMock(side_effect=AIStackError("down"))
    info = await client.list_available_agents()
    assert info["source"] == "fallback_config"
    assert all(isinstance(a, dict) and a["name"] == a["type"] for a in info["agents"])
