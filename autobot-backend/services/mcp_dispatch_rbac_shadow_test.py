# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical-RBAC verdict on the MCP dispatcher — shadow (#13228 stage 2) and
enforced (#14523 stage 3).

Stage 1 declared a permission per tool. Stage 2 (below, the `_would_deny` unit
tests) reported what canonical RBAC would decide without acting on it, to
answer the question the flip needed answered first: *which working calls
would it break?* Stage 3 (#14523) promotes that same verdict to the actual
decision `dispatch()` enforces, replacing the retired `_ADMIN_ONLY_TOOLS`
substring blocklist.

The `_would_deny` unit tests below are unchanged by the flip — they test the
decision function, not who acts on it. The `dispatch()` integration tests in
the second half now assert the opposite of what they asserted under stage 2:
a would-be denial refuses the call rather than merely being logged.
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


def test_a_tool_absent_from_a_populated_cache_is_undeclared():
    d = _dispatcher({"get_text": _tool("get_text", "mcp.browser.read")})

    assert d._would_deny("never_seen", "user") == "undeclared"


def test_an_empty_cache_yields_no_verdict_at_all():
    """A registry outage must not be reported as a policy gap.

    ``refresh_tool_cache`` swallows failures and returns 0, so an empty cache means
    "the registry never answered", not "nothing is declared". Reporting the latter
    would fill the inventory with an outage — and if stage 3 enforced on the same
    signal, a registry blip would deny every MCP call: fail-closed on infrastructure
    rather than on policy.
    """
    assert _dispatcher({})._would_deny("never_seen", "user") is None


def test_a_malformed_cache_entry_does_not_raise():
    """Report-only code must never be the thing that breaks a working call."""
    d = _dispatcher({"weird": "not-a-dict", "empty": None})

    assert d._would_deny("weird", "user") == "undeclared"
    assert d._would_deny("empty", "user") == "undeclared"


# ------------------------------------------------------------------ roles


@pytest.mark.parametrize("role", ["superadmin", "SUPERADMIN", "Admin", "ADMIN"])
def test_administrative_roles_are_not_reported_as_unknown(role):
    """The original point of this test, preserved across #13854.

    ``superadmin`` used not to be a ``Role`` member, so ``Role()`` raised on it and
    the shadow log reported the most privileged role in the system as an
    *unrecognised string*. That was the defect: an administrative role and a typo
    produced the same verdict.

    It is a ``Role`` member now, so it resolves — and what it resolves to is a role
    holding no granular permission. The verdict is therefore about a missing
    grant, never about an unknown role. That distinction is the one this test
    exists to protect, and it is asserted directly below rather than inferred from
    ``is None``.
    """
    d = _dispatcher({"click": _tool("click", "mcp.browser.control")})

    verdict = d._would_deny("click", role)

    assert verdict is None or not verdict.startswith("unknown-role"), (
        f"{role!r} resolved as an unrecognised role ({verdict!r}) — it is administrative "
        "and must resolve through the canonical vocabulary"
    )


@pytest.mark.parametrize("role", ["admin", "ADMIN", "Admin"])
def test_admin_is_permitted_every_declared_tool(role):
    """``admin`` holds all 54 permissions, so it is never denied a declared tool."""
    d = _dispatcher({"click": _tool("click", "mcp.browser.control")})

    assert d._would_deny("click", role) is None


@pytest.mark.parametrize("role", ["superadmin", "SUPERADMIN"])
def test_superadmin_is_refused_a_tool_whose_permission_it_does_not_hold(role):
    """#13854: this gate stopped short-circuiting on the administrative predicate.

    Before, ``is_admin_role`` waved superadmin through every tool while the
    canonical mapping said it held nothing — ``ADMIN_ROLES`` acting as a
    permission source. The refusal names the missing grant, so the reason is
    actionable rather than a bare denial.
    """
    d = _dispatcher({"click": _tool("click", "mcp.browser.control")})

    assert d._would_deny("click", role) == "missing:mcp.browser.control"


def test_a_known_role_in_the_wrong_case_still_resolves():
    d = _dispatcher({"get_text": _tool("get_text", "mcp.browser.read")})

    assert d._would_deny("get_text", "USER") is None


@pytest.mark.parametrize("role", [None, ""])
def test_a_missing_role_is_surfaced_not_waved_through(role):
    d = _dispatcher({"click": _tool("click", "mcp.browser.control")})

    assert d._would_deny("click", role) is not None


def test_an_unrecognised_role_is_surfaced_not_waved_through():
    """An unknown role string must not read as permitted."""
    d = _dispatcher({"get_text": _tool("get_text", "mcp.browser.read")})

    assert d._would_deny("get_text", "not-a-role") == "unknown-role:not-a-role"


@pytest.mark.parametrize("role", ["admin", "operator"])
def test_privileged_roles_hold_the_control_grants(role):
    d = _dispatcher({"click": _tool("click", "mcp.browser.control")})

    assert d._would_deny("click", role) is None


# ------------------------------------------------ stage 3: it now refuses


@pytest.mark.asyncio
async def test_an_undeclared_tool_no_longer_dispatches():
    """#14523: the load-bearing test flips here. Stage 2 pinned that shadow mode
    must not refuse; stage 3 is exactly that flip landing on purpose, now that
    #14494 has proven no live tool is actually undeclared."""
    d = _dispatcher({"mystery": _tool("mystery", None)})
    d._ensure_cache_fresh = AsyncMock()
    d._call_bridge = AsyncMock(return_value={"success": True, "result": "ran"})

    with (
        patch("chat_workflow.cot_events.emit_tool_call", AsyncMock()),
        patch("chat_workflow.cot_events.emit_tool_result", AsyncMock()),
    ):
        result = await d.dispatch("mystery", {}, role="readonly")

    assert result.get("success") is False, "an undeclared tool must be refused, not dispatched"
    d._call_bridge.assert_not_called()


@pytest.mark.asyncio
async def test_an_undeclared_tool_is_refused_even_for_admin():
    """#14523: undeclared denies unconditionally — no role, including admin,
    should be able to run a tool nobody has judged what permission it needs."""
    d = _dispatcher({"mystery": _tool("mystery", None)})
    d._ensure_cache_fresh = AsyncMock()
    d._call_bridge = AsyncMock(return_value={"success": True, "result": "ran"})

    with (
        patch("chat_workflow.cot_events.emit_tool_call", AsyncMock()),
        patch("chat_workflow.cot_events.emit_tool_result", AsyncMock()),
    ):
        result = await d.dispatch("mystery", {}, role="admin")

    assert result.get("success") is False
    d._call_bridge.assert_not_called()


@pytest.mark.asyncio
async def test_flushall_still_denies_non_admin_via_canonical_rbac():
    """#14523: replaces `_ADMIN_ONLY_TOOLS` — flushall's real declaration
    (`mcp.manage`, `_DECLARED_AHEAD_OF_TIME` in mcp_tool_permissions.py) is
    admin-exclusive, so the canonical path denies a non-admin exactly like the
    retired substring blocklist did."""
    d = _dispatcher({"flushall": _tool("flushall", "mcp.manage", bridge="redis_mcp")})
    d._ensure_cache_fresh = AsyncMock()
    d._call_bridge = AsyncMock(return_value={"success": True, "result": "ran"})

    with (
        patch("chat_workflow.cot_events.emit_tool_call", AsyncMock()),
        patch("chat_workflow.cot_events.emit_tool_result", AsyncMock()),
    ):
        result = await d.dispatch("flushall", {}, role="user")

    assert result.get("success") is False, "the canonical path stopped enforcing"
    d._call_bridge.assert_not_called()


@pytest.mark.asyncio
async def test_flushall_still_dispatches_for_admin_via_canonical_rbac():
    """The control case: the canonical path is not overly strict — admin still
    reaches flushall, matching the retired blocklist's actual behaviour."""
    d = _dispatcher({"flushall": _tool("flushall", "mcp.manage", bridge="redis_mcp")})
    d._ensure_cache_fresh = AsyncMock()
    d._call_bridge = AsyncMock(return_value={"success": True, "result": "ran"})

    with (
        patch("chat_workflow.cot_events.emit_tool_call", AsyncMock()),
        patch("chat_workflow.cot_events.emit_tool_result", AsyncMock()),
    ):
        result = await d.dispatch("flushall", {}, role="admin")

    assert result.get("success") is True
    d._call_bridge.assert_awaited_once()


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
async def test_the_same_disagreement_is_reported_once(caplog):
    """The deliverable is a set of disagreements, not a stream of them.

    An agent loop that touches one undeclared tool every iteration would otherwise
    emit a warning per iteration, burying the distinct findings this stage exists
    to collect.
    """
    d = _dispatcher({"mystery": _tool("mystery", None)})
    d._ensure_cache_fresh = AsyncMock()
    d._call_bridge = AsyncMock(return_value={"success": True, "result": "ran"})

    with (
        patch("chat_workflow.cot_events.emit_tool_call", AsyncMock()),
        patch("chat_workflow.cot_events.emit_tool_result", AsyncMock()),
    ):
        with caplog.at_level("WARNING"):
            for _ in range(5):
                await d.dispatch("mystery", {}, role="readonly")

    shadow_lines = [r for r in caplog.records if "rbac-shadow" in r.getMessage()]
    assert len(shadow_lines) == 1


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
