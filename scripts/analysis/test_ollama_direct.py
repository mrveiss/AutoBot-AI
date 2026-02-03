#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test Ollama connection directly without the retry mechanism
"""

import asyncio

import aiohttp


async def test_ollama_direct():
    """Test Ollama directly with aiohttp"""
    print("🤖 Testing Ollama directly with aiohttp...")

    url = "http://127.0.0.1:11434/api/chat"

    data = {
        "model": "artifish/llama3.2-uncensored:latest",
        "messages": [{"role": "user", "content": "Say hello"}],
        "stream": False,
    }

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            print(f"   Making request to {url}...")

            async with session.post(url, json=data) as response:
                print(f"   Response status: {response.status}")
                print(f"   Response headers: {dict(response.headers)}")

                # Test just reading JSON directly
                response_json = await response.json()
                print("   Response received!")
                print(
                    f"   Content: {response_json.get('message', {}).get('content', 'No content')}"
                )

                return response_json

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return None


async def test_complex_request():
    """Test with the complex request AutoBot makes"""
    print("\n🔍 Testing complex AutoBot request...")

    url = "http://127.0.0.1:11434/api/chat"

    data = {
        "model": "artifish/llama3.2-uncensored:latest",
        "messages": [
            {
                "role": "system",
                "content": "You are an expert classification agent. Respond only with valid JSON.",
            },
            {
                "role": "user",
                "content": "Classify this request: 'hello'. Return JSON with complexity (simple/complex) and reasoning.",
            },
        ],
        "stream": False,
        "temperature": 0.7,
        "format": "",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            print(f"   Making complex request to {url}...")

            async with session.post(url, json=data) as response:
                print(f"   Response status: {response.status}")

                # Test reading response
                response_json = await response.json()
                print("   Complex response received!")
                print(f"   Content length: {len(str(response_json))}")

                return response_json

    except Exception as e:
        print(f"❌ Complex request error: {e}")
        import traceback

        traceback.print_exc()
        return None


async def main():
    """Run direct tests"""
    print("🚀 Direct Ollama Test")
    print("=" * 30)

    # Test simple request
    simple_result = await test_ollama_direct()

    # Test complex request
    complex_result = await test_complex_request()

    if simple_result and complex_result:
        print("\n✅ Both tests successful - Ollama works fine with aiohttp")
    else:
        print("\n❌ Some tests failed")


if __name__ == "__main__":
    asyncio.run(main())
