#!/usr/bin/env python3
"""
Detailed Terminal Session Debugging for AutoBot
Checks internal session state and process details

Issue #396: Converted from blocking requests to async httpx.
"""

import asyncio
import json
import logging
import sys
import time
from datetime import datetime

import httpx
import websockets

logger = logging.getLogger(__name__)

# Import centralized network configuration
sys.path.insert(0, "/home/kali/Desktop/AutoBot")
from constants.network_constants import NetworkConstants

# Build URLs from centralized configuration
BASE_URL = f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"
WS_BASE_URL = f"ws://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"


async def _wait_for_session_init(websocket):
    """Wait for WebSocket connection confirmation and session initialization.

    Helper for test_session_lifecycle (#825).
    """
    logger.info("\n🔍 Step 1: Session Initialization")
    try:
        for i in range(5):
            msg = await asyncio.wait_for(websocket.recv(), timeout=2.0)
            logger.info(f"📥 Init message {i+1}: {msg}")

            data = json.loads(msg)
            if (
                data.get("type") == "terminal_session"
                and data.get("status") == "started"
            ):
                logger.info("✅ Terminal session started successfully!")
                break
            elif data.get("type") == "connection":
                logger.info("📡 Connection established")
                continue
        else:
            logger.warning("⚠️ No terminal session start confirmation received")

    except asyncio.TimeoutError:
        logger.info("⏰ Session initialization timeout")


async def _check_active_sessions(chat_id):
    """Check active sessions API for the given chat_id.

    Helper for test_session_lifecycle (#825).
    """
    logger.info("\n🔍 Step 2: Checking Active Sessions")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}/api/terminal/sessions", timeout=5.0
            )
            if response.status_code == 200:
                sessions_data = response.json()
                logger.info(
                    f"📊 Active sessions response: "
                    f"{json.dumps(sessions_data, indent=2)}"
                )

                found_session = False
                sessions = (
                    sessions_data.get("sessions", [])
                    if isinstance(sessions_data, dict)
                    else sessions_data
                )
                for session in sessions:
                    if session.get("chat_id") == chat_id:
                        found_session = True
                        logger.info(f"✅ Found our session: {session}")
                        break

                if not found_session:
                    logger.info(
                        f"❌ Our session {chat_id} not found in " f"active sessions"
                    )
            else:
                logger.info(
                    f"❌ Failed to get active sessions: " f"{response.status_code}"
                )
    except Exception as e:
        logger.error(f"❌ Active sessions check error: {e}")


async def _execute_command_test(websocket):
    """Send a test command and monitor WebSocket responses.

    Helper for test_session_lifecycle (#825).

    Returns:
        True if command output was received successfully.
    """
    logger.info("\n🔍 Step 3: Command Execution Test")

    command = "echo 'Debug test command'"
    command_msg = json.dumps({"type": "input", "text": f"{command}\n"})

    await websocket.send(command_msg)
    logger.info(f"📤 Sent: {command}")

    start_time = time.time()
    received_output = False

    logger.info("📥 Monitoring responses...")
    while time.time() - start_time < 10:
        try:
            response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
            logger.info(f"📨 Response: {response}")

            try:
                data = json.loads(response)
                if data.get("type") == "output":
                    content = data.get("content", "")
                    if "Debug test command" in content:
                        logger.info("✅ Command output received successfully!")
                        received_output = True
                        break
                elif data.get("type") == "error":
                    logger.error(f"❌ Error received: {data}")
                    break
            except json.JSONDecodeError:
                logger.info(f"📊 Raw response: {response[:200]}...")

        except asyncio.TimeoutError:
            continue

    if not received_output:
        logger.error("❌ No command output received")

    return received_output


async def _test_user_control(websocket):
    """Test taking user control of the terminal session.

    Helper for test_session_lifecycle (#825).
    """
    logger.info("\n🔍 Step 4: Testing User Control")
    control_msg = json.dumps({"type": "take_control"})
    await websocket.send(control_msg)
    logger.info("📤 Sent take_control request")

    try:
        response = await asyncio.wait_for(websocket.recv(), timeout=3.0)
        logger.info(f"📥 Control response: {response}")
    except asyncio.TimeoutError:
        logger.info("⏰ No control response")


async def test_session_lifecycle():
    """Test the complete terminal session lifecycle."""
    logger.info("🔬 Detailed Terminal Session Lifecycle Test")
    logger.info("=" * 50)

    chat_id = f"debug_{int(time.time())}"
    logger.info(f"📝 Using chat_id: {chat_id}")

    uri = f"{WS_BASE_URL}/api/terminal/ws/terminal/{chat_id}"

    try:
        async with websockets.connect(uri) as websocket:
            logger.info(f"✅ WebSocket connected: {chat_id}")

            await _wait_for_session_init(websocket)
            await _check_active_sessions(chat_id)
            received_output = await _execute_command_test(websocket)
            await _test_user_control(websocket)

            return received_output

    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False


def test_system_command_agent_direct():
    """Test SystemCommandAgent directly if possible"""
    logger.info("\n🔬 Direct SystemCommandAgent Test")
    logger.info("=" * 50)

    try:
        # Try to import and test directly
        import sys

        sys.path.append("/home/kali/Desktop/AutoBot")

        from agents.system_command_agent import SystemCommandAgent

        agent = SystemCommandAgent()
        chat_id = f"direct_test_{int(time.time())}"

        logger.info(f"📝 Testing with chat_id: {chat_id}")
        logger.info(f"📊 Current active sessions: {len(agent.active_sessions)}")

        # Check if we can access the agent state
        sessions = []
        for session_id, terminal in agent.active_sessions.items():
            sessions.append(
                {
                    "session_id": session_id,
                    "chat_id": terminal.chat_id,
                    "active": terminal.session_active,
                    "mode": terminal.input_mode,
                }
            )

        logger.info(f"📋 Active sessions details: {json.dumps(sessions, indent=2)}")
        return True

    except ImportError as e:
        logger.warning(f"⚠️ Cannot import SystemCommandAgent: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Direct test failed: {e}")
        return False


async def main():
    """Run detailed terminal debugging"""
    logger.info("🚀 Detailed Terminal Session Debugging")
    logger.info("=" * 60)
    logger.info(f"🕐 Started: {datetime.now()}")

    # Test 1: Complete session lifecycle
    session_success = await test_session_lifecycle()

    # Test 2: Direct agent access (if possible)
    direct_success = test_system_command_agent_direct()

    logger.info("\n📊 DETAILED DIAGNOSTIC RESULTS")
    logger.info("=" * 60)

    if session_success:
        logger.info("✅ TERMINAL SESSION: Commands execute properly")
        logger.info("   └─ Terminal backend is working correctly")
    else:
        logger.error("❌ TERMINAL SESSION: Commands not executing")
        logger.info("   └─ Issue in session initialization or command processing")

    if direct_success:
        logger.info("✅ DIRECT ACCESS: SystemCommandAgent accessible")
        logger.info("   └─ Can inspect internal state")
    else:
        logger.warning("⚠️ DIRECT ACCESS: Cannot inspect SystemCommandAgent")
        logger.info("   └─ Using external testing only")

    logger.info("\n🎯 DEBUGGING CONCLUSIONS")
    logger.info("=" * 60)

    if session_success:
        logger.info("Terminal is working - user may have different access method issue")
    else:
        logger.info(
            "Terminal has execution problems - likely in InteractiveTerminalAgent"
        )
        logger.info("Possible causes:")
        logger.info("1. PTY not properly initialized")
        logger.info("2. Process not starting correctly")
        logger.info("3. Output streaming not working")
        logger.info("4. Event manager not publishing events")
        logger.info("5. WebSocket not receiving terminal events")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n🛑 Debugging interrupted")
    except Exception as e:
        logger.error(f"\n💥 Debugging failed: {e}")
