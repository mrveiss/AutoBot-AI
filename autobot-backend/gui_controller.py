# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
GUI automation controller via pyautogui.

Wraps platform mouse/keyboard automation for tasks that require desktop
interaction, with configurable safety settings and fail-safes.
"""

import asyncio
import os
import subprocess
from typing import Any, Dict

import pyautogui

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from autobot_shared.network_constants import NetworkConstants
from autobot_shared.ssot_config import config
from constants.threshold_constants import TimingConstants

logger = get_logger(__name__)

# Issue #11579: Canonical desktop-control display, shared with
# api/vnc_manager.py + api/vnc_mcp.py (xdotool/x11vnc/noVNC). GUIController
# used to start its OWN private ``Xvfb :99``, invisible to the human
# observer who watches the display owned by vnc_manager. It now attaches to
# this single, shared display instead. See NetworkConstants.DESKTOP_DISPLAY
# for the env-driven single source of truth (AUTOBOT_DESKTOP_DISPLAY).
CANONICAL_DISPLAY = NetworkConstants.DESKTOP_DISPLAY


class GUIController:
    def __init__(self):
        """Initialize the GUIController with safety settings, attached to
        the canonical (human-observed) desktop display.
        """
        # Enable failsafe to stop script by moving mouse to upper-left corner
        pyautogui.FAILSAFE = True
        # Add a small pause after each PyAutoGUI call for safety
        pyautogui.PAUSE = 0.5
        self.virtual_display = False
        self.xvfb_process = None
        # Issue #11579: always attach to the canonical display rather than
        # only reacting to a missing DISPLAY env var — this guarantees
        # convergence even if some other DISPLAY was inherited from the
        # environment. Never starts a second/competing X server here; the
        # canonical display's X server is owned by
        # api.vnc_manager.start_vnc_server() (Issue #74).
        self.attach_to_canonical_display()
        self.screen_width, self.screen_height = pyautogui.size()

    def __del__(self):
        """Destructor to clean up resources."""
        self.stop_virtual_display()

    def attach_to_canonical_display(self):
        """Point pyautogui at the canonical (human-observed) desktop display.

        Issue #11579: previously started a private ``Xvfb :99`` here, which
        drove a screen the human operator could never see (#11506 audit).
        This method only ATTACHES to the shared display; it does not spawn
        Xvfb/Xtigervnc. The X server for the canonical display is owned and
        started by api.vnc_manager.start_vnc_server().

        #11506 T1 (control-lock) will hook in here — the agent (this
        controller) and the human (noVNC on the same display) need to
        arbitrate simultaneous input on this shared display. Not implemented
        in this change; scope is display convergence only.
        """
        os.environ["DISPLAY"] = CANONICAL_DISPLAY
        config.display = CANONICAL_DISPLAY
        self.virtual_display = True
        if self._is_canonical_display_active():
            logger.info("GUIController attached to canonical display %s", CANONICAL_DISPLAY)
        else:
            logger.warning(
                "Canonical desktop display %s is not active yet. GUI "
                "automation will fail until the VNC/X server owning it is "
                "started (see api.vnc_manager.start_vnc_server).",
                CANONICAL_DISPLAY,
            )

    def _is_canonical_display_active(self) -> bool:
        """Check whether an X server is already listening on the canonical display."""
        try:
            result = subprocess.run(  # nosec B603 B607 - fixed argv, no user input
                ["pgrep", "-f", f"Xtigervnc {CANONICAL_DISPLAY}"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception as e:
            logger.debug("Could not probe canonical display %s: %s", CANONICAL_DISPLAY, e)
            return False

    def start_virtual_display(self):
        """Deprecated alias, retained for backward compatibility.

        Issue #11579: no longer starts a private Xvfb on :99 — attaches to
        the canonical (human-observed) display instead. See
        attach_to_canonical_display().
        """
        self.attach_to_canonical_display()

    def stop_virtual_display(self):
        """Clean up controller-owned resources.

        Issue #11579: GUIController no longer owns the canonical display's X
        server process (api.vnc_manager does), so there is nothing to
        terminate here beyond any legacy Xvfb handle.
        """
        if self.xvfb_process:
            self.xvfb_process.terminate()
            self.xvfb_process = None
            logger.info("Virtual display stopped")

    async def capture_screen(self):
        """Capture a screenshot of the current screen."""
        try:
            return await asyncio.to_thread(pyautogui.screenshot)
        except Exception as e:
            logger.error("Error capturing screenshot: %s", e)
            return None

    async def read_text_from_region(self, x: int, y: int, width: int, height: int) -> Dict[str, Any]:
        """OCR-read text from a region of the canonical desktop display.

        Issue #11579: this capability (task type ``gui_read_text_from_region``,
        see task_handlers/gui_handlers.py) has no xdotool/vnc_manager
        equivalent that plugs into ``ctx.worker.gui_controller`` today, so it
        is preserved here unchanged except for the display it now targets —
        the canonical, human-observed display instead of the retired
        ``:99`` Xvfb. Uses the same pytesseract dependency as
        api.vnc_manager's ``/ocr`` endpoint (Issue #74 Area 5).
        """
        try:
            import pytesseract
        except ImportError:
            logger.error("pytesseract not installed; cannot read text from region")
            return {
                "status": "error",
                "message": "pytesseract not installed. Run: pip install pytesseract pillow",
                "text": "",
            }

        try:
            screenshot = await asyncio.to_thread(pyautogui.screenshot, region=(x, y, width, height))
            text = await asyncio.to_thread(pytesseract.image_to_string, screenshot)
            logger.debug("Read text from region (%s,%s,%s,%s)", x, y, width, height)
            return {
                "status": "success",
                "message": "GUI text read completed",
                "text": text.strip(),
            }
        except Exception as e:
            logger.error("Error reading text from region (%s,%s,%s,%s): %s", x, y, width, height, e)
            return {"status": "error", "message": "Operation failed", "text": ""}

    async def click_at(self, x, y):
        """Simulate a mouse click at the specified coordinates."""
        try:
            await asyncio.to_thread(pyautogui.click, x, y)
            logger.debug("Clicked at (%s, %s)", x, y)
        except Exception as e:
            logger.error("Error clicking at (%s, %s): %s", x, y, e)

    async def type_text(self, text):
        """Simulate typing the specified text."""
        try:
            await asyncio.to_thread(pyautogui.write, text)
            logger.debug("Typed text: %s", text)
        except Exception as e:
            logger.error("Error typing text: %s", e)

    async def locate_element_by_image(self, image_path, confidence=0.8):
        """Locate an element on the screen by matching an image."""
        try:
            location = await asyncio.to_thread(pyautogui.locateCenterOnScreen, image_path, confidence=confidence)
            if location:
                logger.debug("Found element at %s", location)
                return location
            else:
                logger.debug("Element not found for image: %s", image_path)
                return None
        except Exception as e:
            logger.error("Error locating element by image %s: %s", image_path, e)
            return None

    async def draw_visual_feedback(self, x, y, duration=2):
        """Draw visual feedback at the specified location (optional, for debugging)."""
        try:
            # Simulate visual feedback by moving mouse to location and back
            original_pos = await asyncio.to_thread(pyautogui.position)
            await asyncio.to_thread(pyautogui.moveTo, x, y)
            await asyncio.sleep(duration)
            await asyncio.to_thread(pyautogui.moveTo, original_pos)
            logger.debug("Drew visual feedback at (%s, %s)", x, y)
        except Exception as e:
            logger.error("Error drawing visual feedback: %s", e)

    def check_wsl2_kex(self):
        """Check if running under WSL2 and if Kex is available."""
        if "WSL_DISTRO_NAME" in os.environ:
            logger.info("Detected WSL2 environment")
            try:
                import subprocess

                result = subprocess.run(
                    ["which", "kex"], capture_output=True, text=True
                )  # nosec B603 B607 - fixed argv, probing kex availability
                if result.stdout.strip():
                    logger.info("Kex is available. If GUI fails, consider starting " "a Kex session.")
                    return True
                else:
                    logger.warning("Kex not found. GUI automation may fail without " "a VNC session.")
                    return False
            except Exception as e:
                logger.error("Error checking for Kex: %s", e)
                return False
        return False


async def main():
    """Test function for GUIController with screenshot and click operations."""
    # Test the GUIController
    controller = GUIController()
    if controller.virtual_display:
        logger.debug(
            "%s",
            "Running in virtual display. GUI operations will be performed in the background.",
        )
        # Give Xvfb a moment to start
        await asyncio.sleep(TimingConstants.SERVICE_STARTUP_DELAY)

    # Test screenshot
    screenshot = await controller.capture_screen()
    if screenshot:
        screenshot.save("test_screenshot.png")
        logger.debug("Screenshot saved as test_screenshot.png")

    # Test locating an element (requires an image file to match)
    # location = await controller.locate_element_by_image("sample_element.png")
    # if location:
    #     await controller.click_at(location.x, location.y)
    #     await controller.draw_visual_feedback(location.x, location.y)

    # Test typing
    await controller.type_text("Hello, AutoBot!")

    # Check WSL2 and Kex
    controller.check_wsl2_kex()

    # Clean up
    controller.stop_virtual_display()


if __name__ == "__main__":
    run_or_schedule(main())
