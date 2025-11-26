#!/usr/bin/env python3
"""
Detailed Terminal Session Debugging for AutoBot
Checks internal session state and process details
"""

import asyncio
import json
import requests
import websockets
import sys
import time
from datetime import datetime

# Import centralized network configuration
sys.path.insert(0, "/home/kali/Desktop/AutoBot")
from src.constants.network_constants import NetworkConstants

# Build URLs from centralized configuration
BASE_URL = f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"
WS_BASE_URL = f"ws://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"


async def test_session_lifecycle():
    """Test the complete terminal session lifecycle with detailed monitoring"""
    print("🔬 Detailed Terminal Session Lifecycle Test")
    print("=" * 50)

    chat_id = f"debug_{int(time.time())}"
    print(f"📝 Using chat_id: {chat_id}")

    uri = f"{WS_BASE_URL}/api/terminal/ws/terminal/{chat_id}"

    try:
        async with websockets.connect(uri) as websocket:
            print(f"✅ WebSocket connected: {chat_id}")

            # Step 1: Wait for connection confirmation and session initialization
            print("\n🔍 Step 1: Session Initialization")
            try:
                for i in range(5):
                    msg = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    print(f"📥 Init message {i+1}: {msg}")

                    data = json.loads(msg)
                    if data.get("type") == "terminal_session" and data.get("status") == "started":
                        print("✅ Terminal session started successfully!")
                        break
                    elif data.get("type") == "connection":
                        print("📡 Connection established")
                        continue
                else:
                    print("⚠️ No terminal session start confirmation received")

            except asyncio.TimeoutError:
                print("⏰ Session initialization timeout")

            # Step 2: Test active sessions API
            print("\n🔍 Step 2: Checking Active Sessions")
            try:
                response = requests.get(f"{BASE_URL}/api/terminal/sessions", timeout=5)
                if response.status_code == 200:
                    sessions_data = response.json()
                    print(f"📊 Active sessions response: {json.dumps(sessions_data, indent=2)}")

                    # Look for our session
                    found_session = False
                    sessions = sessions_data.get('sessions', []) if isinstance(sessions_data, dict) else sessions_data
                    for session in sessions:
                        if session.get('chat_id') == chat_id:
                            found_session = True
                            print(f"✅ Found our session: {session}")
                            break

                    if not found_session:
                        print(f"❌ Our session {chat_id} not found in active sessions")
                else:
                    print(f"❌ Failed to get active sessions: {response.status_code}")
            except Exception as e:
                print(f"❌ Active sessions check error: {e}")

            # Step 3: Send a simple command and monitor all responses
            print("\n🔍 Step 3: Command Execution Test")

            # Send command
            command = "echo 'Debug test command'"
            command_msg = json.dumps({
                "type": "input",
                "text": f"{command}\n"
            })

            await websocket.send(command_msg)
            print(f"📤 Sent: {command}")

            # Monitor all responses for 10 seconds
            start_time = time.time()
            received_output = False

            print("📥 Monitoring responses...")
            while time.time() - start_time < 10:
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    print(f"📨 Response: {response}")

                    try:
                        data = json.loads(response)
                        if data.get("type") == "output":
                            content = data.get("content", "")
                            if "Debug test command" in content:
                                print("✅ Command output received successfully!")
                                received_output = True
                                break
                        elif data.get("type") == "error":
                            print(f"❌ Error received: {data}")
                            break
                    except json.JSONDecodeError:
                        print(f"📊 Raw response: {response[:200]}...")

                except asyncio.TimeoutError:
                    continue

            if not received_output:
                print("❌ No command output received")

            # Step 4: Test taking control
            print("\n🔍 Step 4: Testing User Control")
            control_msg = json.dumps({"type": "take_control"})
            await websocket.send(control_msg)
            print("📤 Sent take_control request")

            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=3.0)
                print(f"📥 Control response: {response}")
            except asyncio.TimeoutError:
                print("⏰ No control response")

            return received_output

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def test_system_command_agent_direct():
    """Test SystemCommandAgent directly if possible"""
    print("\n🔬 Direct SystemCommandAgent Test")
    print("=" * 50)

    try:
        # Try to import and test directly
        import sys
        sys.path.append('/home/kali/Desktop/AutoBot')

        from src.agents.system_command_agent import SystemCommandAgent

        agent = SystemCommandAgent()
        chat_id = f"direct_test_{int(time.time())}"

        print(f"📝 Testing with chat_id: {chat_id}")
        print(f"📊 Current active sessions: {len(agent.active_sessions)}")

        # Check if we can access the agent state
        sessions = []
        for session_id, terminal in agent.active_sessions.items():
            sessions.append({
                "session_id": session_id,
                "chat_id": terminal.chat_id,
                "active": terminal.session_active,
                "mode": terminal.input_mode
            })

        print(f"📋 Active sessions details: {json.dumps(sessions, indent=2)}")
        return True

    except ImportError as e:
        print(f"⚠️ Cannot import SystemCommandAgent: {e}")
        return False
    except Exception as e:
        print(f"❌ Direct test failed: {e}")
        return False


async def main():
    """Run detailed terminal debugging"""
    print("🚀 Detailed Terminal Session Debugging")
    print("=" * 60)
    print(f"🕐 Started: {datetime.now()}")

    # Test 1: Complete session lifecycle
    session_success = await test_session_lifecycle()

    # Test 2: Direct agent access (if possible)
    direct_success = test_system_command_agent_direct()

    print("\n📊 DETAILED DIAGNOSTIC RESULTS")
    print("=" * 60)

    if session_success:
        print("✅ TERMINAL SESSION: Commands execute properly")
        print("   └─ Terminal backend is working correctly")
    else:
        print("❌ TERMINAL SESSION: Commands not executing")
        print("   └─ Issue in session initialization or command processing")

    if direct_success:
        print("✅ DIRECT ACCESS: SystemCommandAgent accessible")
        print("   └─ Can inspect internal state")
    else:
        print("⚠️ DIRECT ACCESS: Cannot inspect SystemCommandAgent")
        print("   └─ Using external testing only")

    print("\n🎯 DEBUGGING CONCLUSIONS")
    print("=" * 60)

    if session_success:
        print("Terminal is working - user may have different access method issue")
    else:
        print("Terminal has execution problems - likely in InteractiveTerminalAgent")
        print("Possible causes:")
        print("1. PTY not properly initialized")
        print("2. Process not starting correctly")
        print("3. Output streaming not working")
        print("4. Event manager not publishing events")
        print("5. WebSocket not receiving terminal events")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Debugging interrupted")
    except Exception as e:
        print(f"\n💥 Debugging failed: {e}")
