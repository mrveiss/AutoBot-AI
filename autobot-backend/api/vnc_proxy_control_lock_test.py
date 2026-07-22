# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for api.vnc_proxy's desktop control-lock endpoints (#12002, #11506 T1).

Covers the human takeover/handback REST endpoints (acquire/release/status)
and the best-effort audit hook, without requiring a live Redis or PostgreSQL.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.schemas_system import DesktopControlAcquireRequest, DesktopControlReleaseRequest
from api.vnc_proxy import (
    acquire_desktop_control,
    get_desktop_control_status,
    release_desktop_control,
)


class TestAcquireEndpoint:
    @pytest.mark.asyncio
    async def test_acquire_success(self):
        fake_result = {
            "success": True,
            "owner": "alice",
            "human_active": True,
            "message": "Control acquired by alice",
        }
        with patch(
            "api.vnc_proxy.acquire_human_control", new=AsyncMock(return_value=fake_result)
        ), patch("api.vnc_proxy._audit_control_lock_change", new=AsyncMock()) as mock_audit:
            response = await acquire_desktop_control(
                "desktop",
                DesktopControlAcquireRequest(session_id="default"),
                current_user={"username": "alice", "user_id": None},
            )

        assert response["success"] is True
        assert response["owner"] == "alice"
        assert response["human_active"] is True
        mock_audit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_acquire_unknown_vnc_type_404(self):
        with pytest.raises(HTTPException) as exc_info:
            await acquire_desktop_control(
                "not-a-real-type",
                DesktopControlAcquireRequest(),
                current_user={"username": "alice"},
            )
        assert exc_info.value.status_code == 404


class TestReleaseEndpoint:
    @pytest.mark.asyncio
    async def test_release_success(self):
        fake_result = {
            "success": True,
            "owner": None,
            "human_active": False,
            "message": "Control released",
        }
        with patch(
            "api.vnc_proxy.release_human_control", new=AsyncMock(return_value=fake_result)
        ), patch("api.vnc_proxy._audit_control_lock_change", new=AsyncMock()):
            response = await release_desktop_control(
                "desktop",
                DesktopControlReleaseRequest(session_id="default"),
                current_user={"username": "alice", "user_id": None},
            )

        assert response["success"] is True
        assert response["human_active"] is False

    @pytest.mark.asyncio
    async def test_release_denied_for_non_owner(self):
        fake_result = {
            "success": False,
            "owner": "alice",
            "human_active": True,
            "message": "Control lock is held by another user",
        }
        with patch(
            "api.vnc_proxy.release_human_control", new=AsyncMock(return_value=fake_result)
        ), patch("api.vnc_proxy._audit_control_lock_change", new=AsyncMock()):
            response = await release_desktop_control(
                "desktop",
                DesktopControlReleaseRequest(),
                current_user={"username": "bob"},
            )

        assert response["success"] is False
        assert response["owner"] == "alice"


class TestStatusEndpoint:
    @pytest.mark.asyncio
    async def test_status_reports_owner(self):
        fake_state = {
            "session_id": "default",
            "human_active": True,
            "owner": "alice",
            "acquired_at": "2026-07-22T00:00:00+00:00",
            "redis_available": True,
        }
        with patch("api.vnc_proxy.get_control_lock_state", new=AsyncMock(return_value=fake_state)):
            response = await get_desktop_control_status(
                "desktop", session_id="default", current_user={"username": "bob"}
            )

        assert response["human_active"] is True
        assert response["owner"] == "alice"

    @pytest.mark.asyncio
    async def test_status_unknown_vnc_type_404(self):
        with pytest.raises(HTTPException) as exc_info:
            await get_desktop_control_status("bogus", current_user={"username": "bob"})
        assert exc_info.value.status_code == 404


class TestAuditBestEffort:
    """Audit logging must never block the safety-critical lock operation.

    _audit_control_lock_change() internally catches both RuntimeError (e.g.
    PostgreSQL disabled in single_user mode) and any other exception, so it
    never propagates out to acquire_desktop_control/release_desktop_control.
    """

    @pytest.mark.asyncio
    async def test_acquire_succeeds_even_when_audit_hook_itself_would_fail(self):
        """Acquire succeeds using the REAL (unmocked) audit helper, which is
        expected to no-op cleanly here (no user_id on the caller)."""
        fake_result = {
            "success": True,
            "owner": "alice",
            "human_active": True,
            "message": "Control acquired by alice",
        }
        with patch("api.vnc_proxy.acquire_human_control", new=AsyncMock(return_value=fake_result)):
            response = await acquire_desktop_control(
                "desktop",
                DesktopControlAcquireRequest(),
                current_user={"username": "alice"},  # no user_id -- audit no-ops
            )

        assert response["success"] is True

    @pytest.mark.asyncio
    async def test_audit_skips_cleanly_without_user_id(self):
        from api.vnc_proxy import _audit_control_lock_change

        # No exception raised -- best-effort, no-op when user_id is absent.
        await _audit_control_lock_change("control_lock_acquire", "default", {"username": "alice"})

    @pytest.mark.asyncio
    async def test_audit_skips_cleanly_when_postgres_disabled(self):
        from api.vnc_proxy import _audit_control_lock_change

        with patch(
            "user_management.database.get_async_session_factory",
            side_effect=RuntimeError("PostgreSQL is not enabled for deployment mode: single_user"),
        ):
            # No exception raised -- RuntimeError from PG-disabled mode is swallowed.
            await _audit_control_lock_change(
                "control_lock_acquire",
                "default",
                {"username": "alice", "user_id": "12345678-1234-1234-1234-123456789012"},
            )
