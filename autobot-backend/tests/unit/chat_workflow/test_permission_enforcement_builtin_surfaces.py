# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""RBAC denial reaches execute_command/browser/web_search — the three call
sites #14420 left unwired (#14469).

`_try_mcp_dispatch` was fixed in #14420 to populate `tool_permission` and
`user_role` on the hook context it feeds `PermissionEnforcementExtension`.
Three sibling call sites in the same file — `_process_single_command`
(execute_command), `_handle_browser_tool`, and `_handle_web_search_tool` —
never received `role` at all and never declared a `tool_permission`, so
`PermissionEnforcementExtension` read every call through them as an
undeclared/legacy tool and allowed it through unconditionally regardless of
the caller's RBAC role.

Every test here dispatches through the real handler with the real
`ExtensionManager` singleton and the real `PermissionEnforcementExtension`
registered — only the actual side-effecting I/O (terminal execution, the
browser VM call) is stubbed. A test that only proved the extension's own
logic would have passed before this fix; these prove the *call site* denies.
"""

from unittest.mock import AsyncMock, patch

import pytest

from chat_workflow.tool_handler import ToolHandlerMixin
from middleware.builtin.permission_enforcement import PermissionEnforcementExtension
from middleware.manager import get_extension_manager, reset_extension_manager


def _handler() -> ToolHandlerMixin:
    return ToolHandlerMixin.__new__(ToolHandlerMixin)  # no __init__ side effects needed


@pytest.fixture(autouse=True)
def _real_permission_enforcement():
    """Register the real extension on the real singleton every hook call reads."""
    reset_extension_manager()
    get_extension_manager().register(PermissionEnforcementExtension())
    yield
    reset_extension_manager()


# --------------------------------------------------------------------------
# execute_command — Permission.SHELL_EXECUTE
# --------------------------------------------------------------------------


class TestExecuteCommandDenial:
    """`user`/`readonly` do not hold `allow_shell_execute`; `operator`/`admin` do."""

    def _tool_call(self) -> dict:
        return {"name": "execute_command", "params": {"command": "ls", "host": "main"}, "description": ""}

    @pytest.mark.asyncio
    async def test_a_role_lacking_shell_execute_is_denied(self):
        handler = _handler()
        handler._execute_terminal_command = AsyncMock(return_value={"status": "success", "stdout": "hi"})

        messages = [
            msg
            async for msg in handler._process_single_command(
                self._tool_call(), "sess-1", "term-1", "http://ollama", "model", [], [], role="user"
            )
        ]

        assert messages[-1].type == "error"
        assert messages[-1].metadata.get("cancelled_by_hook") is True
        assert messages[-1].metadata.get("reason") == "permission_denied"
        handler._execute_terminal_command.assert_not_called()

    @pytest.mark.asyncio
    async def test_an_unauthenticated_caller_is_denied(self):
        handler = _handler()
        handler._execute_terminal_command = AsyncMock(return_value={"status": "success", "stdout": "hi"})

        messages = [
            msg
            async for msg in handler._process_single_command(
                self._tool_call(), "sess-1", "term-1", "http://ollama", "model", [], [], role=None
            )
        ]

        assert messages[-1].metadata.get("cancelled_by_hook") is True
        handler._execute_terminal_command.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_role_holding_shell_execute_is_allowed(self):
        """`admin` is the only role holding SHELL_EXECUTE — the control case
        proving this discriminates rather than always denying."""
        handler = _handler()
        handler._execute_terminal_command = AsyncMock(return_value={"status": "error", "error": "boom", "stderr": ""})

        async for _msg in handler._process_single_command(
            self._tool_call(), "sess-1", "term-1", "http://ollama", "model", [], [], role="admin"
        ):
            pass

        handler._execute_terminal_command.assert_awaited_once()


# --------------------------------------------------------------------------
# browser tools — MCP_BROWSER_READ (baseline) / MCP_BROWSER_CONTROL (drives)
# --------------------------------------------------------------------------


class TestBrowserToolDenial:
    @pytest.mark.asyncio
    async def test_a_role_lacking_browser_control_is_denied_for_click(self):
        """`user` holds MCP_BROWSER_READ but not MCP_BROWSER_CONTROL."""
        handler = _handler()
        mock_send = AsyncMock(return_value={"success": True, "result": {}})
        tool_call = {"name": "click", "params": {"selector": "#go"}, "description": "click"}

        with patch("api.browser_mcp.send_to_browser_vm", mock_send):
            messages = [
                msg async for msg in handler._handle_browser_tool(tool_call, [], session_id="sess-1", role="user")
            ]

        assert messages[-1].type == "error"
        assert messages[-1].metadata.get("cancelled_by_hook") is True
        assert messages[-1].metadata.get("reason") == "permission_denied"
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_role_holding_browser_control_is_allowed_for_click(self):
        """`operator` holds MCP_BROWSER_CONTROL — the control case."""
        handler = _handler()
        mock_send = AsyncMock(return_value={"success": True, "result": {}})
        tool_call = {"name": "click", "params": {"selector": "#go"}, "description": "click"}

        with patch("api.browser_mcp.send_to_browser_vm", mock_send):
            async for _msg in handler._handle_browser_tool(tool_call, [], session_id="sess-1", role="operator"):
                pass

        mock_send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_role_lacking_browser_read_is_denied_for_navigate(self):
        """`readonly` holds neither MCP_BROWSER_READ nor MCP_BROWSER_CONTROL."""
        handler = _handler()
        mock_send = AsyncMock(return_value={"success": True, "result": {}})
        tool_call = {"name": "navigate", "params": {"url": "https://example.com"}, "description": "go"}

        with (
            patch("api.browser_mcp.is_url_allowed", AsyncMock(return_value=True)),
            patch("api.browser_mcp.send_to_browser_vm", mock_send),
        ):
            messages = [
                msg async for msg in handler._handle_browser_tool(tool_call, [], session_id="sess-1", role="readonly")
            ]

        assert messages[-1].metadata.get("cancelled_by_hook") is True
        assert messages[-1].metadata.get("reason") == "permission_denied"
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_role_holding_browser_read_is_allowed_for_navigate(self):
        handler = _handler()
        mock_send = AsyncMock(return_value={"success": True, "result": {}})
        tool_call = {"name": "navigate", "params": {"url": "https://example.com"}, "description": "go"}

        with (
            patch("api.browser_mcp.is_url_allowed", AsyncMock(return_value=True)),
            patch("api.browser_mcp.send_to_browser_vm", mock_send),
        ):
            async for _msg in handler._handle_browser_tool(tool_call, [], session_id="sess-1", role="user"):
                pass

        mock_send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_role_lacking_browser_control_is_denied_for_select(self):
        """#14469: `select` was previously undeclared (inherited MCP_BROWSER_READ)."""
        handler = _handler()
        mock_send = AsyncMock(return_value={"success": True, "result": {}})
        tool_call = {"name": "select", "params": {"selector": "#opt", "value": "a"}, "description": "select"}

        with patch("api.browser_mcp.send_to_browser_vm", mock_send):
            messages = [
                msg async for msg in handler._handle_browser_tool(tool_call, [], session_id="sess-1", role="user")
            ]

        assert messages[-1].metadata.get("cancelled_by_hook") is True
        mock_send.assert_not_called()


# --------------------------------------------------------------------------
# web_search — MCP_BROWSER_READ
# --------------------------------------------------------------------------


class TestWebSearchDenial:
    def _tool_call(self) -> dict:
        return {"name": "web_search", "params": {"query": "hello"}, "description": ""}

    @pytest.mark.asyncio
    async def test_a_role_lacking_browser_read_is_denied(self):
        handler = _handler()
        handler._execute_web_search = AsyncMock(return_value="results")

        messages = [
            msg
            async for msg in handler._handle_web_search_tool(
                self._tool_call(), [], session_id="sess-1", role="readonly"
            )
        ]

        assert messages[-1].metadata.get("cancelled_by_hook") is True
        assert messages[-1].metadata.get("reason") == "permission_denied"
        handler._execute_web_search.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_role_holding_browser_read_is_allowed(self):
        handler = _handler()
        handler._execute_web_search = AsyncMock(return_value="results")

        async for _msg in handler._handle_web_search_tool(self._tool_call(), [], session_id="sess-1", role="user"):
            pass

        handler._execute_web_search.assert_awaited_once()

# --------------------------------------------------------------------------
# LLC work-object tools — Permission.WORKFLOW_CREATE (#14491)
#
# `_handle_llc_tool` never called BEFORE_TOOL_EXECUTE at all before this: the
# branch reached `dispatch_llc_tool` (a real DB mutation) directly. This is
# the highest-risk of the seven branches #14491 catalogued.
# --------------------------------------------------------------------------


class TestLLCToolDenial:
    def _tool_call(self) -> dict:
        return {"name": "create_task", "params": {"title": "Ship it"}, "description": ""}

    @pytest.mark.asyncio
    async def test_a_role_lacking_workflow_create_is_denied(self):
        handler = _handler()
        with patch("chat_workflow.tool_handler.dispatch_llc_tool", AsyncMock()) as mock_dispatch:
            messages = [
                msg
                async for msg in handler._handle_llc_tool(
                    "create_task", self._tool_call(), [], None, session_id="sess-1", role="user"
                )
            ]

        assert messages[-1].type == "error"
        assert messages[-1].metadata.get("cancelled_by_hook") is True
        assert messages[-1].metadata.get("reason") == "permission_denied"
        mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_an_unauthenticated_caller_is_denied(self):
        handler = _handler()
        with patch("chat_workflow.tool_handler.dispatch_llc_tool", AsyncMock()) as mock_dispatch:
            async for _msg in handler._handle_llc_tool(
                "create_task", self._tool_call(), [], None, session_id="sess-1", role=None
            ):
                pass

        mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_role_holding_workflow_create_is_allowed(self):
        """`operator` holds WORKFLOW_CREATE — the control case proving this
        discriminates rather than always denying."""
        handler = _handler()
        with patch(
            "chat_workflow.tool_handler.dispatch_llc_tool",
            AsyncMock(return_value={"status": "success", "entity_type": "work_item", "entity_id": "wi-1"}),
        ) as mock_dispatch:
            async for _msg in handler._handle_llc_tool(
                "create_task", self._tool_call(), [], None, session_id="sess-1", role="operator"
            ):
                pass

        mock_dispatch.assert_awaited_once()


# --------------------------------------------------------------------------
# Web research tools — reuse TOOL_PERMISSIONS' existing KNOWLEDGE_READ/WRITE
# declaration for the same tool names on the MCP-registry path (#14491).
# --------------------------------------------------------------------------


class TestWebResearchToolDenial:
    def _tool_call(self, name: str, params: dict) -> dict:
        return {"name": name, "params": params, "description": ""}

    @pytest.mark.asyncio
    async def test_an_unauthenticated_caller_is_denied_for_scrape_url(self):
        """scrape_url declares KNOWLEDGE_READ; role=None holds nothing."""
        handler = _handler()
        handler._exec_scrape_url = AsyncMock(return_value="content")

        messages = [
            msg
            async for msg in handler._handle_web_research_tool(
                "scrape_url",
                self._tool_call("scrape_url", {"url": "https://example.com"}),
                [],
                session_id="sess-1",
                role=None,
            )
        ]

        assert messages[-1].metadata.get("cancelled_by_hook") is True
        assert messages[-1].metadata.get("reason") == "permission_denied"
        handler._exec_scrape_url.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_role_holding_knowledge_read_is_allowed_for_scrape_url(self):
        handler = _handler()
        handler._exec_scrape_url = AsyncMock(return_value="content")

        async for _msg in handler._handle_web_research_tool(
            "scrape_url",
            self._tool_call("scrape_url", {"url": "https://example.com"}),
            [],
            session_id="sess-1",
            role="user",
        ):
            pass

        handler._exec_scrape_url.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_role_lacking_knowledge_write_is_denied_for_crawl_site(self):
        """crawl_site declares KNOWLEDGE_WRITE; `user` holds only KNOWLEDGE_READ."""
        handler = _handler()
        handler._exec_crawl_site = AsyncMock(return_value="index")

        messages = [
            msg
            async for msg in handler._handle_web_research_tool(
                "crawl_site",
                self._tool_call("crawl_site", {"seed_urls": ["https://example.com"]}),
                [],
                session_id="sess-1",
                role="user",
            )
        ]

        assert messages[-1].metadata.get("cancelled_by_hook") is True
        assert messages[-1].metadata.get("reason") == "permission_denied"
        handler._exec_crawl_site.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_role_holding_knowledge_write_is_allowed_for_crawl_site(self):
        """`operator` holds KNOWLEDGE_WRITE — the control case."""
        handler = _handler()
        handler._exec_crawl_site = AsyncMock(return_value="index")

        async for _msg in handler._handle_web_research_tool(
            "crawl_site",
            self._tool_call("crawl_site", {"seed_urls": ["https://example.com"]}),
            [],
            session_id="sess-1",
            role="operator",
        ):
            pass

        handler._exec_crawl_site.assert_awaited_once()
