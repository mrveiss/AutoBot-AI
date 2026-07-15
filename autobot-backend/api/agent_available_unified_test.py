# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the unified GET /agent/agents/available entry point (#6828).

The endpoint must merge AI Stack agents with the canonical local
AgentCapabilityRegistry, support a ``capability`` filter ("find an agent that
can do X"), and degrade to local-only instead of 503 when the AI Stack is
unreachable (#10511 precedent).
"""

from unittest.mock import AsyncMock

import pytest

import api.agent as agent_api
from services.ai_stack_client import AIStackError


def _stub_ai_client(agents: list[str]) -> AsyncMock:
    client = AsyncMock()
    client.list_available_agents = AsyncMock(return_value={"agents": agents})
    return client


def _agents_from(result) -> dict:
    # create_success_response returns a DataResponse pydantic model.
    return {a["name"]: a for a in result.data["agents"]}


async def _call(monkeypatch, ai_client, capability=None):
    async def _get_client():
        return ai_client

    monkeypatch.setattr(agent_api, "get_ai_stack_client", _get_client)
    return await agent_api.list_available_agents(capability=capability)


async def test_merges_ai_stack_and_local_registry(monkeypatch) -> None:
    result = await _call(monkeypatch, _stub_ai_client(["rag"]))
    agents = _agents_from(result)

    assert "rag" in agents  # AI Stack source preserved
    assert "research_agent" in agents  # local canonical registry merged in
    assert agents["rag"]["description"].startswith("Retrieval-Augmented")


async def test_ai_stack_entry_wins_name_collisions(monkeypatch) -> None:
    result = await _call(monkeypatch, _stub_ai_client(["research_agent"]))
    agents = _agents_from(result)

    # One entry only, and it is the AI Stack one (fallback description).
    assert agents["research_agent"]["description"] == "AI agent: research_agent"


async def test_capability_filter_finds_agent_that_can_do_x(monkeypatch) -> None:
    result = await _call(monkeypatch, _stub_ai_client(["rag"]), capability="web_search")
    agents = _agents_from(result)

    assert "research_agent" in agents  # specialization: web_search
    assert "rag" not in agents  # no web_search capability


async def test_degrades_to_local_when_ai_stack_unavailable(monkeypatch) -> None:
    failing = AsyncMock()
    failing.list_available_agents = AsyncMock(side_effect=AIStackError("down"))

    result = await _call(monkeypatch, failing)
    agents = _agents_from(result)

    assert "research_agent" in agents
    assert "system_agent" in agents


async def test_total_agents_matches_list_length(monkeypatch) -> None:
    result = await _call(monkeypatch, _stub_ai_client(["rag", "chat"]))
    assert result.data["total_agents"] == len(result.data["agents"])


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
