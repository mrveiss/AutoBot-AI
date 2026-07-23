# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for GUI tools in tools/tool_registry.py.

Issue #12070: gui_read_text_from_region (OCR) and gui_move_mouse have
registered TaskHandlers (task_handlers/gui_handlers.py) but ToolRegistry
never created tasks of those types, making the handlers unreachable from
the agent side. Verifies task-creation wiring now exists for both, and
that they are registered consistently with the 3 pre-existing GUI tools
(get_available_tools + dispatch table).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# get_available_tools — catalogue registration
# ---------------------------------------------------------------------------


def test_get_available_tools_includes_all_five_gui_tools() -> None:
    """All 5 GUI tools appear in get_available_tools (Issue #12070)."""
    with (
        patch("tools.tool_registry.ToolRegistry.__init__", return_value=None),
        patch("chat_workflow.tool_handler.BROWSER_TOOL_NAMES", frozenset()),
    ):
        from tools.tool_registry import ToolRegistry

        registry = ToolRegistry.__new__(ToolRegistry)
        tools = registry.get_available_tools()

    assert "type_text" in tools
    assert "click_element" in tools
    assert "bring_window_to_front" in tools
    assert "read_text_from_region" in tools
    assert "move_mouse" in tools


# ---------------------------------------------------------------------------
# Dispatch table — normalized name lookup
# ---------------------------------------------------------------------------


def test_dispatch_readtextfromregion_resolves() -> None:
    """Normalized 'readtextfromregion' resolves to read_text_from_region handler."""
    with patch("tools.tool_registry.ToolRegistry.__init__", return_value=None):
        from tools.tool_registry import ToolRegistry

        registry = ToolRegistry.__new__(ToolRegistry)
        handler = registry._get_tool_handler("readtextfromregion")

    assert handler is not None


def test_dispatch_movemouse_resolves() -> None:
    """Normalized 'movemouse' resolves to move_mouse handler."""
    with patch("tools.tool_registry.ToolRegistry.__init__", return_value=None):
        from tools.tool_registry import ToolRegistry

        registry = ToolRegistry.__new__(ToolRegistry)
        handler = registry._get_tool_handler("movemouse")

    assert handler is not None


# ---------------------------------------------------------------------------
# Task-creation wiring — previously-missing surface (Issue #12070)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_text_from_region_creates_gui_task_and_reaches_worker() -> None:
    """read_text_from_region() now creates a 'gui_read_text_from_region' task."""
    with patch("tools.tool_registry.ToolRegistry.__init__", return_value=None):
        from tools.tool_registry import ToolRegistry

        registry = ToolRegistry.__new__(ToolRegistry)
        registry.logger = MagicMock()
        registry.worker_node = MagicMock()
        registry.worker_node.execute_task = AsyncMock(return_value={"status": "success", "text": "hi"})

    result = await registry.read_text_from_region(1, 2, 10, 20)

    submitted_task = registry.worker_node.execute_task.call_args[0][0]
    assert submitted_task["type"] == "gui_read_text_from_region"
    assert submitted_task["x"] == 1
    assert submitted_task["y"] == 2
    assert submitted_task["width"] == 10
    assert submitted_task["height"] == 20
    assert result["status"] == "success"
    assert result["result"] == "hi"


@pytest.mark.asyncio
async def test_move_mouse_creates_gui_task_and_reaches_worker() -> None:
    """move_mouse() now creates a 'gui_move_mouse' task."""
    with patch("tools.tool_registry.ToolRegistry.__init__", return_value=None):
        from tools.tool_registry import ToolRegistry

        registry = ToolRegistry.__new__(ToolRegistry)
        registry.logger = MagicMock()
        registry.worker_node = MagicMock()
        registry.worker_node.execute_task = AsyncMock(return_value={"status": "success", "message": "moved"})

    result = await registry.move_mouse(5, 6, duration=0.5)

    submitted_task = registry.worker_node.execute_task.call_args[0][0]
    assert submitted_task["type"] == "gui_move_mouse"
    assert submitted_task["x"] == 5
    assert submitted_task["y"] == 6
    assert submitted_task["duration"] == 0.5
    assert result["status"] == "success"


# ---------------------------------------------------------------------------
# Regression: bring_window_to_front payload key must match handler contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bring_window_to_front_task_uses_app_title_key() -> None:
    """Task payload key must be 'app_title' — GUIBringWindowToFrontHandler
    (task_handlers/gui_handlers.py) requires that key, not 'window_title'.
    Discovered alongside Issue #12070's task-creation audit.
    """
    with patch("tools.tool_registry.ToolRegistry.__init__", return_value=None):
        from tools.tool_registry import ToolRegistry

        registry = ToolRegistry.__new__(ToolRegistry)
        registry.logger = MagicMock()
        registry.worker_node = MagicMock()
        registry.worker_node.execute_task = AsyncMock(return_value={"status": "success"})

    await registry.bring_window_to_front("Terminal")

    submitted_task = registry.worker_node.execute_task.call_args[0][0]
    assert submitted_task["app_title"] == "Terminal"
    assert "window_title" not in submitted_task
