# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Test suite for GUI task handlers (#11579 code-review follow-up).

Regression coverage for a real bug found in review: every handler called its
GUIController's ``async def`` method WITHOUT awaiting it, then called
``.get()`` on the resulting coroutine object — raising AttributeError on
every real invocation (the coroutine was never actually run). Verifies each
handler now awaits the controller call and returns the resolved dict.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from models.task_context import TaskExecutionContext
from task_handlers.gui_handlers import (
    GUIBringWindowToFrontHandler,
    GUIClickElementHandler,
    GUIMoveMouseHandler,
    GUIReadTextFromRegionHandler,
    GUITypeTextHandler,
)


def _make_ctx(payload: dict) -> TaskExecutionContext:
    worker = MagicMock()
    worker.gui_controller = MagicMock()
    worker.security_layer = MagicMock()
    return TaskExecutionContext(
        worker=worker,
        task_payload=payload,
        user_role="admin",
        task_id="test-task",
    )


class TestGUIHandlersAwaitControllerCalls:
    """Each handler must await its (async) GUIController method call."""

    @pytest.mark.asyncio
    async def test_click_element_awaits_and_returns_result(self):
        ctx = _make_ctx({"image_path": "btn.png"})
        ctx.worker.gui_controller.click_element = AsyncMock(return_value={"status": "success"})

        result = await GUIClickElementHandler().execute(ctx)

        ctx.worker.gui_controller.click_element.assert_awaited_once()
        assert result == {"status": "success"}

    @pytest.mark.asyncio
    async def test_read_text_from_region_awaits_and_returns_result(self):
        ctx = _make_ctx({"x": 1, "y": 2, "width": 10, "height": 20})
        ctx.worker.gui_controller.read_text_from_region = AsyncMock(return_value={"status": "success", "text": "hi"})

        result = await GUIReadTextFromRegionHandler().execute(ctx)

        ctx.worker.gui_controller.read_text_from_region.assert_awaited_once_with(1, 2, 10, 20)
        assert result == {"status": "success", "text": "hi"}

    @pytest.mark.asyncio
    async def test_type_text_awaits_and_returns_result(self):
        ctx = _make_ctx({"text": "hello"})
        ctx.worker.gui_controller.type_text = AsyncMock(return_value={"status": "success"})

        result = await GUITypeTextHandler().execute(ctx)

        ctx.worker.gui_controller.type_text.assert_awaited_once()
        assert result == {"status": "success"}

    @pytest.mark.asyncio
    async def test_move_mouse_awaits_and_returns_result(self):
        ctx = _make_ctx({"x": 5, "y": 6})
        ctx.worker.gui_controller.move_mouse = AsyncMock(return_value={"status": "success"})

        result = await GUIMoveMouseHandler().execute(ctx)

        ctx.worker.gui_controller.move_mouse.assert_awaited_once()
        assert result == {"status": "success"}

    @pytest.mark.asyncio
    async def test_bring_window_to_front_awaits_and_returns_result(self):
        ctx = _make_ctx({"app_title": "Terminal"})
        ctx.worker.gui_controller.bring_window_to_front = AsyncMock(return_value={"status": "success"})

        result = await GUIBringWindowToFrontHandler().execute(ctx)

        ctx.worker.gui_controller.bring_window_to_front.assert_awaited_once()
        assert result == {"status": "success"}
