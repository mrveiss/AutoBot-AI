#!/usr/bin/env python3
"""
Terminal Debugging Utility for AutoBot
Helps diagnose terminal functionality issues

Issue #396: Converted from blocking requests to async httpx.
"""

import asyncio
import json
import httpx
import websockets
import sys
from datetime import datetime

# Import centralized network configuration
sys.path.insert(0, "/home/kali/Desktop/AutoBot")
from src.constants.network_constants import NetworkConstants

# Build URLs from centralized configuration
BASE_URL = f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"
WS_BASE_URL = f"ws://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"


async def test_terminal_api():
    """Test the terminal REST API endpoints"""
    print("🔍 Testing Terminal REST API...")

    # Test session creation
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/api/terminal/sessions",
                json={
                    "shell": "/bin/bash",
                    "environment": {},
                    "working_directory": "/home/kali",
                },
                timeout=5.0,
            )
            if response.status_code == 200:
                session_data = response.json()
                session_id = session_data["session_id"]
                print(f"✅ Session creation successful: {session_id}")
                return session_id
            else:
                print(
                    f"❌ Session creation failed: {response.status_code} - {response.text}"
                )
                return None
    except Exception as e:
        print(f"❌ Session creation error: {e}")
        return None


async def test_terminal_websocket(session_id):
    """Test the terminal WebSocket connection"""
    print(f"\n🔍 Testing Terminal WebSocket for session {session_id}...")

    uri = f"{WS_BASE_URL}/api/terminal/ws/terminal/{session_id}"

    try:
        async with websockets.connect(uri) as websocket:
            print(f"✅ WebSocket connected to {uri}")

            # Send a simple command
            command_msg = json.dumps(
                {"type": "input", "text": "echo 'Hello from terminal test'\n"}
            )

            await websocket.send(command_msg)
            print("📤 Sent command: echo 'Hello from terminal test'")

            # Wait for response
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"📥 Received response: {response}")

                # Try to parse as JSON
                try:
                    data = json.loads(response)
                    if data.get("type") == "output":
                        print(f"✅ Terminal output received: {data.get('content', '')}")
                    else:
                        print(f"📊 Terminal response type: {data.get('type')}")
                except json.JSONDecodeError:
                    print(f"📊 Raw terminal output: {response}")

            except asyncio.TimeoutError:
                print("⏰ Timeout waiting for terminal response")

    except Exception as e:
        print(f"❌ WebSocket connection error: {e}")


async def test_system_health():
    """Test overall system health"""
    print("\n🔍 Testing System Health...")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/api/system/health", timeout=5.0)
            if response.status_code == 200:
                health_data = response.json()
                print(f"✅ System health: {health_data}")
            else:
                print(f"❌ Health check failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Health check error: {e}")


async def test_workflow_api():
    """Test workflow API that we know is working"""
    print("\n🔍 Testing Workflow API (known working)...")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}/api/workflow/workflows", timeout=5.0
            )
            if response.status_code == 200:
                workflow_data = response.json()
                workflow_count = len(workflow_data.get('workflows', []))
                print(f"✅ Workflow API working: {workflow_count} active workflows")
            else:
                print(f"❌ Workflow API failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Workflow API error: {e}")


async def main():
    """Run all terminal diagnostic tests"""
    print("🚀 AutoBot Terminal Diagnostic Tool")
    print("=" * 50)
    print(f"🕐 Test started at: {datetime.now()}")
    print()

    # Test system health first
    await test_system_health()

    # Test workflow API to ensure backend is responding
    await test_workflow_api()

    # Test terminal API
    session_id = await test_terminal_api()

    if session_id:
        # Test WebSocket if session creation succeeded
        await test_terminal_websocket(session_id)

        # Clean up session
        try:
            async with httpx.AsyncClient() as client:
                delete_response = await client.delete(
                    f"{BASE_URL}/api/terminal/sessions/{session_id}", timeout=5.0
                )
                if delete_response.status_code == 200:
                    print(f"🧹 Session {session_id} cleaned up successfully")
                else:
                    print(f"⚠️ Session cleanup warning: {delete_response.status_code}")
        except Exception as e:
            print(f"⚠️ Session cleanup error: {e}")

    print("\n📋 DIAGNOSTIC SUMMARY:")
    print("=" * 50)
    print("If you see '✅' for all tests, the terminal should be working.")
    print("If you see '❌' errors, there's a configuration or connection issue.")
    print()
    print("📝 COMMON ISSUES:")
    print("1. Frontend not connecting - Check browser console for WebSocket errors")
    print("2. Commands not executing - Verify PTY support and permissions")
    print("3. Session not found - Check session ID passing between frontend/backend")
    print()
    print("🔧 FRONTEND DEBUGGING:")
    print("1. Open browser DevTools (F12)")
    print("2. Go to Network tab -> WS (WebSocket)")
    print("3. Try using terminal and watch for connection attempts")
    print("4. Check Console tab for JavaScript errors")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("AutoBot Terminal Diagnostic Tool")
        print("Usage: python3 debug_terminal.py")
        print("This tool tests the terminal API and WebSocket connections")
        sys.exit(0)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Diagnostic interrupted by user")
    except Exception as e:
        print(f"\n💥 Diagnostic failed with error: {e}")
