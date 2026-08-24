#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Test the new simplified terminal WebSocket
"""

import asyncio
import json
import time

import pytest
import websockets

from autobot_shared.ssot_config import config as ssot_config
from tests.test_helpers import get_test_backend_url


def _internal_api_key_headers() -> dict[str, str]:
    """Auth headers for this e2e script's own WebSocket handshake (#14989).

    api.terminal.terminal_websocket now authenticates every handshake
    (#14960) via the canonical SSOT-configured internal-service key -- the
    same credential auth_middleware.verify_internal_api_key checks -- rather
    than a bare value or a parallel path. Empty when unconfigured, matching
    verify_internal_api_key's own "never matches" behaviour for a missing key.
    """
    key = ssot_config.misc.internal_api_key
    return {"X-Internal-API-Key": key} if key else {}


async def _create_session_via_rest() -> str | None:
    """Create a real, owned terminal session via the REST endpoint (#14989).

    Issue #14961: an unknown session_id is now rejected outright, so a
    fabricated id (this script previously used `test_{timestamp}`) can no
    longer be connected to -- it must come from create_terminal_session,
    the only thing that stamps ownership for this session.
    """
    import aiohttp

    headers = _internal_api_key_headers()
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(
                get_test_backend_url() + "/api/terminal/sessions",
                json={"user_id": "e2e-test", "security_level": "standard"},
            ) as response:
                if response.status != 200:
                    print(f"❌ Failed to create terminal session: {response.status}")  # noqa: print
                    return None
                data = await response.json()
                return data.get("session_id")
    except Exception as e:
        print(f"❌ Error creating terminal session: {e}")  # noqa: print
        return None


async def test_simple_terminal():
    """Test the simple terminal WebSocket endpoint"""
    # This is a live e2e smoke test, not a unit test -- it needs a real
    # backend to connect to, which CI's python-suite does not start (no
    # AUTOBOT_TEST_BACKEND_URL is set there). Skip loudly rather than either
    # silently passing (the pre-existing behaviour this file's other checks
    # still have) or failing every run with no backend configured (#14920).
    if not get_test_backend_url():
        pytest.skip("AUTOBOT_TEST_BACKEND_URL not set -- no live backend to test against")

    print("🧪 Testing Simple Terminal WebSocket")  # noqa: print
    print("=" * 40)  # noqa: print

    # #14989/#14961: the session must be created via REST -- an unknown
    # session_id is rejected outright, so a locally-fabricated one no
    # longer connects.
    session_id = await _create_session_via_rest()
    # #14920: a bare `return False` here is discarded by pytest -- this
    # function is collected as test_simple_terminal, so a failure to create
    # the session must fail the test, not silently report green.
    assert session_id, "Could not create a terminal session -- aborting"
    print(f"📝 Session ID: {session_id}")  # noqa: print

    uri = (
        get_test_backend_url().replace("https://", "wss://").replace("http://", "ws://")
        + f"/api/terminal/ws/{session_id}"
    )
    print(f"🔗 Connecting to: {uri}")  # noqa: print

    try:
        async with websockets.connect(uri, additional_headers=_internal_api_key_headers()) as websocket:
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
                            elif (
                                cmd.startswith("cd /tmp")
                                and "/tmp" in content  # nosec B108  # test/controlled code uses tmpdir intentionally
                            ):
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

    import aiohttp

    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(get_test_backend_url() + "/api/terminal/sessions") as response:
                if response.status == 200:
                    sessions = await response.json()
                    print(f"✅ Simple sessions API working: {json.dumps(sessions, indent=2)}")  # noqa: print
                    return True
                else:
                    print(f"❌ Sessions API failed: {response.status}")  # noqa: print
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
