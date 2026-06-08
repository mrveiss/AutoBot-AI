# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for MCP tool prompt injection (#2596, #2631).

Coverage:
- _get_mcp_tools_prompt() returns formatted Markdown when tools are present
- _get_mcp_tools_prompt() returns empty string when no tools are registered
- _get_mcp_tools_prompt() falls back to stale cache when _ensure_cache_fresh raises (#2631)
- process_chat_message() includes MCP tool section in the system prompt sent to the LLM

Note: _get_mcp_tools_prompt is defined on StandardizedAgent (#2631) — ChatAgent
inherits it. The base imports get_mcp_dispatcher lazily inside the method
(`from services.mcp_dispatch import get_mcp_dispatcher`), so patches must
target the source module (#6651).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_TOOL_DEF = {
    "name": "search_knowledge_base",
    "description": "[knowledge_mcp] Search the knowledge base",
    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
}


def _make_mock_dispatcher(tools: list) -> MagicMock:
    """Return a mock MCPDispatcher that yields *tools* from get_tool_definitions."""
    dispatcher = MagicMock()
    dispatcher._ensure_cache_fresh = AsyncMock()
    dispatcher.get_tool_definitions = MagicMock(return_value=tools)
    return dispatcher


# ---------------------------------------------------------------------------
# _get_mcp_tools_prompt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_mcp_tools_prompt_returns_formatted_section():
    """When tools are available, prompt section should list them in Markdown (#2596)."""
    from agents.chat_agent import ChatAgent

    with (
        patch(
            "services.mcp_dispatch.get_mcp_dispatcher",
            return_value=_make_mock_dispatcher([_SAMPLE_TOOL_DEF]),
        ),
        patch.object(ChatAgent, "__init__", lambda self: None),
    ):
        agent = ChatAgent.__new__(ChatAgent)
        result = await agent._get_mcp_tools_prompt()

    assert "## Available MCP Tools" in result
    assert "search_knowledge_base" in result
    assert "[knowledge_mcp] Search the knowledge base" in result


@pytest.mark.asyncio
async def test_get_mcp_tools_prompt_returns_empty_when_no_tools():
    """When no tools are registered, the prompt section should be empty (#2596)."""
    from agents.chat_agent import ChatAgent

    with (
        patch(
            "services.mcp_dispatch.get_mcp_dispatcher",
            return_value=_make_mock_dispatcher([]),
        ),
        patch.object(ChatAgent, "__init__", lambda self: None),
    ):
        agent = ChatAgent.__new__(ChatAgent)
        result = await agent._get_mcp_tools_prompt()

    assert result == ""


# ---------------------------------------------------------------------------
# process_chat_message — MCP section injected into prompt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_tools_injected_into_system_prompt():
    """process_chat_message() should include MCP tool list in the system prompt (#2596)."""
    from agents.chat_agent import ChatAgent

    captured_messages = []

    async def fake_chat_completion(messages, **kwargs):
        captured_messages.extend(messages)
        return {"message": {"content": "Hello!"}}

    mock_llm = MagicMock()
    mock_llm.chat_completion = fake_chat_completion

    with (
        patch(
            "services.mcp_dispatch.get_mcp_dispatcher",
            return_value=_make_mock_dispatcher([_SAMPLE_TOOL_DEF]),
        ),
        patch("agents.chat_agent.resolve_language", return_value="en"),
        patch("agents.chat_agent.get_language_instruction", return_value=""),
        patch.object(ChatAgent, "__init__", lambda self: None),
    ):
        agent = ChatAgent.__new__(ChatAgent)
        agent.llm_interface = mock_llm
        agent.model_name = "test-model"
        agent.llm_provider = "test"
        agent.llm_endpoint = "http://localhost"

        await agent.process_chat_message("hello")

    assert captured_messages, "LLM was not called"
    system_content = captured_messages[0]["content"]
    assert "## Available MCP Tools" in system_content
    assert "search_knowledge_base" in system_content


# ---------------------------------------------------------------------------
# Cache fallback (#2631)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_mcp_tools_prompt_falls_back_to_stale_cache_on_refresh_error():
    """When _ensure_cache_fresh raises, stale tools should still be returned (#2631)."""
    from agents.chat_agent import ChatAgent

    def _make_dispatcher_with_error_and_stale_tools() -> MagicMock:
        """Dispatcher that errors on refresh but has stale tool data."""
        dispatcher = MagicMock()
        dispatcher._ensure_cache_fresh = AsyncMock(side_effect=Exception("registry down"))
        dispatcher.get_tool_definitions = MagicMock(return_value=[_SAMPLE_TOOL_DEF])
        return dispatcher

    with (
        patch(
            "services.mcp_dispatch.get_mcp_dispatcher",
            return_value=_make_dispatcher_with_error_and_stale_tools(),
        ),
        patch.object(ChatAgent, "__init__", lambda self: None),
    ):
        agent = ChatAgent.__new__(ChatAgent)
        result = await agent._get_mcp_tools_prompt()

    # Stale tools should still be returned despite the refresh error
    assert "## Available MCP Tools" in result
    assert "search_knowledge_base" in result
