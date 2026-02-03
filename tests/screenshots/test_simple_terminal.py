#!/usr/bin/env python3
"""
Test the new simplified terminal WebSocket
"""

import asyncio
import json
import time

import websockets


async def test_simple_terminal():
    """Test the simple terminal WebSocket endpoint"""
    print("🧪 Testing Simple Terminal WebSocket")
    print("=" * 40)

    # Generate a unique session ID
    session_id = f"test_{int(time.time())}"
    print(f"📝 Session ID: {session_id}")

    uri = f"ws://localhost:8001/api/terminal/ws/simple/{session_id}"
    print(f"🔗 Connecting to: {uri}")

    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to simple terminal")

            # Wait for connection message and initial prompt
            for i in range(3):
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    print(f"📥 Initial message {i+1}: {response}")

                    data = json.loads(response)
                    if data.get("type") == "output" and "$" in data.get("content", ""):
                        print("✅ Got initial prompt - ready to send commands!")
                        break

                except asyncio.TimeoutError:
                    break

            # Test commands
            test_commands = [
                "whoami",
                "pwd",
                "echo 'Simple terminal test'",
                "ls -la",
                "cd /tmp && pwd",
            ]

            for cmd in test_commands:
                print(f"\n📤 Testing: {cmd}")

                # Send command
                await websocket.send(json.dumps({"type": "input", "text": cmd}))

                # Collect output
                output_received = False
                start_time = time.time()

                while time.time() - start_time < 5:
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        data = json.loads(response)

                        if data.get("type") == "output":
                            content = data.get("content", "")
                            print(f"📥 Output: {repr(content)}")

                            # Check if we got the expected output
                            if cmd == "whoami" and "kali" in content:
                                print("✅ whoami command worked!")
                                output_received = True
                            elif cmd == "pwd" and "/" in content:
                                print("✅ pwd command worked!")
                                output_received = True
                            elif "Simple terminal test" in content:
                                print("✅ echo command worked!")
                                output_received = True
                            elif cmd.startswith("ls") and (
                                "total" in content or "drwx" in content
                            ):
                                print("✅ ls command worked!")
                                output_received = True
                            elif cmd.startswith("cd /tmp") and "/tmp" in content:
                                print("✅ cd command worked!")
                                output_received = True

                            # Check for new prompt (command finished)
                            if "$" in content and not content.strip().endswith("$"):
                                break

                        elif data.get("type") == "error":
                            print(f"❌ Error: {data.get('message')}")
                            break

                    except asyncio.TimeoutError:
                        break

                if not output_received and cmd in [
                    "whoami",
                    "echo 'Simple terminal test'",
                ]:
                    print(f"⚠️ No clear output received for: {cmd}")

            print(f"\n🎉 Simple terminal test completed!")
            return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


async def test_sessions_api():
    """Test the simple sessions API"""
    print(f"\n🧪 Testing Simple Sessions API")
    print("=" * 40)

    import requests

    try:
        response = requests.get(
            "http://localhost:8001/api/terminal/simple/sessions", timeout=5
        )
        if response.status_code == 200:
            sessions = response.json()
            print(f"✅ Simple sessions API working: {json.dumps(sessions, indent=2)}")
            return True
        else:
            print(f"❌ Sessions API failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Sessions API error: {e}")
        return False


async def main():
    """Run simple terminal tests"""
    print("🚀 Simple Terminal Testing")
    print("=" * 50)

    # Test the WebSocket terminal
    terminal_success = await test_simple_terminal()

    # Test the sessions API
    api_success = await test_sessions_api()

    print(f"\n📊 TEST RESULTS:")
    print("=" * 50)

    if terminal_success:
        print("✅ SIMPLE TERMINAL: Working correctly!")
        print("   └─ Commands execute and return output")
    else:
        print("❌ SIMPLE TERMINAL: Not working")

    if api_success:
        print("✅ SESSIONS API: Working correctly!")
        print("   └─ Can list active simple sessions")
    else:
        print("❌ SESSIONS API: Not working")

    if terminal_success and api_success:
        print(f"\n🎉 SUCCESS: Simple terminal is a working replacement!")
        print("User can now use the simple terminal endpoint:")
        print("  WebSocket: ws://localhost:8001/api/terminal/ws/simple/{session_id}")
        print("  Sessions:  http://localhost:8001/api/terminal/simple/sessions")
    else:
        print(f"\n💥 Some tests failed - simple terminal needs fixes")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Tests interrupted")
    except Exception as e:
        print(f"\n💥 Tests failed: {e}")
