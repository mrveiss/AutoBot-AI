#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Visual test for AutoBot GUI chat functionality using Playwright service."""

import json
import logging
import time

logger = logging.getLogger(__name__)


import requests

from autobot_shared.network_constants import ServiceURLs
from autobot_shared.ssot_config import config

#: One browser session for every step, so the page the input is typed into is the page that is read.
_SESSION = "gui-chat-visual"
_INPUT = 'textarea[placeholder*="Type your message"], input[placeholder*="Type your message"]'
_SEND = 'button[type="submit"], button:has-text("Send"), button[aria-label*="send"]'
_MESSAGE = "Hello, can you hear me?"


def _automation(base_url: str, action: str, **params) -> dict:
    """One ``POST /automation`` step on the browser worker: the canonical selector-based route (#19490).

    The worker registers no ``/scrape`` or ``/interact``; ``/automation`` carries navigate, click,
    fill, screenshot, evaluate and get_text. Raises on a non-2xx answer or ``success: false``.
    """
    response = requests.post(
        f"{base_url}/automation", json={"action": action, "params": params, "session_id": _SESSION}, timeout=60
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError(payload.get("error", f"{action} failed"))
    return payload.get("result", {})


def _step(label: str, base_url: str, action: str, **params) -> dict | None:
    """Run one step and log its outcome; ``None`` when it failed."""
    try:
        result = _automation(base_url, action, **params)
        logger.info("✅ %s", label)
        return result
    except Exception as e:
        logger.error("❌ %s failed: %s", label, e)
        return None


def _submit(base_url: str) -> None:
    """Click send; if no send button matches, submit the input's form instead."""
    if _step("Clicked send button", base_url, "click", selector=_SEND) is None:
        script = f"document.querySelector({json.dumps(_INPUT)})?.form?.requestSubmit()"
        _step("Submitted the chat form", base_url, "evaluate", script=script)
    logger.info("⏳ Waiting for response...")
    time.sleep(5)


def _check_reply(base_url: str) -> None:
    """Screenshot the chat, then look for the sent message and a reply in the page text."""
    _step("Messages rendered", base_url, "wait_for_selector", selector=".message, .chat-message")
    if _step("Screenshot captured", base_url, "screenshot", full_page=True) is None:
        return
    content = (_step("Read page text", base_url, "get_text", selector="body") or {}).get("text") or ""
    if _MESSAGE not in content:
        logger.error("❌ Message not found in chat")
        return
    reply = content.split(_MESSAGE, 1)[1].lower()  # only text after the sent message can be a reply
    if any(word in reply for word in ["yes", "hello", "hi", "hear"]):
        logger.info("✅ User message appears in chat; bot response detected!")
    else:
        logger.error("❌ User message appears, but no bot response detected")


def test_gui_chat():
    """Test the GUI chat interface visually."""
    logger.info("🎭 Visual GUI Chat Test")
    logger.info("📺 Please watch the browser at %s", ServiceURLs.VNC_LOCAL)
    base_url = f"http://localhost:{config.port.browser}"

    if _step("Loaded AutoBot GUI", base_url, "navigate", url=ServiceURLs.FRONTEND_LOCAL) is None:
        return
    time.sleep(2)  # let the watcher see the page
    _step("Clicked chat input", base_url, "click", selector=_INPUT)
    _step(f"Typed message: {_MESSAGE!r}", base_url, "fill", selector=_INPUT, value=_MESSAGE)
    _submit(base_url)
    _check_reply(base_url)
    logger.info("📺 Check %s to see the visual result", ServiceURLs.FRONTEND_LOCAL)


if __name__ == "__main__":
    test_gui_chat()
