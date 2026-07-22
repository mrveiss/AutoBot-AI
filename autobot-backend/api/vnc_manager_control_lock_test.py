# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for api.vnc_manager's desktop control-lock gating (#12002, #11506 T1).

Verifies that agent actuation entrypoints (click/type/key/scroll/drag) are
muted (no xdotool dispatch) while a human holds the control-lock, and
execute normally when the lock is unheld.
"""

from unittest.mock import AsyncMock, patch

import pytest

from api.schemas_system import (
    KeyboardTypeRequest,
    MouseClickRequest,
    MouseDragRequest,
    MouseScrollRequest,
    SpecialKeyRequest,
)
from api.vnc_manager import (
    vnc_keyboard_type,
    vnc_mouse_click,
    vnc_mouse_drag,
    vnc_mouse_scroll,
    vnc_special_key,
)


def _human_active(active: bool):
    """Patch api.vnc_manager.is_human_active for the module under test."""
    return patch("api.vnc_manager.is_human_active", new=AsyncMock(return_value=active))


class TestMouseClickGating:
    @pytest.mark.asyncio
    async def test_muted_when_human_active(self):
        with _human_active(True), patch("api.vnc_manager._run_xdotool_cmd") as mock_run:
            result = await vnc_mouse_click(MouseClickRequest(x=10, y=20), admin_check=True)

        assert result["status"] == "muted"
        assert result["muted"] is True
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_when_human_inactive(self):
        with (
            _human_active(False),
            patch(
                "api.vnc_manager._run_xdotool_cmd", return_value={"status": "success", "message": "Action completed"}
            ) as mock_run,
        ):
            result = await vnc_mouse_click(MouseClickRequest(x=10, y=20), admin_check=True)

        assert result["status"] == "success"
        mock_run.assert_called_once()


class TestKeyboardTypeGating:
    @pytest.mark.asyncio
    async def test_muted_when_human_active(self):
        with _human_active(True), patch("api.vnc_manager._run_xdotool_cmd") as mock_run:
            result = await vnc_keyboard_type(KeyboardTypeRequest(text="hello"), admin_check=True)

        assert result["status"] == "muted"
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_when_human_inactive(self):
        # should_add_human_pause() is stochastic (20% chance of a mid-typing
        # pause that splits into 2 xdotool calls) -- pin it False so this
        # test deterministically exercises the single-call path.
        with (
            _human_active(False),
            patch("api.vnc_manager.should_add_human_pause", return_value=False),
            patch(
                "api.vnc_manager._run_xdotool_cmd", return_value={"status": "success", "message": "Action completed"}
            ) as mock_run,
        ):
            result = await vnc_keyboard_type(KeyboardTypeRequest(text="hello"), admin_check=True)

        assert result["status"] == "success"
        mock_run.assert_called_once()


class TestSpecialKeyGating:
    @pytest.mark.asyncio
    async def test_muted_when_human_active(self):
        with _human_active(True), patch("api.vnc_manager._run_xdotool_cmd") as mock_run:
            result = await vnc_special_key(SpecialKeyRequest(key="Return"), admin_check=True)

        assert result["status"] == "muted"
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_when_human_inactive(self):
        with (
            _human_active(False),
            patch(
                "api.vnc_manager._run_xdotool_cmd", return_value={"status": "success", "message": "Action completed"}
            ) as mock_run,
        ):
            result = await vnc_special_key(SpecialKeyRequest(key="Return"), admin_check=True)

        assert result["status"] == "success"
        mock_run.assert_called_once()


class TestMouseScrollGating:
    @pytest.mark.asyncio
    async def test_muted_when_human_active(self):
        with _human_active(True), patch("api.vnc_manager._run_xdotool_cmd") as mock_run:
            result = await vnc_mouse_scroll(MouseScrollRequest(direction="up"), admin_check=True)

        assert result["status"] == "muted"
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_when_human_inactive(self):
        with (
            _human_active(False),
            patch(
                "api.vnc_manager._run_xdotool_cmd", return_value={"status": "success", "message": "Action completed"}
            ) as mock_run,
        ):
            result = await vnc_mouse_scroll(MouseScrollRequest(direction="up"), admin_check=True)

        assert result["status"] == "success"
        mock_run.assert_called_once()


class TestMouseDragGating:
    @pytest.mark.asyncio
    async def test_muted_when_human_active(self):
        with _human_active(True), patch("api.vnc_manager._run_xdotool_cmd") as mock_run:
            result = await vnc_mouse_drag(MouseDragRequest(x1=0, y1=0, x2=10, y2=10), admin_check=True)

        assert result["status"] == "muted"
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_when_human_inactive(self):
        with (
            _human_active(False),
            patch(
                "api.vnc_manager._run_xdotool_cmd", return_value={"status": "success", "message": "Action completed"}
            ) as mock_run,
        ):
            result = await vnc_mouse_drag(MouseDragRequest(x1=0, y1=0, x2=10, y2=10), admin_check=True)

        assert result["status"] == "success"
        # mousedown + N mousemove points + mouseup
        assert mock_run.call_count >= 2


class TestSessionIdThreading:
    @pytest.mark.asyncio
    async def test_gating_checks_the_requested_session_id(self):
        """is_human_active must be called with the request's session_id, not a default."""
        with patch("api.vnc_manager.is_human_active", new=AsyncMock(return_value=True)) as mock_active:
            await vnc_mouse_click(MouseClickRequest(x=1, y=1, session_id="chat-42"), admin_check=True)

        mock_active.assert_called_once_with("chat-42")
