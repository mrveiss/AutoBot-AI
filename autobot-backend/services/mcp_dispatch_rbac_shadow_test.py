# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shadow-mode RBAC reporting on the MCP dispatcher (#13228 stage 2).

Stage 1 declared a permission per tool. Stage 3 will refuse the undeclared. This
stage answers the question the flip needs answered first — *which working calls
would it break?* — by reporting the canonical-RBAC verdict without acting on it.

So the property under test is unusual and is the whole point: **the verdict must
change nothing.** A test that only checked the log would pass just as happily if
the shadow had started denying calls, which is the one outcome that must not
happen yet.
"""

from unittest.mock import AsyncMock, patch

import pytest

from services.mcp_dispatch import MCPDispatcher


def _dispatcher(tool_cache: dict) -> MCPDispatcher:
    d = MCPDispatcher()
    d._tool_cache = tool_cache
    d._cache_loaded = True
    return d


def _tool(name: str, permission: str | None, bridge: str = "browser_mcp") -> dict:
    return {
        "name": name,
        "description": "",
        "input_schema": {},
        "bridge": bridge,
        "required_permission": permission,
        "endpoint": f"http://localhost/{name}",
    }


# ------------------------------------------------------------- the verdict


def test_a_permission_the_role_holds_is_not_flagged():
    d = _dispatcher({"get_text": _tool("get_text", "mcp.browser.read")})

    assert d._would_deny("get_text", "user") is None


def test_a_permission_the_role_lacks_is_flagged_with_the_name():
    """The reason has to name the grant, or the fix is a guessing game."""
    d = _dispatcher({"click": _tool("click", "mcp.browser.control")})

    assert d._would_deny("click", "readonly") == "missing:mcp.browser.control"


def test_an_undeclared_tool_is_flagged_distinctly():
    """Undeclared needs a declaration; missing needs a grant. Different fixes."""
    d = _dispatcher({"mystery": _tool("mystery", None)})

    assert d._would_deny("mystery", "admin") == "undeclared"


def test_a_tool_absent_from_the_cache_is_undeclared():
    assert _dispatcher({})._would_deny("never_seen", "admin") == "undeclared"


def test_an_unrecognised_role_is_surfaced_not_waved_through():
    """An unknown role string must not read as permitted."""
    d = _dispatcher({"get_text": _tool("get_text", "mcp.browser.read")})

    assert d._would_deny("get_text", "not-a-role") == "unknown-role:not-a-role"


@pytest.mark.parametrize("role", ["admin", "operator"])
def test_privileged_roles_hold_the_control_grants(role):
    d = _dispatcher({"click": _tool("click", "mcp.browser.control")})

    assert d._would_deny("click", role) is None


# --------------------------------------------- it must not change behaviour


@pytest.mark.asyncio
async def test_a_would_be_denial_still_dispatches():
    """The load-bearing test: shadow mode reports, it does not refuse.

    If this ever fails, stage 2 has silently become stage 3 and every caller of
    an undeclared tool starts breaking without the fallout inventory that the
    flip is supposed to be based on.
    """
    d = _dispatcher({"mystery": _tool("mystery", None)})
    d._ensure_cache_fresh = AsyncMock()
    d._call_bridge = AsyncMock(return_value={"success": True, "result": "ran"})

    with (
        patch("chat_workflow.cot_events.emit_tool_call", AsyncMock()),
        patch("chat_workflow.cot_events.emit_tool_result", AsyncMock()),
    ):
        result = await d.dispatch("mystery", {}, role="readonly")

    assert result.get("success") is True, "shadow mode refused a call it must only report"


@pytest.mark.asyncio
async def test_the_legacy_blocklist_still_decides():
    """`_ADMIN_ONLY_TOOLS` remains the authority until stage 3."""
    d = _dispatcher({"flushall": _tool("flushall", "mcp.manage", bridge="redis_mcp")})
    d._ensure_cache_fresh = AsyncMock()
    d._call_bridge = AsyncMock(return_value={"success": True, "result": "ran"})

    with (
        patch("chat_workflow.cot_events.emit_tool_call", AsyncMock()),
        patch("chat_workflow.cot_events.emit_tool_result", AsyncMock()),
    ):
        result = await d.dispatch("flushall", {}, role="user")

    assert result.get("success") is False, "the legacy blocklist stopped enforcing"


@pytest.mark.asyncio
async def test_the_shadow_verdict_is_logged_for_the_inventory(caplog):
    """The log line is the deliverable — it is what stage 3 gets planned from."""
    d = _dispatcher({"mystery": _tool("mystery", None)})
    d._ensure_cache_fresh = AsyncMock()
    d._call_bridge = AsyncMock(return_value={"success": True, "result": "ran"})

    with (
        patch("chat_workflow.cot_events.emit_tool_call", AsyncMock()),
        patch("chat_workflow.cot_events.emit_tool_result", AsyncMock()),
    ):
        with caplog.at_level("WARNING"):
            await d.dispatch("mystery", {}, role="readonly")

    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "rbac-shadow" in logged
    assert "mystery" in logged and "undeclared" in logged
    assert "#13228" in logged, "the log must point at the issue that explains it"


@pytest.mark.asyncio
async def test_a_permitted_call_logs_nothing(caplog):
    """Shadow noise on every allowed call would drown the signal it exists to give."""
    d = _dispatcher({"get_text": _tool("get_text", "mcp.browser.read")})
    d._ensure_cache_fresh = AsyncMock()
    d._call_bridge = AsyncMock(return_value={"success": True, "result": "ran"})

    with (
        patch("chat_workflow.cot_events.emit_tool_call", AsyncMock()),
        patch("chat_workflow.cot_events.emit_tool_result", AsyncMock()),
    ):
        with caplog.at_level("WARNING"):
            await d.dispatch("get_text", {}, role="user")

    assert "rbac-shadow" not in "\n".join(r.getMessage() for r in caplog.records)
