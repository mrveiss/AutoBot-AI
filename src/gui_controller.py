# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import asyncio
import logging
import os
import subprocess

import pyautogui

logger = logging.getLogger(__name__)


class GUIController:
    def __init__(self):
        """Initialize the GUIController with safety settings and virtual
        display if needed.
        """
        # Enable failsafe to stop script by moving mouse to upper-left corner
        pyautogui.FAILSAFE = True
        # Add a small pause after each PyAutoGUI call for safety
        pyautogui.PAUSE = 0.5
        self.screen_width, self.screen_height = pyautogui.size()
        self.virtual_display = False
        self.xvfb_process = None
        # Check if running under Xvfb or need virtual display
        if "DISPLAY" not in os.environ:
            self.virtual_display = True
            logger.warning(
                "DISPLAY environment variable not set. "
                "Attempting to start virtual display."
            )
            self.start_virtual_display()

    def __del__(self):
        """Destructor to clean up resources."""
        self.stop_virtual_display()

    def start_virtual_display(self):
        """Start Xvfb virtual display if not already running."""
        try:
            # Check if Xvfb is installed
            if subprocess.run(["which", "Xvfb"], capture_output=True).returncode != 0:
                logger.error(
                    "Xvfb is not installed. Please install it to use the virtual display."
                )
                return

            # Start Xvfb
            self.xvfb_process = subprocess.Popen(
                ["Xvfb", ":99", "-screen", "0", "1280x1024x24"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            os.environ["DISPLAY"] = ":99"
            logger.info("Virtual display started on :99")
        except Exception as e:
            logger.error("Error starting virtual display: %s", e)

    def stop_virtual_display(self):
        """Stop the Xvfb virtual display if it was started by this controller."""
        if self.xvfb_process:
            self.xvfb_process.terminate()
            self.xvfb_process = None
            if "DISPLAY" in os.environ:
                del os.environ["DISPLAY"]
            logger.info("Virtual display stopped")

    async def capture_screen(self):
        """Capture a screenshot of the current screen."""
        try:
            return await asyncio.to_thread(pyautogui.screenshot)
        except Exception as e:
            logger.error("Error capturing screenshot: %s", e)
            return None

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
            location = await asyncio.to_thread(
                pyautogui.locateCenterOnScreen, image_path, confidence=confidence
            )
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
                )
                if result.stdout.strip():
                    logger.info(
                        "Kex is available. If GUI fails, consider starting "
                        "a Kex session."
                    )
                    return True
                else:
                    logger.warning(
                        "Kex not found. GUI automation may fail without "
                        "a VNC session."
                    )
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
        await asyncio.sleep(2)

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
    asyncio.run(main())
