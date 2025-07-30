# src/gui_controller_dummy.py
import os
from typing import Tuple, List, Dict, Any, Optional
import asyncio

class GUIController:
    """
    A dummy GUIController for environments where actual GUI automation is not supported or desired.
    All methods will return a success status indicating the action was "skipped".
    """
    def __init__(self):
        print("WARNING: Initializing Dummy GUIController. GUI automation features will be skipped.")
        pass

    async def _screenshot(self, region: Optional[Tuple[int, int, int, int]] = None) -> Any:
        print("Dummy GUIController: _screenshot skipped.")
        await asyncio.sleep(0)
        # Return a dummy image or None, depending on how it's used downstream
        return None 

    async def click_element(self, image_path: str, confidence: float = 0.9, button: str = 'left', clicks: int = 1, interval: float = 0.0) -> Dict[str, Any]:
        print(f"Dummy GUIController: click_element('{image_path}') skipped.")
        await asyncio.sleep(0)
        return {"status": "success", "message": "GUI click skipped (Dummy Controller)."}

    async def read_text_from_region(self, x: int, y: int, width: int, height: int) -> Dict[str, Any]:
        print(f"Dummy GUIController: read_text_from_region({x}, {y}, {width}, {height}) skipped.")
        await asyncio.sleep(0)
        return {"status": "success", "message": "GUI text read skipped (Dummy Controller).", "text": ""}

    async def type_text(self, text: str, interval: float = 0.0) -> Dict[str, Any]:
        print(f"Dummy GUIController: type_text('{text}') skipped.")
        await asyncio.sleep(0)
        return {"status": "success", "message": "GUI text type skipped (Dummy Controller)."}

    async def move_mouse(self, x: int, y: int, duration: float = 0.0) -> Dict[str, Any]:
        print(f"Dummy GUIController: move_mouse({x}, {y}) skipped.")
        await asyncio.sleep(0)
        return {"status": "success", "message": "GUI mouse move skipped (Dummy Controller)."}

    async def bring_window_to_front(self, app_title: str) -> Dict[str, Any]:
        print(f"Dummy GUIController: bring_window_to_front('{app_title}') skipped.")
        await asyncio.sleep(0)
        return {"status": "success", "message": "GUI window bring to front skipped (Dummy Controller)."}
