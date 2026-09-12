# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the external-MCP-server dispatch fallback in chat_workflow/tool_handler.py (#11542).

_try_mcp_dispatch() falls back to _try_external_mcp_dispatch() when the
internal MCPDispatcher registry doesn't know the tool — see that function's
docstring for why it deliberately skips _emit_before_tool_execute().
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_workflow.tool_handler import _try_external_mcp_dispatch, _try_mcp_dispatch

_MCP_DISPATCH_MODULE = "services.mcp_dispatch"
_EXTERNAL_BRIDGE_MODULE = "services.mcp_external_bridge"


def _internal_dispatcher_with_no_match() -> MagicMock:
    dispatcher = MagicMock()
    dispatcher._cache_loaded = True
    dispatcher.find_tool = MagicMock(return_value=None)
    return dispatcher


class TestTryExternalMcpDispatch:
    @pytest.mark.asyncio
    async def test_unknown_to_both_registries_returns_none(self):
        bridge = MagicMock()
        bridge.has_tool = MagicMock(return_value=False)
        bridge.list_tools = AsyncMock(return_value=[])

        with patch(f"{_EXTERNAL_BRIDGE_MODULE}.get_mcp_external_bridge", return_value=bridge):
            result = await _try_external_mcp_dispatch("nope", {"arguments": {}}, [])

        assert result is None
        bridge.list_tools.assert_awaited_once()  # refreshed once before giving up

    @pytest.mark.asyncio
    async def test_already_known_tool_skips_refresh(self):
        bridge = MagicMock()
        bridge.has_tool = MagicMock(return_value=True)
        bridge.list_tools = AsyncMock()
        bridge.call_tool = AsyncMock(return_value=_success_result("hello"))

        with patch(f"{_EXTERNAL_BRIDGE_MODULE}.get_mcp_external_bridge", return_value=bridge):
            await _try_external_mcp_dispatch("known", {"arguments": {}}, [])

        bridge.list_tools.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_successful_call_returns_tool_result_message(self):
        execution_results = []
        bridge = MagicMock()
        bridge.has_tool = MagicMock(return_value=True)
        bridge.call_tool = AsyncMock(return_value=_success_result({"answer": 42}))

        with patch(f"{_EXTERNAL_BRIDGE_MODULE}.get_mcp_external_bridge", return_value=bridge):
            result = await _try_external_mcp_dispatch("external_search", {"arguments": {"q": "x"}}, execution_results)

        assert result.type == "tool_result"
        assert "42" in result.content
        assert result.metadata["bridge"] == "external"
        assert execution_results[0]["status"] == "success"

    @pytest.mark.asyncio
    async def test_failed_call_returns_error_message(self):
        execution_results = []
        bridge = MagicMock()
        bridge.has_tool = MagicMock(return_value=True)
        bridge.call_tool = AsyncMock(return_value=_failure_result("server unreachable"))

        with patch(f"{_EXTERNAL_BRIDGE_MODULE}.get_mcp_external_bridge", return_value=bridge):
            result = await _try_external_mcp_dispatch("external_search", {"arguments": {}}, execution_results)

        assert result.type == "error"
        assert "server unreachable" in result.content
        assert execution_results[0]["status"] == "error"

    @pytest.mark.asyncio
    async def test_transport_exception_propagates(self):
        """An exception from call_tool() itself (not a handled failure result) re-raises."""
        bridge = MagicMock()
        bridge.has_tool = MagicMock(return_value=True)
        bridge.call_tool = AsyncMock(side_effect=RuntimeError("boom"))

        with patch(f"{_EXTERNAL_BRIDGE_MODULE}.get_mcp_external_bridge", return_value=bridge):
            with pytest.raises(RuntimeError, match="boom"):
                await _try_external_mcp_dispatch("external_search", {"arguments": {}}, [])

    @pytest.mark.asyncio
    async def test_does_not_call_before_tool_execute_hook(self):
        """#14523: the hook would raise PermissionError for any undeclared tool_permission."""
        bridge = MagicMock()
        bridge.has_tool = MagicMock(return_value=True)
        bridge.call_tool = AsyncMock(return_value=_success_result("ok"))

        with patch(f"{_EXTERNAL_BRIDGE_MODULE}.get_mcp_external_bridge", return_value=bridge):
            with patch("chat_workflow.tool_handler._emit_before_tool_execute") as mock_hook:
                await _try_external_mcp_dispatch("external_search", {"arguments": {}}, [])

        mock_hook.assert_not_called()


class TestTryMcpDispatchFallsBackToExternal:
    @pytest.mark.asyncio
    async def test_falls_back_when_internal_registry_misses(self):
        """_try_mcp_dispatch() routes to the external bridge when the internal one doesn't know the tool."""
        bridge = MagicMock()
        bridge.has_tool = MagicMock(return_value=True)
        bridge.call_tool = AsyncMock(return_value=_success_result("from external"))

        with (
            patch(f"{_MCP_DISPATCH_MODULE}.get_mcp_dispatcher", return_value=_internal_dispatcher_with_no_match()),
            patch(f"{_EXTERNAL_BRIDGE_MODULE}.get_mcp_external_bridge", return_value=bridge),
        ):
            result = await _try_mcp_dispatch("external_search", {"arguments": {}}, [])

        assert result is not None
        assert result.type == "tool_result"
        assert "from external" in result.content

    @pytest.mark.asyncio
    async def test_none_when_neither_registry_knows_the_tool(self):
        bridge = MagicMock()
        bridge.has_tool = MagicMock(return_value=False)
        bridge.list_tools = AsyncMock(return_value=[])

        with (
            patch(f"{_MCP_DISPATCH_MODULE}.get_mcp_dispatcher", return_value=_internal_dispatcher_with_no_match()),
            patch(f"{_EXTERNAL_BRIDGE_MODULE}.get_mcp_external_bridge", return_value=bridge),
        ):
            result = await _try_mcp_dispatch("truly_unknown", {"arguments": {}}, [])

        assert result is None


def _success_result(value):
    from services.mcp_external_bridge import ExternalToolCallResult

    return ExternalToolCallResult(success=True, result=value)


def _failure_result(error):
    from services.mcp_external_bridge import ExternalToolCallResult

    return ExternalToolCallResult(success=False, error=error)
