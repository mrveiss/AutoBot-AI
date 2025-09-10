# \!/usr/bin/env python3
"""
Test script to debug chat endpoint issues
"""

import asyncio
import time

import aiohttp

BASE_URL = "http://127.0.0.3:8001"


async def test_endpoint(session, endpoint, method="GET", data=None, timeout=10):
    """Test a single endpoint with timeout"""
    url = f"{BASE_URL}{endpoint}"
    print(f"Testing {method} {endpoint}...")

    start_time = time.time()
    try:
        if method == "GET":
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                result = await response.json()
                elapsed = time.time() - start_time
                print(f"  ✅ SUCCESS ({elapsed:.2f}s): {response.status}")
                return True, result
        elif method == "POST":
            async with session.post(
                url, json=data, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                result = await response.json()
                elapsed = time.time() - start_time
                print(f"  ✅ SUCCESS ({elapsed:.2f}s): {response.status}")
                return True, result
    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        print(f"  ❌ TIMEOUT ({elapsed:.2f}s)")
        return False, "timeout"
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"  ❌ ERROR ({elapsed:.2f}s): {e}")
        return False, str(e)


async def main():
    """Run endpoint tests"""
    print("🧪 Testing AutoBot API endpoints...\n")

    async with aiohttp.ClientSession() as session:
        # Test basic endpoints
        endpoints_to_test = [
            ("/api/system/health", "GET", None, 5),
            ("/api/chats/new", "POST", {}, 10),
            ("/api/chats", "GET", None, 10),
        ]

        for endpoint, method, data, timeout in endpoints_to_test:
            success, result = await test_endpoint(
                session, endpoint, method, data, timeout
            )
            if not success:
                print(f"❌ Critical endpoint {endpoint} failed!")
                continue
            print()

        # Test chat endpoints if basic ones work
        print("🗨️ Testing chat endpoints...")

        # Create a test chat first
        success, chat_result = await test_endpoint(
            session, "/api/chats/new", "POST", {}, 10
        )
        if success and "chat_id" in chat_result:
            chat_id = chat_result["chat_id"]
            print(f"Created test chat: {chat_id}")

            # Test direct chat (simpler)
            chat_data = {"chatId": chat_id, "message": "hi"}
            success, result = await test_endpoint(
                session, "/api/chat/direct", "POST", chat_data, 15
            )
            if success:
                print("✅ Direct chat endpoint working!")
            else:
                print("❌ Direct chat endpoint failed")

            # Test main chat endpoint
            chat_data = {"message": "hi"}
            success, result = await test_endpoint(
                session, f"/api/chats/{chat_id}/message", "POST", chat_data, 25
            )
            if success:
                print("✅ Main chat endpoint working!")
            else:
                print("❌ Main chat endpoint failed")
        else:
            print("❌ Could not create test chat, skipping chat tests")


if __name__ == "__main__":
    asyncio.run(main())
