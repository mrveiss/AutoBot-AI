# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
# src/gui_controller_dummy.py
import asyncio
import logging
from typing import Any, Dict, Optional, Tuple


logger = logging.getLogger(__name__)


class GUIController:
    """
    A dummy GUIController for environments where actual GUI automation
    is not supported or desired. All methods will return a success status
    indicating the action was "skipped".
    """

    def __init__(self):
        """Initialize dummy GUI controller for non-GUI environments."""
        logger.info(
            "Initializing Dummy GUIController for Linux environment. "
            "GUI automation features will be skipped."
        )

    async def _screenshot(
        self, region: Optional[Tuple[int, int, int, int]] = None
    ) -> Any:
        """Return None as screenshot is not supported in dummy controller."""
        logger.debug("Dummy GUIController: _screenshot skipped.")
        await asyncio.sleep(0)
        # Return a dummy image or None, depending on downstream usage
        return None

    async def click_element(
        self,
        image_path: str,
        confidence: float = 0.9,
        button: str = "left",
        clicks: int = 1,
        interval: float = 0.0,
    ) -> Dict[str, Any]:
        """Return success status without performing click in dummy mode."""
        logger.debug("Dummy GUIController: click_element('%s') skipped.", image_path)
        await asyncio.sleep(0)
        return {"status": "success", "message": "GUI click skipped (Dummy Controller)."}

    async def read_text_from_region(
        self, x: int, y: int, width: int, height: int
    ) -> Dict[str, Any]:
        """Return empty text as OCR is not supported in dummy mode."""
        logger.debug(
            "Dummy GUIController: read_text_from_region("
            f"{x}, {y}, {width}, {height}) skipped."
        )
        await asyncio.sleep(0)
        return {
            "status": "success",
            "message": "GUI text read skipped (Dummy Controller).",
            "text": "",
        }

    async def type_text(self, text: str, interval: float = 0.0) -> Dict[str, Any]:
        """Return success status without typing text in dummy mode."""
        logger.debug("Dummy GUIController: type_text('%s') skipped.", text)
        await asyncio.sleep(0)
        return {
            "status": "success",
            "message": "GUI text type skipped (Dummy Controller).",
        }

    async def move_mouse(self, x: int, y: int, duration: float = 0.0) -> Dict[str, Any]:
        """Return success status without moving mouse in dummy mode."""
        logger.debug("Dummy GUIController: move_mouse(%s, %s) skipped.", x, y)
        await asyncio.sleep(0)
        return {
            "status": "success",
            "message": "GUI mouse move skipped (Dummy Controller).",
        }

    async def bring_window_to_front(self, app_title: str) -> Dict[str, Any]:
        """Return success status without window management in dummy mode."""
        logger.debug(
            f"Dummy GUIController: bring_window_to_front('{app_title}') skipped."
        )
        await asyncio.sleep(0)
        return {
            "status": "success",
            "message": "GUI window bring to front skipped (Dummy Controller).",
        }
