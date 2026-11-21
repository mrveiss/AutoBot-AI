#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Test Ollama connection directly without the retry mechanism
"""

import asyncio
import sys
from pathlib import Path

import aiohttp

# Runs from any directory with no PYTHONPATH: the repository root goes on the path for `autobot_shared` (#18289).
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from autobot_shared.network_constants import ServiceURLs  # noqa: E402
from autobot_shared.ollama_urls import ollama_chat_url  # noqa: E402


async def test_ollama_direct():
    """Test Ollama directly with aiohttp"""
    print("🤖 Testing Ollama directly with aiohttp...")

    url = ollama_chat_url(ServiceURLs.OLLAMA_LOCAL)

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
                print(f"   Content: {response_json.get('message', {}).get('content', 'No content')}")

                return response_json

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return None


async def test_complex_request():
    """Test with the complex request AutoBot makes"""
    print("\n🔍 Testing complex AutoBot request...")

    url = ollama_chat_url(ServiceURLs.OLLAMA_LOCAL)

    data = {
        "model": "artifish/llama3.2-uncensored:latest",
        "messages": [
            {
                "role": "system",
                "content": "You are an expert classification agent. Respond only with valid JSON.",
            },
            {
                "role": "user",
                "content": (
                    "Classify this request: 'hello'. Return JSON with complexity (simple/complex) and reasoning."
                ),
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
