import pyautogui
import time
from PIL import Image
import os
import asyncio

class GUIController:
    def __init__(self):
        """Initialize the GUIController with safety settings and virtual display if needed."""
        pyautogui.FAILSAFE = True  # Enable failsafe to stop script by moving mouse to upper-left corner
        pyautogui.PAUSE = 0.5  # Add a small pause after each PyAutoGUI call for safety
        self.screen_width, self.screen_height = pyautogui.size()
        self.virtual_display = False
        # Check if running under Xvfb or need virtual display
        if 'DISPLAY' not in os.environ:
            self.virtual_display = True
            # Note: Xvfb setup would be done externally or via system call if needed
            print("Warning: DISPLAY environment variable not set. GUI automation may not work without Xvfb.")

    async def capture_screen(self):
        """Capture a screenshot of the current screen."""
        try:
            return await asyncio.to_thread(pyautogui.screenshot)
        except Exception as e:
            print(f"Error capturing screenshot: {e}")
            return None

    async def click_at(self, x, y):
        """Simulate a mouse click at the specified coordinates."""
        try:
            await asyncio.to_thread(pyautogui.click, x, y)
            print(f"Clicked at ({x}, {y})")
        except Exception as e:
            print(f"Error clicking at ({x}, {y}): {e}")

    async def type_text(self, text):
        """Simulate typing the specified text."""
        try:
            await asyncio.to_thread(pyautogui.write, text)
            print(f"Typed text: {text}")
        except Exception as e:
            print(f"Error typing text: {e}")

    async def locate_element_by_image(self, image_path, confidence=0.8):
        """Locate an element on the screen by matching an image."""
        try:
            location = await asyncio.to_thread(pyautogui.locateCenterOnScreen, image_path, confidence=confidence)
            if location:
                print(f"Found element at {location}")
                return location
            else:
                print(f"Element not found for image: {image_path}")
                return None
        except Exception as e:
            print(f"Error locating element by image {image_path}: {e}")
            return None

    async def draw_visual_feedback(self, x, y, duration=2):
        """Draw visual feedback at the specified location (optional, for debugging)."""
        try:
            # Simulate visual feedback by moving mouse to location and back
            original_pos = await asyncio.to_thread(pyautogui.position)
            await asyncio.to_thread(pyautogui.moveTo, x, y)
            await asyncio.sleep(duration)
            await asyncio.to_thread(pyautogui.moveTo, original_pos)
            print(f"Drew visual feedback at ({x}, {y})")
        except Exception as e:
            print(f"Error drawing visual feedback: {e}")

    def check_wsl2_kex(self):
        """Check if running under WSL2 and if Kex is available."""
        if 'WSL_DISTRO_NAME' in os.environ:
            print("Detected WSL2 environment.")
            try:
                import subprocess
                result = subprocess.run(['which', 'kex'], capture_output=True, text=True)
                if result.stdout.strip():
                    print("Kex is available. If GUI fails, consider starting a Kex session.")
                    return True
                else:
                    print("Kex not found. GUI automation may fail without a VNC session.")
                    return False
            except Exception as e:
                print(f"Error checking for Kex: {e}")
                return False
        return False

async def main():
    # Test the GUIController
    controller = GUIController()
    if controller.virtual_display:
        print("Running without DISPLAY. GUI operations may be limited.")
    else:
        # Test screenshot
        screenshot = await controller.capture_screen()
        if screenshot:
            screenshot.save("test_screenshot.png")
            print("Screenshot saved as test_screenshot.png")
        
        # Test locating an element (requires an image file to match)
        # location = await controller.locate_element_by_image("sample_element.png")
        # if location:
        #     await controller.click_at(location.x, location.y)
        #     await controller.draw_visual_feedback(location.x, location.y)
        
        # Test typing
        await controller.type_text("Hello, AutoBot!")
        
        # Check WSL2 and Kex
        controller.check_wsl2_kex()

if __name__ == "__main__":
    asyncio.run(main())
