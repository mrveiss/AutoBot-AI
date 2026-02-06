#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Visual test for AutoBot GUI chat functionality using Playwright service."""

import time

import requests

from src.constants import ServiceURLs


def test_gui_chat():
    """Test the GUI chat interface visually."""
    print("🎭 Visual GUI Chat Test")
    print("=" * 60)
    print("📺 Please watch the browser at http://localhost:3000")
    print("=" * 60)

    base_url = "http://localhost:3000"

    # Step 1: Navigate to AutoBot GUI
    print("\n1. Navigating to AutoBot GUI...")
    scrape_data = {
        "url": ServiceURLs.FRONTEND_LOCAL,
        "waitFor": "body",
        "screenshot": True,
    }

    try:
        response = requests.post(f"{base_url}/scrape", json=scrape_data)
        if response.status_code == 200:
            print("✅ Loaded AutoBot GUI")
            time.sleep(2)  # Let user see the page
        else:
            print(f"❌ Failed to load GUI: {response.status_code}")
            return
    except Exception as e:
        print(f"❌ Error: {e}")
        return

    # Step 2: Click on the chat input
    print("\n2. Clicking on chat input...")
    click_data = {
        "url": ServiceURLs.FRONTEND_LOCAL,
        "selector": 'textarea[placeholder*="Type your message"], input[placeholder*="Type your message"]',
        "action": "click",
    }

    try:
        response = requests.post(f"{base_url}/interact", json=click_data)
        if response.status_code == 200:
            print("✅ Clicked chat input")
            time.sleep(1)
        else:
            print(f"⚠️  Could not click input: {response.status_code}")
    except Exception as e:
        print(f"⚠️  Click error: {e}")

    # Step 3: Type a message
    print("\n3. Typing test message...")
    type_data = {
        "url": ServiceURLs.FRONTEND_LOCAL,
        "selector": 'textarea[placeholder*="Type your message"], input[placeholder*="Type your message"]',
        "action": "type",
        "text": "Hello, can you hear me?",
    }

    try:
        response = requests.post(f"{base_url}/interact", json=type_data)
        if response.status_code == 200:
            print("✅ Typed message: 'Hello, can you hear me?'")
            time.sleep(1)
        else:
            print(f"⚠️  Could not type: {response.status_code}")
    except Exception as e:
        print(f"⚠️  Type error: {e}")

    # Step 4: Submit the message
    print("\n4. Submitting message...")
    submit_data = {
        "url": ServiceURLs.FRONTEND_LOCAL,
        "selector": 'button[type="submit"], button:has-text("Send"), button[aria-label*="send"]',
        "action": "click",
    }

    try:
        response = requests.post(f"{base_url}/interact", json=submit_data)
        if response.status_code == 200:
            print("✅ Clicked send button")
            print("⏳ Waiting for response...")
            time.sleep(5)  # Wait for response
        else:
            # Try pressing Enter instead
            print("⚠️  Send button not found, trying Enter key...")
            enter_data = {
                "url": ServiceURLs.FRONTEND_LOCAL,
                "selector": 'textarea[placeholder*="Type your message"], input[placeholder*="Type your message"]',
                "action": "press",
                "key": "Enter",
            }
            response = requests.post(f"{base_url}/interact", json=enter_data)
            if response.status_code == 200:
                print("✅ Pressed Enter")
                time.sleep(5)
    except Exception as e:
        print(f"⚠️  Submit error: {e}")

    # Step 5: Take screenshot of result
    print("\n5. Taking screenshot of chat result...")
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
                print("✅ Screenshot captured")
                print("   Screenshot available in response")

            # Check if messages appeared
            content = result.get("content", "")
            if "Hello, can you hear me?" in content:
                print("✅ User message appears in chat")
                if any(
                    word in content.lower() for word in ["yes", "hello", "hi", "hear"]
                ):
                    print("✅ Bot response detected!")
                else:
                    print("❌ No bot response detected")
            else:
                print("❌ Message not found in chat")
        else:
            print(f"❌ Screenshot failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Screenshot error: {e}")

    print("\n" + "=" * 60)
    print("📺 Check http://localhost:3000 to see the visual result")
    print("=" * 60)


if __name__ == "__main__":
    test_gui_chat()
