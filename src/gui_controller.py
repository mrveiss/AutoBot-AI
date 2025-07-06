# src/gui_controller.py
import pyautogui
import pygetwindow as gw
from PIL import Image
import pytesseract
import cv2
import numpy as np
import os
import time
from typing import Tuple, List, Dict, Any, Optional

class GUIController:
    def __init__(self):
        # Ensure Tesseract is in PATH or specify its path
        # pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract' # Example for Linux
        # pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe' # Example for Windows
        pass

    def _screenshot(self, region: Optional[Tuple[int, int, int, int]] = None) -> Image.Image:
        """Takes a screenshot of the entire screen or a specified region."""
        if region:
            return pyautogui.screenshot(region=region)
        else:
            return pyautogui.screenshot()

    def click_element(self, image_path: str, confidence: float = 0.9, button: str = 'left', clicks: int = 1, interval: float = 0.0) -> Dict[str, Any]:
        """
        Locates an element on the screen using an image template and clicks it.
        
        Args:
            image_path (str): Path to the image file of the element to find.
            confidence (float): Confidence level for image recognition (0.0 to 1.0).
            button (str): Mouse button to click ('left', 'right', 'middle').
            clicks (int): Number of clicks.
            interval (float): Interval between clicks.
            
        Returns:
            Dict[str, Any]: Status and message.
        """
        try:
            # Load the template image
            template = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
            if template is None:
                return {"status": "error", "message": f"Failed to load template image: {image_path}"}

            # Take a screenshot of the current screen
            screenshot_pil = self._screenshot()
            screenshot_cv = cv2.cvtColor(np.array(screenshot_pil), cv2.COLOR_RGB2BGR)

            # Perform template matching
            res = cv2.matchTemplate(screenshot_cv, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            if max_val >= confidence:
                # Get the top-left corner of the matched region
                top_left = max_loc
                h, w = template.shape[0], template.shape[1]
                center_x = top_left[0] + w // 2
                center_y = top_left[1] + h // 2

                pyautogui.click(x=center_x, y=center_y, button=button, clicks=clicks, interval=interval)
                return {"status": "success", "message": f"Clicked element at ({center_x}, {center_y}) with confidence {max_val:.2f}."}
            else:
                return {"status": "error", "message": f"Element not found on screen with confidence {confidence}. Max confidence: {max_val:.2f}"}
        except Exception as e:
            return {"status": "error", "message": f"Error clicking element: {e}"}

    def read_text_from_region(self, x: int, y: int, width: int, height: int) -> Dict[str, Any]:
        """
        Performs OCR on a specified screen region to read text.
        
        Args:
            x (int): X-coordinate of the top-left corner.
            y (int): Y-coordinate of the top-left corner.
            width (int): Width of the region.
            height (int): Height of the region.
            
        Returns:
            Dict[str, Any]: Status, message, and extracted text.
        """
        try:
            region = (x, y, width, height)
            screenshot_region = self._screenshot(region=region)
            text = pytesseract.image_to_string(screenshot_region)
            return {"status": "success", "message": "Text extracted successfully.", "text": text.strip()}
        except Exception as e:
            return {"status": "error", "message": f"Error reading text from region: {e}"}

    def type_text(self, text: str, interval: float = 0.0) -> Dict[str, Any]:
        """
        Types a given string of text.
        
        Args:
            text (str): The text to type.
            interval (float): Interval between key presses.
            
        Returns:
            Dict[str, Any]: Status and message.
        """
        try:
            pyautogui.write(text, interval=interval)
            return {"status": "success", "message": f"Typed text: '{text}'"}
        except Exception as e:
            return {"status": "error", "message": f"Error typing text: {e}"}

    def move_mouse(self, x: int, y: int, duration: float = 0.0) -> Dict[str, Any]:
        """
        Moves the mouse to the specified coordinates.
        
        Args:
            x (int): X-coordinate.
            y (int): Y-coordinate.
            duration (float): Duration of the mouse movement in seconds.
            
        Returns:
            Dict[str, Any]: Status and message.
        """
        try:
            pyautogui.moveTo(x, y, duration=duration)
            return {"status": "success", "message": f"Mouse moved to ({x}, {y})."}
        except Exception as e:
            return {"status": "error", "message": f"Error moving mouse: {e}"}

    def bring_window_to_front(self, app_title: str) -> Dict[str, Any]:
        """
        Identifies a window by its title and brings it to the front.
        
        Args:
            app_title (str): Partial or full title of the application window.
            
        Returns:
            Dict[str, Any]: Status and message.
        """
        try:
            windows = gw.getWindowsWithTitle(app_title)
            if windows:
                # Prioritize visible windows
                visible_windows = [win for win in windows if win.isMinimized == False and win.isVisible == True]
                if visible_windows:
                    target_window = visible_windows[0]
                else:
                    target_window = windows[0] # Fallback to any window with title

                if target_window.isMinimized:
                    target_window.restore()
                target_window.activate()
                return {"status": "success", "message": f"Window '{app_title}' brought to front."}
            else:
                return {"status": "error", "message": f"No window found with title containing '{app_title}'."}
        except Exception as e:
            return {"status": "error", "message": f"Error bringing window to front: {e}"}

# Example Usage (for testing)
if __name__ == "__main__":
    # Note: GUI automation requires a display environment.
    # On Linux, ensure you are running in an X server session (e.g., via VNC or directly on desktop).
    # For testing, you might need to uncomment and set tesseract_cmd path.
    # For click_element, you'd need a sample image file (e.g., a screenshot of a button).

    gui_controller = GUIController()

    print("--- Testing move_mouse and type_text ---")
    # Move mouse to a known location (e.g., top-left of screen) and type
    # pyautogui.FAILSAFE = False # Disable failsafe for testing, be careful!
    # try:
    #     print(gui_controller.move_mouse(100, 100, duration=1))
    #     time.sleep(1)
    #     print(gui_controller.type_text("Hello, AutoBot!", interval=0.1))
    # except Exception as e:
    #     print(f"Test failed: {e}")

    print("\n--- Testing bring_window_to_front (e.g., 'Terminal' or 'Firefox') ---")
    # You might need to open a terminal or browser window manually first
    # print(gui_controller.bring_window_to_front("Terminal"))
    # time.sleep(2)
    # print(gui_controller.bring_window_to_front("Firefox"))

    print("\n--- Testing read_text_from_region (requires Tesseract OCR installed) ---")
    # Take a screenshot of a small region and try to read text
    # You might need to adjust coordinates and size based on your screen content
    # try:
    #     # Example: Read text from a region where you expect some text
    #     result = gui_controller.read_text_from_region(0, 0, 500, 100)
    #     print(result)
    # except Exception as e:
    #     print(f"Test failed: {e}")

    print("\n--- Testing click_element (requires a template image) ---")
    # Create a dummy image file for testing
    # cv2.imwrite("dummy_button.png", np.zeros((50, 100, 3), dtype=np.uint8))
    # try:
    #     # This will likely fail unless you have a matching image on screen
    #     result = gui_controller.click_element("dummy_button.png", confidence=0.8)
    #     print(result)
    # finally:
    #     if os.path.exists("dummy_button.png"):
    #         os.remove("dummy_button.png")
