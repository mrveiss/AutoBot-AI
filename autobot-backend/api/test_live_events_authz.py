# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Authorization tests for tenant-scoped LLC live-event channels (#11386).

`company:` and `board:` channels carry per-company data, so subscription must be
gated on company membership. These tests exercise `_authorize_llc_channel`.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.live_events import _authorize_llc_channel


@asynccontextmanager
async def _fake_session_cm():
    yield AsyncMock()


def _patch_session():
    factory = MagicMock(return_value=_fake_session_cm())
    return patch("user_management.database.get_async_session_factory", MagicMock(return_value=factory))


@pytest.mark.asyncio
async def test_admin_bypasses_membership() -> None:
    assert await _authorize_llc_channel("company:c1", {"roles": ["admin"], "user_id": "u1"}) is True


@pytest.mark.asyncio
async def test_missing_user_denied() -> None:
    assert await _authorize_llc_channel("company:c1", {"roles": []}) is False


@pytest.mark.asyncio
async def test_empty_ident_denied() -> None:
    assert await _authorize_llc_channel("company:", {"user_id": "u1"}) is False


@pytest.mark.asyncio
async def test_company_member_allowed() -> None:
    svc = MagicMock()
    svc.is_member = AsyncMock(return_value=True)
    with _patch_session(), patch("llc.services.membership_service.MembershipService", MagicMock(return_value=svc)):
        assert await _authorize_llc_channel("company:c1", {"user_id": "u1", "roles": []}) is True
    svc.is_member.assert_awaited_once()


@pytest.mark.asyncio
async def test_company_non_member_denied() -> None:
    svc = MagicMock()
    svc.is_member = AsyncMock(return_value=False)
    with _patch_session(), patch("llc.services.membership_service.MembershipService", MagicMock(return_value=svc)):
        assert await _authorize_llc_channel("company:other", {"user_id": "u1", "roles": []}) is False


@pytest.mark.asyncio
async def test_board_resolves_company_then_checks_membership() -> None:
    membership = MagicMock()
    membership.is_member = AsyncMock(return_value=True)
    board = MagicMock(company_id="c-owner")
    board_svc = MagicMock()
    board_svc.get_board = AsyncMock(return_value=board)
    with (
        _patch_session(),
        patch("llc.services.membership_service.MembershipService", MagicMock(return_value=membership)),
        patch("llc.services.board.BoardService", MagicMock(return_value=board_svc)),
    ):
        assert await _authorize_llc_channel("board:b1", {"user_id": "u1", "roles": []}) is True
    board_svc.get_board.assert_awaited_once()
    # membership checked against the board's owning company, not the board id
    assert membership.is_member.call_args[0][1] == "c-owner"


@pytest.mark.asyncio
async def test_board_not_found_denied() -> None:
    board_svc = MagicMock()
    board_svc.get_board = AsyncMock(return_value=None)
    with _patch_session(), patch("llc.services.board.BoardService", MagicMock(return_value=board_svc)):
        assert await _authorize_llc_channel("board:missing", {"user_id": "u1", "roles": []}) is False


@pytest.mark.asyncio
async def test_fails_closed_on_error() -> None:
    with patch("user_management.database.get_async_session_factory", MagicMock(side_effect=RuntimeError("db down"))):
        assert await _authorize_llc_channel("company:c1", {"user_id": "u1", "roles": []}) is False


# ---------------------------------------------------------------------------
# #11396 — per-resource authorization for workflow:/heartbeat:/task: channels
# ---------------------------------------------------------------------------

from api.live_events import _authorize_resource_channel  # noqa: E402


@pytest.mark.asyncio
async def test_resource_admin_bypasses() -> None:
    for ch in ("workflow:w1", "heartbeat:h1", "task:t1"):
        assert await _authorize_resource_channel(ch, {"roles": ["admin"], "user_id": "u1"}) is True


@pytest.mark.asyncio
async def test_resource_missing_user_denied() -> None:
    assert await _authorize_resource_channel("workflow:w1", {"roles": []}) is False


@pytest.mark.asyncio
async def test_resource_empty_ident_denied() -> None:
    assert await _authorize_resource_channel("workflow:", {"user_id": "u1", "roles": []}) is False


@pytest.mark.asyncio
async def test_task_channel_denied_for_non_admin() -> None:
    """No task ownership store exists — non-admins are denied fail-closed (#11396)."""
    assert await _authorize_resource_channel("task:any-id", {"user_id": "u1", "roles": []}) is False


@pytest.mark.asyncio
async def test_workflow_permission_holder_allowed() -> None:
    svc = MagicMock()
    svc.check_permission = AsyncMock(return_value=True)
    with (
        _patch_session(),
        patch("api.live_events.WorkflowPermissionService", MagicMock(return_value=svc)),
    ):
        assert await _authorize_resource_channel("workflow:w1", {"user_id": "u1", "roles": []}) is True
    # checked with the "view" action against the claimed workflow id
    assert svc.check_permission.call_args[0] == ("u1", "w1", "view")


@pytest.mark.asyncio
async def test_workflow_without_permission_denied() -> None:
    svc = MagicMock()
    svc.check_permission = AsyncMock(return_value=False)
    with (
        _patch_session(),
        patch("api.live_events.WorkflowPermissionService", MagicMock(return_value=svc)),
    ):
        assert await _authorize_resource_channel("workflow:other", {"user_id": "u1", "roles": []}) is False


@pytest.mark.asyncio
async def test_heartbeat_member_of_owning_company_allowed() -> None:
    membership = MagicMock()
    membership.is_member = AsyncMock(return_value=True)
    run = MagicMock(company_id="c-owner")
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=run)))

    @asynccontextmanager
    async def _session_cm():
        yield session

    factory = MagicMock(return_value=_session_cm())
    with (
        patch("user_management.database.get_async_session_factory", MagicMock(return_value=factory)),
        patch("llc.services.membership_service.MembershipService", MagicMock(return_value=membership)),
    ):
        assert await _authorize_resource_channel("heartbeat:h1", {"user_id": "u1", "roles": []}) is True
    # membership checked against the run's owning company
    assert membership.is_member.call_args[0][1] == "c-owner"


@pytest.mark.asyncio
async def test_heartbeat_run_not_found_denied() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    @asynccontextmanager
    async def _session_cm():
        yield session

    factory = MagicMock(return_value=_session_cm())
    with patch("user_management.database.get_async_session_factory", MagicMock(return_value=factory)):
        assert await _authorize_resource_channel("heartbeat:missing", {"user_id": "u1", "roles": []}) is False


@pytest.mark.asyncio
async def test_resource_fails_closed_on_error() -> None:
    with patch("user_management.database.get_async_session_factory", MagicMock(side_effect=RuntimeError("db down"))):
        assert await _authorize_resource_channel("workflow:w1", {"user_id": "u1", "roles": []}) is False
