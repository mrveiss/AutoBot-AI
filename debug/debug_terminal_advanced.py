#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Advanced Terminal Debugging Utility for AutoBot
Tests both REST API sessions and Chat-based WebSocket sessions
"""

import asyncio
import json
import requests
import websockets
import sys
import uuid
from datetime import datetime


def test_rest_api_approach():
    """Test the REST API terminal session approach"""
    print("🔍 Testing REST API Terminal Approach...")
    print("=" * 40)

    # Create session via REST API
    try:
        response = requests.post(
            "http://localhost:8001/api/terminal/sessions",
            json={"shell": "/bin/bash", "environment": {}, "working_directory": "/home/autobot"},
            timeout=5,
        )
        if response.status_code == 200:
            session_data = response.json()
            session_id = session_data["session_id"]
            print(f"✅ REST session created: {session_id}")
            return session_id
        else:
            print(f"❌ REST session failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"❌ REST session error: {e}")
        return None


async def test_chat_websocket_approach():
    """Test the chat-based WebSocket terminal approach"""
    print("\n🔍 Testing Chat WebSocket Terminal Approach...")
    print("=" * 40)

    # Generate a chat ID (like the frontend does)
    chat_id = f"chat_{int(datetime.now().timestamp())}"
    print(f"📝 Using chat_id: {chat_id}")

    uri = f"ws://localhost:8001/api/terminal/ws/terminal/{chat_id}"

    try:
        async with websockets.connect(uri) as websocket:
            print(f"✅ Chat WebSocket connected: {uri}")

            # Wait for initialization message
            try:
                init_msg = await asyncio.wait_for(websocket.recv(), timeout=3.0)
                print(f"📥 Initial message: {init_msg}")
            except asyncio.TimeoutError:
                print("⏰ No initial message received")

            # Send a command
            command_msg = json.dumps({"type": "input", "text": "echo 'Hello from chat terminal'\n"})

            await websocket.send(command_msg)
            print("📤 Sent: echo 'Hello from chat terminal'")

            # Wait for responses (multiple may come)
            for i in range(3):
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    print(f"📥 Response {i+1}: {response}")

                    # Parse and analyze response
                    try:
                        data = json.loads(response)
                        if data.get("type") == "output":
                            content = data.get("content", "")
                            if "Hello from chat terminal" in content:
                                print("✅ Command executed successfully!")
                                return True
                    except json.JSONDecodeError:
                        pass

                except asyncio.TimeoutError:
                    if i == 0:
                        print("⏰ No immediate response")
                    break

            return False

    except Exception as e:
        print(f"❌ Chat WebSocket error: {e}")
        return False


async def test_rest_websocket_mismatch(session_id):
    """Test connecting to WebSocket with REST session ID (should fail)"""
    print(f"\n🔍 Testing REST Session ID on Chat WebSocket (Expected to Fail)...")
    print("=" * 40)

    uri = f"ws://localhost:8001/api/terminal/ws/terminal/{session_id}"

    try:
        async with websockets.connect(uri) as websocket:
            print(f"⚠️ WebSocket connected with REST session ID: {session_id}")

            # Send command
            command_msg = json.dumps({"type": "input", "text": "echo 'Testing with REST session ID'\n"})

            await websocket.send(command_msg)
            print("📤 Sent command with REST session ID")

            # Check if we get proper output
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=3.0)
                print(f"📥 Response: {response}")

                data = json.loads(response)
                if data.get("type") == "output" and "Testing with REST session ID" in data.get("content", ""):
                    print("⚠️ Unexpectedly worked! This might explain the confusion.")
                    return True
                else:
                    print("❌ Command didn't execute as expected")
                    return False

            except asyncio.TimeoutError:
                print("⏰ No response - confirms session ID mismatch")
                return False

    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


def test_frontend_simulation():
    """Simulate how the frontend should work"""
    print("\n🔍 Frontend Integration Simulation...")
    print("=" * 40)

    print("📋 How the frontend SHOULD work:")
    print("1. TerminalWindow generates or gets chat_id")
    print("2. Connects to ws://localhost:8001/api/terminal/ws/terminal/{chat_id}")
    print("3. WebSocket handler creates internal terminal session")
    print("4. Commands are sent via WebSocket input messages")
    print("5. Output streams back via WebSocket output messages")
    print()
    print("❌ How it might be BROKEN:")
    print("1. User tries to use REST API session_id with WebSocket")
    print("2. Session ID mismatch prevents proper terminal initialization")
    print("3. Commands appear as text instead of being executed")


async def main():
    """Run comprehensive terminal debugging"""
    print("🚀 Advanced AutoBot Terminal Diagnostic")
    print("=" * 60)
    print(f"🕐 Started at: {datetime.now()}")
    print()

    # Test REST API approach
    session_id = test_rest_api_approach()

    # Test proper chat WebSocket approach
    chat_success = await test_chat_websocket_approach()

    # Test the problematic mixing of approaches
    if session_id:
        rest_ws_success = await test_rest_websocket_mismatch(session_id)

        # Cleanup REST session
        try:
            requests.delete(f"http://localhost:8001/api/terminal/sessions/{session_id}", timeout=5)
            print(f"🧹 Cleaned up REST session: {session_id}")
        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")

    # Show frontend simulation
    test_frontend_simulation()

    print(f"\n📊 DIAGNOSTIC RESULTS:")
    print("=" * 60)

    if chat_success:
        print("✅ CHAT WEBSOCKET APPROACH: Working correctly")
        print("   └─ This is how the frontend should work")
    else:
        print("❌ CHAT WEBSOCKET APPROACH: Not working")
        print("   └─ This indicates a deeper terminal execution problem")

    if session_id and rest_ws_success:
        print("⚠️ REST+WEBSOCKET MIXING: Unexpectedly working")
        print("   └─ This might be causing user confusion")
    elif session_id:
        print("❌ REST+WEBSOCKET MIXING: Properly rejected")
        print("   └─ Confirms session ID types shouldn't mix")

    print(f"\n💡 RECOMMENDED SOLUTION:")
    print("=" * 60)

    if chat_success:
        print("✅ Terminal backend is working correctly")
        print("📝 User should access terminal through chat interface:")
        print("   1. Open AutoBot frontend")
        print("   2. Look for Terminal option in navigation")
        print("   3. Use the integrated terminal (not REST API)")
        print("   4. Commands should execute properly")
    else:
        print("❌ Terminal backend has execution issues")
        print("🔧 Backend debugging needed:")
        print("   1. Check SystemCommandAgent initialization")
        print("   2. Verify PTY support and permissions")
        print("   3. Check InteractiveTerminalAgent session handling")

    print(f"\n🎯 USER GUIDANCE:")
    print("=" * 60)
    print("The terminal is designed to work through the chat interface,")
    print("not as standalone REST API sessions. Make sure you're using")
    print("the terminal feature within the AutoBot web interface.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("Advanced AutoBot Terminal Diagnostic")
        print("Tests both REST API and Chat WebSocket terminal approaches")
        print("Usage: python3 debug_terminal_advanced.py")
        sys.exit(0)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Diagnostic interrupted")
    except Exception as e:
        print(f"\n💥 Diagnostic failed: {e}")
