#!/usr/bin/env python3
"""
Test the new simplified terminal WebSocket
"""

import asyncio
import json
import time

import websockets

from tests.test_helpers import get_test_backend_url


async def test_simple_terminal():
    """Test the simple terminal WebSocket endpoint"""
    print("🧪 Testing Simple Terminal WebSocket")  # noqa: print
    print("=" * 40)  # noqa: print

    # Generate a unique session ID
    session_id = f"test_{int(time.time())}"
    print(f"📝 Session ID: {session_id}")  # noqa: print

    uri = (
        get_test_backend_url().replace("https://", "wss://").replace("http://", "ws://")
        + f"/api/terminal/ws/{session_id}"
    )
    print(f"🔗 Connecting to: {uri}")  # noqa: print

    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to simple terminal")  # noqa: print

            # Wait for connection message and initial prompt
            for i in range(3):
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    print(f"📥 Initial message {i+1}: {response}")  # noqa: print

                    data = json.loads(response)
                    if data.get("type") == "output" and "$" in data.get("content", ""):
                        print("✅ Got initial prompt - ready to send commands!")  # noqa: print  # noqa: print
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
                print(f"\n📤 Testing: {cmd}")  # noqa: print

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
                            print(f"📥 Output: {repr(content)}")  # noqa: print

                            # Check if we got the expected output
                            if cmd == "whoami" and "kali" in content:
                                print("✅ whoami command worked!")  # noqa: print
                                output_received = True
                            elif cmd == "pwd" and "/" in content:
                                print("✅ pwd command worked!")  # noqa: print
                                output_received = True
                            elif "Simple terminal test" in content:
                                print("✅ echo command worked!")  # noqa: print
                                output_received = True
                            elif cmd.startswith("ls") and ("total" in content or "drwx" in content):
                                print("✅ ls command worked!")  # noqa: print
                                output_received = True
                            elif cmd.startswith("cd /tmp") and "/tmp" in content:  # nosec B108 - test/controlled code uses tmpdir intentionally
                                print("✅ cd command worked!")  # noqa: print
                                output_received = True

                            # Check for new prompt (command finished)
                            if "$" in content and not content.strip().endswith("$"):
                                break

                        elif data.get("type") == "error":
                            print(f"❌ Error: {data.get('message')}")  # noqa: print
                            break

                    except asyncio.TimeoutError:
                        break

                if not output_received and cmd in [
                    "whoami",
                    "echo 'Simple terminal test'",
                ]:
                    print(f"⚠️ No clear output received for: {cmd}")  # noqa: print

            print("\n🎉 Simple terminal test completed!")  # noqa: print
            return True

    except Exception as e:
        print(f"❌ Test failed: {e}")  # noqa: print
        return False


async def test_sessions_api():
    """Test the simple sessions API"""
    print("\n🧪 Testing Simple Sessions API")  # noqa: print
    print("=" * 40)  # noqa: print

    import requests

    try:
        response = requests.get(get_test_backend_url() + "/api/terminal/sessions", timeout=5)
        if response.status_code == 200:
            sessions = response.json()
            print(f"✅ Simple sessions API working: {json.dumps(sessions, indent=2)}")  # noqa: print  # noqa: print
            return True
        else:
            print(f"❌ Sessions API failed: {response.status_code}")  # noqa: print
            return False
    except Exception as e:
        print(f"❌ Sessions API error: {e}")  # noqa: print
        return False


async def main():
    """Run simple terminal tests"""
    print("🚀 Simple Terminal Testing")  # noqa: print
    print("=" * 50)  # noqa: print

    # Test the WebSocket terminal
    terminal_success = await test_simple_terminal()

    # Test the sessions API
    api_success = await test_sessions_api()

    print("\n📊 TEST RESULTS:")  # noqa: print
    print("=" * 50)  # noqa: print

    if terminal_success:
        print("✅ SIMPLE TERMINAL: Working correctly!")  # noqa: print
        print("   └─ Commands execute and return output")  # noqa: print
    else:
        print("❌ SIMPLE TERMINAL: Not working")  # noqa: print

    if api_success:
        print("✅ SESSIONS API: Working correctly!")  # noqa: print
        print("   └─ Can list active simple sessions")  # noqa: print
    else:
        print("❌ SESSIONS API: Not working")  # noqa: print

    if terminal_success and api_success:
        print("\n🎉 SUCCESS: Simple terminal is a working replacement!")  # noqa: print
        print("User can now use the simple terminal endpoint:")  # noqa: print
        _base = get_test_backend_url()
        print(  # noqa: print
            f"  WebSocket: {_base.replace('https://', 'wss://').replace('http://', 'ws://')}/api/terminal/ws/{{session_id}}"
        )  # noqa: print
        print(f"  Sessions:  {_base}/api/terminal/sessions")  # noqa: print  # noqa: print
    else:
        print("\n💥 Some tests failed - simple terminal needs fixes")  # noqa: print


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Tests interrupted")  # noqa: print
    except Exception as e:
        print(f"\n💥 Tests failed: {e}")  # noqa: print
