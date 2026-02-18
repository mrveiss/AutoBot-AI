# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
GUI Automation Task Handlers

Issue #322: Refactored to use TaskExecutionContext to eliminate data clump pattern.
"""

import logging
from typing import Any, Dict

from backend.models.task_context import TaskExecutionContext

from .base import TaskHandler

logger = logging.getLogger(__name__)


class GUIClickElementHandler(TaskHandler):
    """Handler for gui_click_element tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute GUI element click and log the audit result."""
        image_path = ctx.require_payload_value("image_path")
        confidence = ctx.get_payload_value("confidence", 0.9)
        button = ctx.get_payload_value("button", "left")
        clicks = ctx.get_payload_value("clicks", 1)
        interval = ctx.get_payload_value("interval", 0.0)

        result = ctx.worker.gui_controller.click_element(
            image_path, confidence, button, clicks, interval
        )

        ctx.audit_log(
            "gui_click_element",
            result.get("status", "unknown"),
            {"image_path": image_path},
        )

        return result


class GUIReadTextFromRegionHandler(TaskHandler):
    """Handler for gui_read_text_from_region tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute OCR text extraction from region and log the audit result."""
        x = ctx.require_payload_value("x")
        y = ctx.require_payload_value("y")
        width = ctx.require_payload_value("width")
        height = ctx.require_payload_value("height")

        result = ctx.worker.gui_controller.read_text_from_region(x, y, width, height)

        ctx.audit_log(
            "gui_read_text_from_region",
            result.get("status", "unknown"),
            {"region": f"({x},{y},{width},{height})"},
        )

        return result


class GUITypeTextHandler(TaskHandler):
    """Handler for gui_type_text tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute keyboard text input and log the audit result."""
        text = ctx.require_payload_value("text")
        interval = ctx.get_payload_value("interval", 0.0)

        result = ctx.worker.gui_controller.type_text(text, interval)

        ctx.audit_log(
            "gui_type_text",
            result.get("status", "unknown"),
            {"text_preview": text[:50]},
        )

        return result


class GUIMoveMouseHandler(TaskHandler):
    """Handler for gui_move_mouse tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute mouse movement and log the audit result."""
        x = ctx.require_payload_value("x")
        y = ctx.require_payload_value("y")
        duration = ctx.get_payload_value("duration", 0.0)

        result = ctx.worker.gui_controller.move_mouse(x, y, duration)

        ctx.audit_log(
            "gui_move_mouse",
            result.get("status", "unknown"),
            {"coords": f"({x},{y})"},
        )

        return result


class GUIBringWindowToFrontHandler(TaskHandler):
    """Handler for gui_bring_window_to_front tasks"""

    async def execute(self, ctx: TaskExecutionContext) -> Dict[str, Any]:
        """Execute window focus operation and log the audit result."""
        app_title = ctx.require_payload_value("app_title")

        result = ctx.worker.gui_controller.bring_window_to_front(app_title)

        ctx.audit_log(
            "gui_bring_window_to_front",
            result.get("status", "unknown"),
            {"app_title": app_title},
        )

        return result
