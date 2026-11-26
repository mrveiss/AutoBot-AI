# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Chat Desktop controls executed on the selected /secrets host over RFB (#22145)."""

import asyncio
import base64
import struct
from typing import Dict, List

from api.vnc_host_target import resolve_vnc_target
from api.vnc_humanization import simulate_mouse_curve
from api.vnc_rfb_client import VncAuthError, VncProtocolError, VncRfbSession, frame_to_png
from autobot_shared.env_utils import env_float_clamped
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Pause between synthesised input events, so a remote server applies them in order.
VNC_INPUT_STEP_DELAY_S = env_float_clamped("AUTOBOT_VNC_INPUT_STEP_DELAY_S", 0.02, 0.0, 5.0, positive_finite=True)

_BUTTON_MASK = {"left": 1, "middle": 2, "right": 4}
_WHEEL_MASK = {"up": 8, "down": 16}
_KEYSYMS = {
    "return": 0xFF0D, "enter": 0xFF0D, "tab": 0xFF09, "escape": 0xFF1B, "esc": 0xFF1B,
    "backspace": 0xFF08, "delete": 0xFFFF, "home": 0xFF50, "left": 0xFF51, "up": 0xFF52,
    "right": 0xFF53, "down": 0xFF54, "page_up": 0xFF55, "page_down": 0xFF56, "end": 0xFF57,
    "insert": 0xFF63, "space": 0x20, "ctrl": 0xFFE3, "control": 0xFFE3, "shift": 0xFFE1,
    "alt": 0xFFE9, "super": 0xFFEB, "meta": 0xFFE7,
}  # fmt: skip
# Control characters in typed text map to their named keys: the raw 0x09 / 0x0A codes are not RFB keysyms.
_TEXT_CONTROL_KEYS = {"\n": "Return", "\t": "Tab"}
_KEYSYM_F1 = 0xFFBE
_KEYSYM_UNICODE = 0x01000000


def keysym_for(name: str) -> int:
    """X11 keysym for a key name such as ``Return``, ``F5`` or ``a``."""
    lowered = name.lower()
    if lowered in _KEYSYMS:
        return _KEYSYMS[lowered]
    if lowered.startswith("f") and lowered[1:].isdigit() and 1 <= int(lowered[1:]) <= 12:
        return _KEYSYM_F1 + int(lowered[1:]) - 1
    if len(name) != 1:
        raise ValueError(f"Unknown key: {name}")
    return ord(name) if ord(name) < 0x100 else _KEYSYM_UNICODE + ord(name)


async def _tap_keys(session: VncRfbSession, keysyms: List[int]) -> None:
    for keysym in keysyms:
        await session.key(keysym, True)
    for keysym in reversed(keysyms):
        await session.key(keysym, False)


async def _click(session: VncRfbSession, x: int, y: int, mask: int) -> None:
    await session.pointer(x, y, 0)
    await session.pointer(x, y, mask)
    await asyncio.sleep(VNC_INPUT_STEP_DELAY_S)
    await session.pointer(x, y, 0)


async def _drag(session: VncRfbSession, x1: int, y1: int, x2: int, y2: int) -> None:
    points = simulate_mouse_curve(x1, y1, x2, y2)
    await session.pointer(x1, y1, 0)
    await session.pointer(x1, y1, _BUTTON_MASK["left"])
    for x, y in points[1:]:
        await session.pointer(x, y, _BUTTON_MASK["left"])
        await asyncio.sleep(VNC_INPUT_STEP_DELAY_S)
    await session.pointer(x2, y2, 0)


async def _scroll(session: VncRfbSession, direction: str, amount: int) -> None:
    mask, x, y = _WHEEL_MASK[direction], session.width // 2, session.height // 2
    await session.pointer(x, y, 0)  # the wheel acts where the pointer is: the screen centre
    for _ in range(amount):
        await session.pointer(x, y, mask)
        await session.pointer(x, y, 0)


async def _type(session: VncRfbSession, text: str) -> None:
    for char in text:
        keysym = keysym_for(_TEXT_CONTROL_KEYS.get(char, char))
        await _tap_keys(session, [keysym])


async def run_on_host(host_id: str, action: str, **params) -> Dict[str, object]:
    """Run one control (*action*) on the selected host; returns the endpoint result dict."""
    target = await resolve_vnc_target(host_id)
    try:
        async with VncRfbSession(target.address, target.port, target.password) as session:
            return await _dispatch(session, action, params)
    except (VncAuthError, VncProtocolError, OSError, asyncio.TimeoutError, struct.error) as exc:
        logger.warning("Desktop %s on host %s failed: %s", action, target.host_id, type(exc).__name__)
        return {"status": "error", "message": f"Could not reach the host's VNC server ({type(exc).__name__})"}
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}


async def _dispatch(session: VncRfbSession, action: str, p: Dict[str, object]) -> Dict[str, object]:
    if action == "click":
        await _click(session, p["x"], p["y"], _BUTTON_MASK.get(p["button"], 1))
    elif action == "type":
        await _type(session, p["text"])
    elif action == "key":
        await _tap_keys(session, [keysym_for(k) for k in str(p["key"]).split("+")])
    elif action == "scroll":
        await _scroll(session, p["direction"], p["amount"])
    elif action == "drag":
        await _drag(session, p["x1"], p["y1"], p["x2"], p["y2"])
    elif action == "clipboard":
        await session.cut_text(p["content"])
    elif action == "screenshot":
        png = frame_to_png(await session.grab_frame())
        return {"status": "success", "message": "Screenshot captured", "image_data": base64.b64encode(png).decode()}
    else:
        raise ValueError(f"Unknown desktop action: {action}")
    return {"status": "success", "message": "Action completed"}
