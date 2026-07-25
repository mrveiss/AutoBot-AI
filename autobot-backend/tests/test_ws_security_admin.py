# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the shared admin WebSocket auth helpers (#12178).

``authenticate_ws_admin`` / ``enforce_ws_admin`` gate admin-only WS endpoints
(``/ws/monitoring``, ``/ws/desktop``) with the same fail-closed auth+authz the
REST siblings enforce via ``Depends(check_admin_permission)``. Before #12178
those two sockets did Origin validation only — an authenticated non-admin (or,
with a permissive Origin, any caller) could open them.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.ws_security import authenticate_ws_admin, enforce_ws_admin


def _ws(headers=None):
    return SimpleNamespace(headers=headers or {})


def test_authenticate_ws_admin_denies_unauthenticated():
    with (
        patch.dict("os.environ", {"AUTOBOT_REQUIRE_WS_AUTH": "1"}),
        patch("auth_middleware.get_auth_middleware") as gam,
        patch("auth_middleware.verify_internal_api_key", return_value=False),
    ):
        gam.return_value.get_user_from_request.return_value = None
        assert authenticate_ws_admin(_ws()) is False


def test_authenticate_ws_admin_denies_non_admin():
    with (
        patch.dict("os.environ", {"AUTOBOT_REQUIRE_WS_AUTH": "1"}),
        patch("auth_middleware.get_auth_middleware") as gam,
        patch("auth_middleware.verify_internal_api_key", return_value=False),
    ):
        gam.return_value.get_user_from_request.return_value = {"role": "user"}
        assert authenticate_ws_admin(_ws()) is False


def test_authenticate_ws_admin_allows_admin_and_internal_key():
    with (
        patch.dict("os.environ", {"AUTOBOT_REQUIRE_WS_AUTH": "1"}),
        patch("auth_middleware.get_auth_middleware") as gam,
        patch("auth_middleware.verify_internal_api_key", side_effect=lambda key: key == "k"),
    ):
        gam.return_value.get_user_from_request.return_value = {"role": "admin"}
        assert authenticate_ws_admin(_ws()) is True
        assert authenticate_ws_admin(_ws({"X-Internal-API-Key": "k"})) is True


def test_authenticate_ws_admin_dev_bypass_when_disabled():
    with patch.dict("os.environ", {"AUTOBOT_REQUIRE_WS_AUTH": "0"}):
        assert authenticate_ws_admin(_ws()) is True


def test_authenticate_ws_admin_fail_closed_on_error():
    """Any exception in the auth path denies (never leaks an open socket)."""
    with (
        patch.dict("os.environ", {"AUTOBOT_REQUIRE_WS_AUTH": "1"}),
        patch("auth_middleware.verify_internal_api_key", side_effect=RuntimeError("boom")),
    ):
        assert authenticate_ws_admin(_ws()) is False


@pytest.mark.asyncio
async def test_enforce_ws_admin_accepts_then_closes_4001_when_denied():
    """#12366: rejection accepts the handshake before closing so the client
    receives a real close frame (code + reason), not an HTTP 403."""
    ws = SimpleNamespace(headers={}, accept=AsyncMock(), close=AsyncMock())
    with (
        patch.dict("os.environ", {"AUTOBOT_REQUIRE_WS_AUTH": "1"}),
        patch("auth_middleware.get_auth_middleware") as gam,
        patch("auth_middleware.verify_internal_api_key", return_value=False),
    ):
        gam.return_value.get_user_from_request.return_value = {"role": "user"}
        assert await enforce_ws_admin(ws) is False
    ws.accept.assert_awaited_once()
    ws.close.assert_awaited_once()
    assert ws.close.await_args.kwargs.get("code") == 4001


@pytest.mark.asyncio
async def test_enforce_ws_admin_allows_admin_without_closing():
    ws = SimpleNamespace(headers={}, accept=AsyncMock(), close=AsyncMock())
    with patch.dict("os.environ", {"AUTOBOT_REQUIRE_WS_AUTH": "0"}):
        assert await enforce_ws_admin(ws) is True
    ws.close.assert_not_awaited()
