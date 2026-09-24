# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The desktop socket needs more than "is this somebody" (#17054).

`api/vnc_proxy`'s websockify route calls `enforce_ws_desktop_auth`, which named
`DESKTOP_VIEW` and `DESKTOP_INPUT` in its signature. Those apply to a *paired
device*. An ordinary browser session presents no device credential, so
`enforce_ws_remote_control_auth` delegated it to `enforce_ws_authentication`,
which asks only whether the caller is authenticated — and **any signed-in
account, whatever its role, got full view and input of the managed desktop**.

The capability names were in the signature the whole time and never reached the
path most callers take. That is why this file tests the ROLE decision through
the real `enforce_ws_remote_control_auth` rather than by patching it: patching
the function under the gate would test the gate on a path production does not
use, which is how the previous version of a fix elsewhere in this repo passed
with the vulnerability intact.

Patched seams are the two the existing capability test already uses —
`_resolve_ws_device_credential` (the JWT validation seam) and
`enforce_ws_authentication` (the user-credential seam). Everything between them,
including the new gate, is the real code.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from api import ws_security
from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role, role_has_permission


class _FakeWS:
    """Records whether the handshake was refused, and with what."""

    def __init__(self) -> None:
        self.closed_with: tuple[int, str] | None = None

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed_with = (code, reason)


def _as_user(role: str) -> dict:
    return {"username": f"{role}-user", "user_id": f"id-{role}", "role": role}


def _gate(user: dict | None):
    """Patch only the two credential seams; run the real chain and gate."""
    return (
        patch.object(ws_security, "_resolve_ws_device_credential", AsyncMock(return_value=None)),
        patch.object(ws_security, "enforce_ws_authentication", AsyncMock(return_value=user)),
    )


# ---------------------------------------------------------------------------
# The roles that may drive the desktop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["admin", "operator"])
async def test_a_role_holding_desktop_control_is_admitted(role: str) -> None:
    """These two hold `mcp.desktop.control` in ROLE_PERMISSIONS."""
    ws = _FakeWS()
    device_seam, user_seam = _gate(_as_user(role))

    with device_seam, user_seam:
        result = await ws_security.enforce_ws_desktop_auth(ws)

    assert result is not None, f"{role} holds desktop.control and must be admitted"
    assert ws.closed_with is None


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["user", "editor", "analyst", "readonly"])
async def test_an_ordinary_signed_in_account_is_refused(role: str) -> None:
    """The defect: each of these was admitted with full view AND input.

    `user`, `editor` and `analyst` hold `mcp.desktop.read` and NOT `.control`.
    Read is not enough here — the RFB stream carries input on the same socket,
    so admitting on `read` would be a view-only grant that is not view-only.
    """
    ws = _FakeWS()
    device_seam, user_seam = _gate(_as_user(role))

    with device_seam, user_seam:
        result = await ws_security.enforce_ws_desktop_auth(ws)

    assert result is None, f"{role} must not reach the desktop"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["user", "readonly"])
async def test_a_refused_caller_is_closed_before_any_rfb_byte(role: str) -> None:
    """Refusal happens in the handshake, not after `accept()`.

    The route calls this before touching the RFB socket, so returning None with
    the handshake closed is what "no frames are proxied" means here.
    """
    ws = _FakeWS()
    device_seam, user_seam = _gate(_as_user(role))

    with device_seam, user_seam:
        await ws_security.enforce_ws_desktop_auth(ws)

    assert ws.closed_with is not None, "the handshake must be closed, not merely unauthorised"
    code, reason = ws.closed_with
    assert code == 1008
    assert "desktop" in reason.lower()


# ---------------------------------------------------------------------------
# The paired-device path must be unaffected (#15146)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_paired_device_that_passed_the_capability_gate_is_still_admitted() -> None:
    """A device credential is judged on its grant set, not on a user role.

    Without this, the fix would close the desktop to the very callers #15146
    built it for — the shape of "a fix that breaks the feature it protects".
    """
    ws = _FakeWS()
    device_user = {"device_id": "dev-1", "username": "paired-device"}
    granted = type("_D", (), {"granted": True, "describe": lambda self: "ok"})()

    with (
        patch.object(ws_security, "_resolve_ws_device_credential", AsyncMock(return_value=device_user)),
        patch("services.device_capabilities.evaluate_device_capabilities", AsyncMock(return_value=granted)),
    ):
        result = await ws_security.enforce_ws_desktop_auth(ws)

    assert result == device_user
    assert ws.closed_with is None


@pytest.mark.asyncio
async def test_an_unauthenticated_handshake_is_still_refused() -> None:
    """The pre-existing behaviour, asserted so the new gate cannot become the
    only thing standing between an anonymous caller and the desktop."""
    ws = _FakeWS()
    device_seam, user_seam = _gate(None)

    with device_seam, user_seam:
        result = await ws_security.enforce_ws_desktop_auth(ws)

    assert result is None


# ---------------------------------------------------------------------------
# The permission table this gate reads, asserted rather than assumed
# ---------------------------------------------------------------------------


def test_the_gate_reads_the_canonical_permission_source() -> None:
    """`role_has_permission`, not `is_admin_role`.

    #13854 removed the administrative short-circuit from `role_has_permission`
    because it made a predicate the most permissive permission source in the
    system. Re-adding it at this call site would reverse that ruling one file at
    a time, so the gate asks the table.
    """
    assert role_has_permission(Role.ADMIN, Permission.MCP_DESKTOP_CONTROL) is True
    assert role_has_permission(Role.OPERATOR, Permission.MCP_DESKTOP_CONTROL) is True
    assert role_has_permission(Role.USER, Permission.MCP_DESKTOP_CONTROL) is False


def test_superadmin_is_refused_and_that_is_the_tables_answer_not_this_gates() -> None:
    """Documented consequence, asserted so it cannot change unnoticed.

    `ROLE_PERMISSIONS[Role.SUPERADMIN]` is empty by the #13854 decision, so a
    superadmin does not hold `mcp.desktop.control` and this gate refuses it. If
    that is wrong, the fix is to give superadmin its ROLE_PERMISSIONS entries --
    one place, asserted here -- and NOT a bypass in the gate.
    """
    assert ROLE_PERMISSIONS.get(Role.SUPERADMIN) == []
    assert role_has_permission(Role.SUPERADMIN, Permission.MCP_DESKTOP_CONTROL) is False


@pytest.mark.asyncio
async def test_a_superadmin_handshake_is_refused_today() -> None:
    """The behaviour that follows from the table, stated at the socket.

    Paired with the test above: one asserts the table's answer, this asserts the
    socket honours it. If superadmin gains the permission, this flips and the
    pair still describes the system truthfully.
    """
    ws = _FakeWS()
    device_seam, user_seam = _gate(_as_user("superadmin"))

    with device_seam, user_seam:
        result = await ws_security.enforce_ws_desktop_auth(ws)

    assert result is None
