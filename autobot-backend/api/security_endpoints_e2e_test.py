#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Test security endpoints integration
"""

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).parent.parent))
from tests.test_helpers import get_test_backend_url


async def _poll_server_ready(timeout: float = 2.0) -> bool:
    """Return True if /api/hello responds 200 within timeout seconds."""
    try:
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.get(get_test_backend_url() + "/api/hello") as resp:
                return resp.status == 200
    except Exception:
        return False


async def _get_json(session: aiohttp.ClientSession, url: str, timeout: float = 5.0):
    """GET url and return (status, json_data, text). On error returns (None, None, str)."""
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    try:
        async with session.get(url, timeout=client_timeout) as resp:
            status = resp.status
            try:
                data = await resp.json()
            except Exception:
                data = None
            text = await resp.text() if data is None else None
            return status, data, text
    except Exception as exc:
        return None, None, str(exc)


async def test_security_endpoints():
    """Test security endpoints with a running server"""
    print("🔒 Testing Security Endpoints Integration")  # noqa: print
    print("=" * 60)  # noqa: print

    server_process = None
    try:
        # Start the server
        print("🚀 Starting backend server...")  # noqa: print
        server_process = subprocess.Popen(
            [sys.executable, "main.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid,
        )

        # Wait for server to start up
        print("⏳ Waiting for server startup...")  # noqa: print
        max_attempts = 20
        server_ready = False

        for attempt in range(max_attempts):
            if await _poll_server_ready():
                server_ready = True
                print(f"✅ Server ready after {attempt + 1} attempts")  # noqa: print
                break
            await asyncio.sleep(1)

        if not server_ready:
            print("❌ Server failed to start within timeout")  # noqa: print
            return

        base_timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=base_timeout) as session:
            # Test security status endpoint
            print("\n🔍 Testing security status endpoint...")  # noqa: print
            try:
                status, data, text = await _get_json(session, get_test_backend_url() + "/api/security/status")
                print(f"   Status code: {status}")  # noqa: print
                if status == 200:
                    print("✅ Security status endpoint working")  # noqa: print
                    print(f"   - Security enabled: {data.get('security_enabled')}")  # noqa: print
                    print(f"   - Command security enabled: {data.get('command_security_enabled')}")  # noqa: print
                    print(f"   - Docker sandbox enabled: {data.get('docker_sandbox_enabled')}")  # noqa: print
                    print(f"   - Pending approvals: {len(data.get('pending_approvals', []))}")  # noqa: print
                else:
                    print(f"❌ Security status endpoint failed: {status}")  # noqa: print
                    print(f"   Response: {text}")  # noqa: print
            except Exception as e:
                print(f"❌ Security status test failed: {e}")  # noqa: print

            # Test command history endpoint
            print("\n📋 Testing command history endpoint...")  # noqa: print
            try:
                status, data, text = await _get_json(session, get_test_backend_url() + "/api/security/command-history")
                print(f"   Status code: {status}")  # noqa: print
                if status == 200:
                    print("✅ Command history endpoint working")  # noqa: print
                    print(f"   - History entries: {data.get('count', 0)}")  # noqa: print
                    if data.get("count", 0) > 0:
                        print("   - Sample entries:")  # noqa: print
                        for entry in data.get("command_history", [])[:3]:
                            print(
                                f"     * {entry.get('timestamp', 'N/A')} - {entry.get('action', 'N/A')}"
                            )  # noqa: print
                else:
                    print(f"❌ Command history endpoint failed: {status}")  # noqa: print
                    print(f"   Response: {text}")  # noqa: print
            except Exception as e:
                print(f"❌ Command history test failed: {e}")  # noqa: print

            # Test pending approvals endpoint
            print("\n⏳ Testing pending approvals endpoint...")  # noqa: print
            try:
                status, data, text = await _get_json(
                    session, get_test_backend_url() + "/api/security/pending-approvals"
                )
                print(f"   Status code: {status}")  # noqa: print
                if status == 200:
                    print("✅ Pending approvals endpoint working")  # noqa: print
                    print(f"   - Pending count: {data.get('count', 0)}")  # noqa: print
                else:
                    print(f"❌ Pending approvals endpoint failed: {status}")  # noqa: print
                    print(f"   Response: {text}")  # noqa: print
            except Exception as e:
                print(f"❌ Pending approvals test failed: {e}")  # noqa: print

            # Test audit log endpoint
            print("\n📜 Testing audit log endpoint...")  # noqa: print
            try:
                status, data, text = await _get_json(session, get_test_backend_url() + "/api/security/audit-log")
                print(f"   Status code: {status}")  # noqa: print
                if status == 200:
                    print("✅ Audit log endpoint working")  # noqa: print
                    print(f"   - Audit entries: {data.get('count', 0)}")  # noqa: print
                else:
                    print(f"❌ Audit log endpoint failed: {status}")  # noqa: print
                    print(f"   Response: {text}")  # noqa: print
            except Exception as e:
                print(f"❌ Audit log test failed: {e}")  # noqa: print

        # Test secure terminal WebSocket (basic connection test)
        print("\n🖥️  Testing secure terminal WebSocket availability...")  # noqa: print
        try:
            # Just check if the endpoint is available (can't easily test WebSocket here)
            pass

            ws_url = get_test_backend_url().replace("http://", "ws://") + "/api/terminal/ws/secure/test_session"
            print(f"   WebSocket URL: {ws_url}")  # noqa: print
            print("   ℹ️  WebSocket functionality requires separate testing")  # noqa: print
        except Exception as e:
            print(f"   ℹ️  WebSocket test skipped: {e}")  # noqa: print

        print("\n✅ Security endpoints integration test completed!")  # noqa: print

    except Exception as e:
        print(f"❌ Test failed with exception: {e}")  # noqa: print

    finally:
        # Clean up server
        if server_process:
            print("\n🛑 Stopping server...")  # noqa: print
            try:
                # Send SIGTERM to process group
                os.killpg(os.getpgid(server_process.pid), signal.SIGTERM)
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if needed
                os.killpg(os.getpgid(server_process.pid), signal.SIGKILL)
                server_process.wait()
            except Exception:
                pass
            print("✅ Server stopped")  # noqa: print


def main():
    """Main test runner"""
    asyncio.run(test_security_endpoints())


if __name__ == "__main__":
    main()
