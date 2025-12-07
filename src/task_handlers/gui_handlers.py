# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
GUI Automation Task Handlers
"""

import logging
from typing import TYPE_CHECKING, Any, Dict

from .base import TaskHandler

if TYPE_CHECKING:
    from src.worker_node import WorkerNode

logger = logging.getLogger(__name__)


class GUIClickElementHandler(TaskHandler):
    """Handler for gui_click_element tasks"""

    async def execute(
        self,
        worker: "WorkerNode",
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        """Execute GUI element click and log the audit result."""
        image_path = task_payload["image_path"]
        confidence = task_payload.get("confidence", 0.9)
        button = task_payload.get("button", "left")
        clicks = task_payload.get("clicks", 1)
        interval = task_payload.get("interval", 0.0)

        result = worker.gui_controller.click_element(
            image_path, confidence, button, clicks, interval
        )

        worker.security_layer.audit_log(
            "gui_click_element",
            user_role,
            result.get("status", "unknown"),
            {"task_id": task_id, "image_path": image_path},
        )

        return result


class GUIReadTextFromRegionHandler(TaskHandler):
    """Handler for gui_read_text_from_region tasks"""

    async def execute(
        self,
        worker: "WorkerNode",
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        """Execute OCR text extraction from region and log the audit result."""
        x = task_payload["x"]
        y = task_payload["y"]
        width = task_payload["width"]
        height = task_payload["height"]

        result = worker.gui_controller.read_text_from_region(x, y, width, height)

        worker.security_layer.audit_log(
            "gui_read_text_from_region",
            user_role,
            result.get("status", "unknown"),
            {"task_id": task_id, "region": f"({x},{y},{width},{height})"},
        )

        return result


class GUITypeTextHandler(TaskHandler):
    """Handler for gui_type_text tasks"""

    async def execute(
        self,
        worker: "WorkerNode",
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        """Execute keyboard text input and log the audit result."""
        text = task_payload["text"]
        interval = task_payload.get("interval", 0.0)

        result = worker.gui_controller.type_text(text, interval)

        worker.security_layer.audit_log(
            "gui_type_text",
            user_role,
            result.get("status", "unknown"),
            {"task_id": task_id, "text_preview": text[:50]},
        )

        return result


class GUIMoveMouseHandler(TaskHandler):
    """Handler for gui_move_mouse tasks"""

    async def execute(
        self,
        worker: "WorkerNode",
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        """Execute mouse movement and log the audit result."""
        x = task_payload["x"]
        y = task_payload["y"]
        duration = task_payload.get("duration", 0.0)

        result = worker.gui_controller.move_mouse(x, y, duration)

        worker.security_layer.audit_log(
            "gui_move_mouse",
            user_role,
            result.get("status", "unknown"),
            {"task_id": task_id, "coords": f"({x},{y})"},
        )

        return result


class GUIBringWindowToFrontHandler(TaskHandler):
    """Handler for gui_bring_window_to_front tasks"""

    async def execute(
        self,
        worker: "WorkerNode",
        task_payload: Dict[str, Any],
        user_role: str,
        task_id: str,
    ) -> Dict[str, Any]:
        """Execute window focus operation and log the audit result."""
        app_title = task_payload["app_title"]

        result = worker.gui_controller.bring_window_to_front(app_title)

        worker.security_layer.audit_log(
            "gui_bring_window_to_front",
            user_role,
            result.get("status", "unknown"),
            {"task_id": task_id, "app_title": app_title},
        )

        return result
