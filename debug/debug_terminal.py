#!/usr/bin/env python3
"""
Terminal Debugging Utility for AutoBot
Helps diagnose terminal functionality issues

Issue #396: Converted from blocking requests to async httpx.
"""

import asyncio
import json
import logging
import sys
import os
from datetime import datetime

import httpx
import websockets

# Import centralized network configuration
sys.path.insert(0, os.environ.get("AUTOBOT_PROJECT_ROOT", "/opt/autobot/code_source"))
from constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)

# Build URLs from centralized configuration
BASE_URL = f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"
WS_BASE_URL = f"ws://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"


async def test_terminal_api():
    """Test the terminal REST API endpoints"""
    logger.info("Testing Terminal REST API...")

    # Test session creation
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/api/terminal/sessions",
                json={
                    "shell": "/bin/bash",
                    "environment": {},
                    "working_directory": "/home/autobot",
                },
                timeout=5.0,
            )
            if response.status_code == 200:
                session_data = response.json()
                session_id = session_data["session_id"]
                logger.info("Session creation successful: %s", session_id)
                return session_id
            else:
                logger.error(
                    "Session creation failed: %s - %s",
                    response.status_code,
                    response.text,
                )
                return None
    except Exception as e:
        logger.error("Session creation error: %s", e)
        return None


async def test_terminal_websocket(session_id):
    """Test the terminal WebSocket connection"""
    logger.info(f"\n🔍 Testing Terminal WebSocket for session {session_id}...")

    uri = f"{WS_BASE_URL}/api/terminal/ws/terminal/{session_id}"

    try:
        async with websockets.connect(uri) as websocket:
            logger.info(f"✅ WebSocket connected to {uri}")

            # Send a simple command
            command_msg = json.dumps({"type": "input", "text": "echo 'Hello from terminal test'\n"})

            await websocket.send(command_msg)
            logger.info("📤 Sent command: echo 'Hello from terminal test'")

            # Wait for response
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                logger.info(f"📥 Received response: {response}")

                # Try to parse as JSON
                try:
                    data = json.loads(response)
                    if data.get("type") == "output":
                        logger.info(f"✅ Terminal output received: {data.get('content', '')}")
                    else:
                        logger.info(f"📊 Terminal response type: {data.get('type')}")
                except json.JSONDecodeError:
                    logger.info(f"📊 Raw terminal output: {response}")

            except asyncio.TimeoutError:
                logger.info("⏰ Timeout waiting for terminal response")

    except Exception as e:
        logger.info(f"❌ WebSocket connection error: {e}")


async def test_system_health():
    """Test overall system health"""
    logger.info("\n🔍 Testing System Health...")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/api/system/health", timeout=5.0)
            if response.status_code == 200:
                health_data = response.json()
                logger.info(f"✅ System health: {health_data}")
            else:
                logger.info(f"❌ Health check failed: {response.status_code}")
    except Exception as e:
        logger.info(f"❌ Health check error: {e}")


async def test_workflow_api():
    """Test workflow API that we know is working"""
    logger.info("\n🔍 Testing Workflow API (known working)...")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/api/workflow/workflows", timeout=5.0)
            if response.status_code == 200:
                workflow_data = response.json()
                workflow_count = len(workflow_data.get("workflows", []))
                logger.info(f"✅ Workflow API working: {workflow_count} active workflows")
            else:
                logger.info(f"❌ Workflow API failed: {response.status_code}")
    except Exception as e:
        logger.info(f"❌ Workflow API error: {e}")


async def main():
    """Run all terminal diagnostic tests"""
    logger.info("🚀 AutoBot Terminal Diagnostic Tool")
    logger.info("=" * 50)
    logger.info(f"🕐 Test started at: {datetime.now()}")
    logger.info()

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
                delete_response = await client.delete(f"{BASE_URL}/api/terminal/sessions/{session_id}", timeout=5.0)
                if delete_response.status_code == 200:
                    logger.info(f"🧹 Session {session_id} cleaned up successfully")
                else:
                    logger.info(f"⚠️ Session cleanup warning: {delete_response.status_code}")
        except Exception as e:
            logger.info(f"⚠️ Session cleanup error: {e}")

    logger.info("\n📋 DIAGNOSTIC SUMMARY:")
    logger.info("=" * 50)
    logger.info("If you see '✅' for all tests, the terminal should be working.")
    logger.info("If you see '❌' errors, there's a configuration or connection issue.")
    logger.info()
    logger.info("📝 COMMON ISSUES:")
    logger.info("1. Frontend not connecting - Check browser console for WebSocket errors")
    logger.info("2. Commands not executing - Verify PTY support and permissions")
    logger.info("3. Session not found - Check session ID passing between frontend/backend")
    logger.info()
    logger.info("🔧 FRONTEND DEBUGGING:")
    logger.info("1. Open browser DevTools (F12)")
    logger.info("2. Go to Network tab -> WS (WebSocket)")
    logger.info("3. Try using terminal and watch for connection attempts")
    logger.info("4. Check Console tab for JavaScript errors")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        logger.info("AutoBot Terminal Diagnostic Tool")
        logger.info("Usage: python3 debug_terminal.py")
        logger.info("This tool tests the terminal API and WebSocket connections")
        sys.exit(0)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Diagnostic interrupted by user")
    except Exception as e:
        logger.error("Diagnostic failed with error: %s", e)
