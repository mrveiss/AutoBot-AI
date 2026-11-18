# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Desktop control is gated on `mcp.desktop.control`, not the admin role (#19087).

THREAT_MODEL section 5 names `enforce_ws_desktop_auth` the one gate. `/ws/desktop`
and the vnc_mcp REST control tools checked `is_admin_role` instead. "an admin
without mcp.desktop.control" is built by patching ROLE_PERMISSIONS["admin"], so it does not depend on
superadmin's grants; superadmin is asserted against whatever the real table says.
Only the credential seams are patched; the gates are the real code.
"""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import auth_middleware
import auth_rbac
from api import advanced_control, vnc_mcp, ws_security
from autobot_shared.auth import permissions
from autobot_shared.auth.mcp_tool_permissions import required_permission
from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role, is_admin_role, role_has_permission

CONTROL_TOOLS = ["desktop_mouse_click", "desktop_keyboard_type", "desktop_special_key"]
READ_TOOLS = ["desktop_screenshot", "desktop_observe_state"]
ALL_TOOLS = CONTROL_TOOLS + READ_TOOLS


def _user(role: str) -> dict:
    return {"username": f"{role}-u", "user_id": f"id-{role}", "role": role}


_DESKTOP = {Permission.MCP_DESKTOP_READ, Permission.MCP_DESKTOP_CONTROL}


@pytest.fixture
def admin_without_desktop(monkeypatch):
    """An admin-role caller that lacks the desktop permissions, by patching the table.

    Independent of what any other role holds (superadmin's grants are a separate decision), so the
    refusal tests hold whether or not superadmin is ever given admin's set.
    """
    stripped = [p for p in ROLE_PERMISSIONS[Role.ADMIN] if p not in _DESKTOP]
    monkeypatch.setitem(ROLE_PERMISSIONS, Role.ADMIN, stripped)
    # role_has_permission answers from this derived cache, built once from the table.
    monkeypatch.setitem(permissions._ROLE_PERMISSION_VALUES, Role.ADMIN, frozenset(p.value for p in stripped))
    assert is_admin_role("admin")
    assert not role_has_permission("admin", Permission.MCP_DESKTOP_CONTROL)


def test_premise_admin_holds_the_permission_and_user_only_reads() -> None:
    assert role_has_permission("admin", Permission.MCP_DESKTOP_CONTROL)
    # `user` reads the desktop but never drives it: the READ/CONTROL split the map declares.
    assert role_has_permission("user", Permission.MCP_DESKTOP_READ)
    assert not role_has_permission("user", Permission.MCP_DESKTOP_CONTROL)


def test_routes_follow_the_canonical_map() -> None:
    assert {t: required_permission(t) for t in CONTROL_TOOLS} == dict.fromkeys(
        CONTROL_TOOLS, Permission.MCP_DESKTOP_CONTROL
    )
    assert {t: required_permission(t) for t in READ_TOOLS} == dict.fromkeys(READ_TOOLS, Permission.MCP_DESKTOP_READ)


def _raise_403(*_a, **_k):
    raise HTTPException(status_code=403, detail="denied")


def _post(role: str, path: str, *, admin_gate: bool = True) -> int:
    """POST through the real router and gates; only credential resolution (and optionally the role gate) is patched."""
    user = _user(role)
    app = FastAPI()
    app.include_router(vnc_mcp.router)
    gate = auth_rbac._permission_gate
    patches = [
        patch.object(auth_middleware, "resolve_human_user", AsyncMock(return_value=user)),
        patch.object(auth_rbac, "resolve_human_user", AsyncMock(return_value=user)),
        patch.object(gate, "_wire_rbac", lambda: None),
        patch.object(gate, "_load_db_names", AsyncMock(return_value=())),
        patch.object(gate, "deny", AsyncMock(side_effect=_raise_403)),
    ]
    if not admin_gate:  # isolate the permission layer from the router's admin-role layer
        app.dependency_overrides[auth_middleware.check_admin_permission] = lambda: True
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        return TestClient(app, raise_server_exceptions=False).post(path, json={}).status_code


@pytest.mark.parametrize("tool", ALL_TOOLS)
def test_rest_admin_without_permission_is_refused(tool: str, admin_without_desktop) -> None:
    assert _post("admin", f"/mcp/{tool}") == 403


@pytest.mark.parametrize("tool", ALL_TOOLS)
def test_rest_superadmin_follows_the_real_table(tool: str) -> None:
    """Superadmin is judged by the table alone, no route special-case: admitted iff the table grants it."""
    granted = role_has_permission("superadmin", required_permission(tool))
    assert (_post("superadmin", f"/mcp/{tool}") not in (401, 403)) is granted


@pytest.mark.parametrize("tool", ALL_TOOLS)
def test_rest_permission_holder_passes_the_gate(tool: str) -> None:
    # The gate admits; the handler may then fail validation/capture, but never 401/403.
    assert _post("admin", f"/mcp/{tool}") not in (401, 403)


@pytest.mark.parametrize("tool", CONTROL_TOOLS)
def test_rest_read_only_role_is_refused_control_tools(tool: str) -> None:
    assert _post("user", f"/mcp/{tool}", admin_gate=False) == 403


@pytest.mark.parametrize("tool", READ_TOOLS)
def test_rest_read_only_role_passes_read_tools(tool: str) -> None:
    assert _post("user", f"/mcp/{tool}", admin_gate=False) not in (401, 403)


def test_non_tool_routes_pass_the_permission_layer() -> None:
    assert _post("user", "/observations/desktop", admin_gate=False) not in (401, 403)


@pytest.mark.asyncio
async def test_an_undeclared_mcp_tool_is_refused() -> None:
    request = MagicMock()
    request.scope = {"route": MagicMock(path="/mcp/not_a_declared_tool")}
    with pytest.raises(HTTPException) as err:
        await auth_rbac.check_mcp_tool_permission(request)
    assert err.value.status_code == 403


class _FakeWS:
    def __init__(self) -> None:
        self.accepted = False
        self.closed_with: tuple[int, str] | None = None

    async def accept(self, *a, **k) -> None:
        self.accepted = True

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed_with = (code, reason)


async def _accept(w) -> None:
    await w.accept()


async def _ws_connect(role: str) -> _FakeWS:
    """Run the real endpoint with only the credential seams patched."""
    ws = _FakeWS()
    streaming = MagicMock()
    streaming.handle_websocket_client = AsyncMock()
    with (
        patch.object(advanced_control, "enforce_ws_origin", AsyncMock(return_value=True)),
        patch.object(ws_security, "_resolve_ws_device_credential", AsyncMock(return_value=None)),
        patch.object(ws_security, "enforce_ws_authentication", AsyncMock(return_value=_user(role))),
        patch.object(advanced_control, "get_desktop_streaming", return_value=streaming),
        patch.object(advanced_control, "accept_websocket", _accept),
    ):
        await advanced_control.desktop_streaming_websocket(ws, "s1")
    ws.handled = streaming.handle_websocket_client.await_count
    return ws


@pytest.mark.asyncio
async def test_ws_admin_without_permission_is_refused(admin_without_desktop) -> None:
    ws = await _ws_connect("admin")
    assert ws.closed_with is not None and ws.closed_with[0] == 1008
    assert not ws.accepted and ws.handled == 0


@pytest.mark.asyncio
async def test_ws_permission_holder_is_admitted() -> None:
    ws = await _ws_connect("admin")
    assert ws.closed_with is None, ws.closed_with
    assert ws.accepted and ws.handled == 1


@pytest.mark.asyncio
async def test_ws_superadmin_follows_the_real_table() -> None:
    ws = await _ws_connect("superadmin")
    assert ws.accepted is role_has_permission("superadmin", Permission.MCP_DESKTOP_CONTROL)
