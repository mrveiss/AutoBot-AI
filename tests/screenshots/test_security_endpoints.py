#!/usr/bin/env python3
"""
Test security endpoints integration
"""

import asyncio
import os
import signal
import subprocess
import sys
import time

import requests


async def test_security_endpoints():
    """Test security endpoints with a running server"""
    print("🔒 Testing Security Endpoints Integration")
    print("=" * 60)

    server_process = None
    try:
        # Start the server
        print("🚀 Starting backend server...")
        server_process = subprocess.Popen(
            [sys.executable, "main.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid,
        )

        # Wait for server to start up
        print("⏳ Waiting for server startup...")
        max_attempts = 20
        server_ready = False

        for attempt in range(max_attempts):
            try:
                response = requests.get("http://localhost:8001/api/hello", timeout=2)
                if response.status_code == 200:
                    server_ready = True
                    print(f"✅ Server ready after {attempt + 1} attempts")
                    break
            except Exception:
                pass
            time.sleep(1)

        if not server_ready:
            print("❌ Server failed to start within timeout")
            return

        # Test security status endpoint
        print("\n🔍 Testing security status endpoint...")
        try:
            response = requests.get(
                "http://localhost:8001/api/security/status", timeout=5
            )
            print(f"   Status code: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print("✅ Security status endpoint working")
                print(f"   - Security enabled: {data.get('security_enabled')}")
                print(
                    f"   - Command security enabled: {data.get('command_security_enabled')}"
                )
                print(
                    f"   - Docker sandbox enabled: {data.get('docker_sandbox_enabled')}"
                )
                print(
                    f"   - Pending approvals: {len(data.get('pending_approvals', []))}"
                )
            else:
                print(f"❌ Security status endpoint failed: {response.status_code}")
                print(f"   Response: {response.text}")

        except Exception as e:
            print(f"❌ Security status test failed: {e}")

        # Test command history endpoint
        print("\n📋 Testing command history endpoint...")
        try:
            response = requests.get(
                "http://localhost:8001/api/security/command-history", timeout=5
            )
            print(f"   Status code: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print("✅ Command history endpoint working")
                print(f"   - History entries: {data.get('count', 0)}")
                if data.get("count", 0) > 0:
                    print("   - Sample entries:")
                    for entry in data.get("command_history", [])[:3]:
                        print(
                            f"     * {entry.get('timestamp', 'N/A')} - {entry.get('action', 'N/A')}"
                        )
            else:
                print(f"❌ Command history endpoint failed: {response.status_code}")
                print(f"   Response: {response.text}")

        except Exception as e:
            print(f"❌ Command history test failed: {e}")

        # Test pending approvals endpoint
        print("\n⏳ Testing pending approvals endpoint...")
        try:
            response = requests.get(
                "http://localhost:8001/api/security/pending-approvals", timeout=5
            )
            print(f"   Status code: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print("✅ Pending approvals endpoint working")
                print(f"   - Pending count: {data.get('count', 0)}")
            else:
                print(f"❌ Pending approvals endpoint failed: {response.status_code}")
                print(f"   Response: {response.text}")

        except Exception as e:
            print(f"❌ Pending approvals test failed: {e}")

        # Test audit log endpoint
        print("\n📜 Testing audit log endpoint...")
        try:
            response = requests.get(
                "http://localhost:8001/api/security/audit-log", timeout=5
            )
            print(f"   Status code: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print("✅ Audit log endpoint working")
                print(f"   - Audit entries: {data.get('count', 0)}")
            else:
                print(f"❌ Audit log endpoint failed: {response.status_code}")
                print(f"   Response: {response.text}")

        except Exception as e:
            print(f"❌ Audit log test failed: {e}")

        # Test secure terminal WebSocket (basic connection test)
        print("\n🖥️  Testing secure terminal WebSocket availability...")
        try:
            # Just check if the endpoint is available (can't easily test WebSocket here)
            import websocket

            ws_url = "ws://localhost:8001/api/terminal/ws/secure/test_session"
            print(f"   WebSocket URL: {ws_url}")
            print("   ℹ️  WebSocket functionality requires separate testing")
        except Exception as e:
            print(f"   ℹ️  WebSocket test skipped: {e}")

        print("\n✅ Security endpoints integration test completed!")

    except Exception as e:
        print(f"❌ Test failed with exception: {e}")

    finally:
        # Clean up server
        if server_process:
            print("\n🛑 Stopping server...")
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
            print("✅ Server stopped")


def main():
    """Main test runner"""
    asyncio.run(test_security_endpoints())


if __name__ == "__main__":
    main()
