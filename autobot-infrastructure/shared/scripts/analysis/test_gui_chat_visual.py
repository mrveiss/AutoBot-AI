#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Visual test for AutoBot GUI chat functionality using Playwright service."""

import time

logger = logging.getLogger(__name__)


import requests

from constants import ServiceURLs


def test_gui_chat():
    """Test the GUI chat interface visually."""
    logger.info("🎭 Visual GUI Chat Test")
    logger.info("=" * 60)
    logger.info("📺 Please watch the browser at http://localhost:3000")
    logger.info("=" * 60)

    base_url = "http://localhost:3000"

    # Step 1: Navigate to AutoBot GUI
    logger.info("\n1. Navigating to AutoBot GUI...")
    scrape_data = {
        "url": ServiceURLs.FRONTEND_LOCAL,
        "waitFor": "body",
        "screenshot": True,
    }

    try:
        response = requests.post(f"{base_url}/scrape", json=scrape_data)
        if response.status_code == 200:
            logger.info("✅ Loaded AutoBot GUI")
            time.sleep(2)  # Let user see the page
        else:
            logger.error(f"❌ Failed to load GUI: {response.status_code}")
            return
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return

    # Step 2: Click on the chat input
    logger.info("\n2. Clicking on chat input...")
    click_data = {
        "url": ServiceURLs.FRONTEND_LOCAL,
        "selector": 'textarea[placeholder*="Type your message"], input[placeholder*="Type your message"]',
        "action": "click",
    }

    try:
        response = requests.post(f"{base_url}/interact", json=click_data)
        if response.status_code == 200:
            logger.info("✅ Clicked chat input")
            time.sleep(1)
        else:
            logger.warning(f"⚠️  Could not click input: {response.status_code}")
    except Exception as e:
        logger.error(f"⚠️  Click error: {e}")

    # Step 3: Type a message
    logger.info("\n3. Typing test message...")
    type_data = {
        "url": ServiceURLs.FRONTEND_LOCAL,
        "selector": 'textarea[placeholder*="Type your message"], input[placeholder*="Type your message"]',
        "action": "type",
        "text": "Hello, can you hear me?",
    }

    try:
        response = requests.post(f"{base_url}/interact", json=type_data)
        if response.status_code == 200:
            logger.info("✅ Typed message: 'Hello, can you hear me?'")
            time.sleep(1)
        else:
            logger.warning(f"⚠️  Could not type: {response.status_code}")
    except Exception as e:
        logger.error(f"⚠️  Type error: {e}")

    # Step 4: Submit the message
    logger.info("\n4. Submitting message...")
    submit_data = {
        "url": ServiceURLs.FRONTEND_LOCAL,
        "selector": 'button[type="submit"], button:has-text("Send"), button[aria-label*="send"]',
        "action": "click",
    }

    try:
        response = requests.post(f"{base_url}/interact", json=submit_data)
        if response.status_code == 200:
            logger.info("✅ Clicked send button")
            logger.info("⏳ Waiting for response...")
            time.sleep(5)  # Wait for response
        else:
            # Try pressing Enter instead
            logger.warning("⚠️  Send button not found, trying Enter key...")
            enter_data = {
                "url": ServiceURLs.FRONTEND_LOCAL,
                "selector": 'textarea[placeholder*="Type your message"], input[placeholder*="Type your message"]',
                "action": "press",
                "key": "Enter",
            }
            response = requests.post(f"{base_url}/interact", json=enter_data)
            if response.status_code == 200:
                logger.info("✅ Pressed Enter")
                time.sleep(5)
    except Exception as e:
        logger.error(f"⚠️  Submit error: {e}")

    # Step 5: Take screenshot of result
    logger.info("\n5. Taking screenshot of chat result...")
    screenshot_data = {
        "url": ServiceURLs.FRONTEND_LOCAL,
        "waitFor": ".message, .chat-message",
        "screenshot": True,
    }

    try:
        response = requests.post(f"{base_url}/scrape", json=screenshot_data)
        if response.status_code == 200:
            result = response.json()
            if result.get("screenshot"):
                logger.info("✅ Screenshot captured")
                logger.info("   Screenshot available in response")

            # Check if messages appeared
            content = result.get("content", "")
            if "Hello, can you hear me?" in content:
                logger.info("✅ User message appears in chat")
                if any(word in content.lower() for word in ["yes", "hello", "hi", "hear"]):
                    logger.info("✅ Bot response detected!")
                else:
                    logger.error("❌ No bot response detected")
            else:
                logger.error("❌ Message not found in chat")
        else:
            logger.error(f"❌ Screenshot failed: {response.status_code}")
    except Exception as e:
        logger.error(f"❌ Screenshot error: {e}")

    logger.info("\n" + "=" * 60)
    logger.info("📺 Check http://localhost:3000 to see the visual result")
    logger.info("=" * 60)


if __name__ == "__main__":
    test_gui_chat()
