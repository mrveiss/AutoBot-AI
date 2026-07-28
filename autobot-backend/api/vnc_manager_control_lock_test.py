# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for api.vnc_manager's desktop control-lock gating (#12002, #11506 T1).

Verifies that human-facing REST actuation entrypoints (click/type/key/scroll/
drag) are muted (no xdotool dispatch) when a DIFFERENT human holds the
control-lock, execute normally when unheld OR when the caller IS the lock
owner (owner-aware gating), and degrade safely (unconditional gating) when
called without a resolvable current_user (e.g. macro playback's direct
Python calls).
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.params import Depends

from api.schemas_system import (
    KeyboardTypeRequest,
    MouseClickRequest,
    MouseDragRequest,
    MouseScrollRequest,
    SpecialKeyRequest,
)
from api.vnc_manager import (
    _caller_username,
    vnc_keyboard_type,
    vnc_mouse_click,
    vnc_mouse_drag,
    vnc_mouse_scroll,
    vnc_special_key,
)

ALICE = {"username": "alice"}
BOB = {"username": "bob"}


def _muted(active: bool):
    """Patch api.vnc_manager.is_actuation_muted for the module under test."""
    return patch("api.vnc_manager.is_actuation_muted", new=AsyncMock(return_value=active))


class TestMouseClickGating:
    @pytest.mark.asyncio
    async def test_muted_for_non_owner_while_held(self):
        with _muted(True), patch("api.vnc_manager._run_xdotool_cmd") as mock_run:
            result = await vnc_mouse_click(MouseClickRequest(x=10, y=20), admin_check=True, current_user=BOB)

        assert result["status"] == "muted"
        assert result["muted"] is True
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_when_unheld(self):
        with (
            _muted(False),
            patch(
                "api.vnc_manager._run_xdotool_cmd", return_value={"status": "success", "message": "Action completed"}
            ) as mock_run,
        ):
            result = await vnc_mouse_click(MouseClickRequest(x=10, y=20), admin_check=True, current_user=ALICE)

        assert result["status"] == "success"
        mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_executes_for_lock_owner(self):
        """The lock owner's own toolbar must not mute itself (#12002 review fix)."""
        with (
            patch("api.vnc_manager.is_actuation_muted", new=AsyncMock(return_value=False)) as mock_muted,
            patch(
                "api.vnc_manager._run_xdotool_cmd", return_value={"status": "success", "message": "Action completed"}
            ) as mock_run,
        ):
            result = await vnc_mouse_click(MouseClickRequest(x=10, y=20), admin_check=True, current_user=ALICE)

        assert result["status"] == "success"
        mock_run.assert_called_once()
        mock_muted.assert_called_once_with("default", "alice")


class TestKeyboardTypeGating:
    @pytest.mark.asyncio
    async def test_muted_for_non_owner_while_held(self):
        with _muted(True), patch("api.vnc_manager._run_xdotool_cmd") as mock_run:
            result = await vnc_keyboard_type(KeyboardTypeRequest(text="hello"), admin_check=True, current_user=BOB)

        assert result["status"] == "muted"
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_when_unheld(self):
        # should_add_human_pause() is stochastic (20% chance of a mid-typing
        # pause that splits into 2 xdotool calls) -- pin it False so this
        # test deterministically exercises the single-call path.
        with (
            _muted(False),
            patch("api.vnc_manager.should_add_human_pause", return_value=False),
            patch(
                "api.vnc_manager._run_xdotool_cmd", return_value={"status": "success", "message": "Action completed"}
            ) as mock_run,
        ):
            result = await vnc_keyboard_type(KeyboardTypeRequest(text="hello"), admin_check=True, current_user=ALICE)

        assert result["status"] == "success"
        mock_run.assert_called_once()


class TestSpecialKeyGating:
    @pytest.mark.asyncio
    async def test_muted_for_non_owner_while_held(self):
        with _muted(True), patch("api.vnc_manager._run_xdotool_cmd") as mock_run:
            result = await vnc_special_key(SpecialKeyRequest(key="Return"), admin_check=True, current_user=BOB)

        assert result["status"] == "muted"
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_when_unheld(self):
        with (
            _muted(False),
            patch(
                "api.vnc_manager._run_xdotool_cmd", return_value={"status": "success", "message": "Action completed"}
            ) as mock_run,
        ):
            result = await vnc_special_key(SpecialKeyRequest(key="Return"), admin_check=True, current_user=ALICE)

        assert result["status"] == "success"
        mock_run.assert_called_once()


class TestMouseScrollGating:
    @pytest.mark.asyncio
    async def test_muted_for_non_owner_while_held(self):
        with _muted(True), patch("api.vnc_manager._run_xdotool_cmd") as mock_run:
            result = await vnc_mouse_scroll(MouseScrollRequest(direction="up"), admin_check=True, current_user=BOB)

        assert result["status"] == "muted"
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_when_unheld(self):
        with (
            _muted(False),
            patch(
                "api.vnc_manager._run_xdotool_cmd", return_value={"status": "success", "message": "Action completed"}
            ) as mock_run,
        ):
            result = await vnc_mouse_scroll(MouseScrollRequest(direction="up"), admin_check=True, current_user=ALICE)

        assert result["status"] == "success"
        mock_run.assert_called_once()


class TestMouseDragGating:
    @pytest.mark.asyncio
    async def test_muted_for_non_owner_while_held(self):
        with _muted(True), patch("api.vnc_manager._run_xdotool_cmd") as mock_run:
            result = await vnc_mouse_drag(
                MouseDragRequest(x1=0, y1=0, x2=10, y2=10), admin_check=True, current_user=BOB
            )

        assert result["status"] == "muted"
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_when_unheld(self):
        with (
            _muted(False),
            patch(
                "api.vnc_manager._run_xdotool_cmd", return_value={"status": "success", "message": "Action completed"}
            ) as mock_run,
        ):
            result = await vnc_mouse_drag(
                MouseDragRequest(x1=0, y1=0, x2=10, y2=10), admin_check=True, current_user=ALICE
            )

        assert result["status"] == "success"
        # mousedown + N mousemove points + mouseup
        assert mock_run.call_count >= 2


class TestSessionIdThreading:
    @pytest.mark.asyncio
    async def test_gating_checks_the_requested_session_id(self):
        """is_actuation_muted must be called with the request's session_id, not a default."""
        with patch("api.vnc_manager.is_actuation_muted", new=AsyncMock(return_value=True)) as mock_muted:
            await vnc_mouse_click(
                MouseClickRequest(x=1, y=1, session_id="chat-42"), admin_check=True, current_user=ALICE
            )

        mock_muted.assert_called_once_with("chat-42", "alice")


class TestCallerUsernameExtraction:
    """_caller_username must degrade gracefully for non-dict callers (e.g.
    playback_macro()'s direct Python calls, which never resolve the FastAPI
    current_user dependency) instead of raising."""

    def test_extracts_username_from_dict(self):
        assert _caller_username({"username": "alice"}) == "alice"

    def test_dict_without_username_returns_none(self):
        assert _caller_username({"role": "admin"}) is None

    def test_unresolved_depends_sentinel_returns_none(self):
        # Mirrors what `current_user` actually is when playback_macro() calls
        # vnc_mouse_click(...) directly without passing current_user.
        assert _caller_username(Depends(lambda: None)) is None

    def test_none_returns_none(self):
        assert _caller_username(None) is None

    @pytest.mark.asyncio
    async def test_macro_style_direct_call_does_not_crash_and_is_unconditionally_gated(self):
        """Direct call with no current_user (macro playback style) must not
        raise, and must fall back to unconditional gating (caller=None)."""
        with (
            patch("api.vnc_manager.is_actuation_muted", new=AsyncMock(return_value=True)) as mock_muted,
            patch("api.vnc_manager._run_xdotool_cmd") as mock_run,
        ):
            result = await vnc_mouse_click(MouseClickRequest(x=1, y=1), admin_check=True)

        assert result["status"] == "muted"
        mock_run.assert_not_called()
        mock_muted.assert_called_once_with("default", None)
