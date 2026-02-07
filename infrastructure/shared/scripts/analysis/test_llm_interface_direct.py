#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test LLM interface with a simplified version bypassing retry mechanism
"""

import asyncio
import json
import sys
from pathlib import Path

import aiohttp

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


async def test_llm_interface_simplified():
    """Test LLM interface logic without retry mechanism"""
    print("🤖 Testing simplified LLM interface logic...")

    # Mimic the exact data structure AutoBot uses
    url = "http://127.0.0.1:11434/api/chat"
    headers = {"Content-Type": "application/json"}

    data = {
        "model": "artifish/llama3.2-uncensored:latest",
        "messages": [{"role": "user", "content": "Say hello"}],
        "stream": False,
        "temperature": 0.7,
        "format": "",
    }

    print(f"Ollama Request URL: {url}")
    print(f"Ollama Request Headers: {headers}")
    print(f"Ollama Request Data: {json.dumps(data, indent=2)}")

    try:
        # This is exactly the same logic as in LLM interface but without retry wrapper
        timeout = aiohttp.ClientTimeout(total=30)  # Shorter timeout for testing
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=data) as response:
                response.raise_for_status()
                response_json = await response.json()

                print(f"Ollama Raw Response Status: {response.status}")
                print(f"Ollama Raw Response Headers: {response.headers}")
                print(f"Ollama Raw Response JSON: {response_json}")

                return response_json

    except Exception as e:
        print(f"❌ Simplified LLM interface failed: {e}")
        import traceback

        traceback.print_exc()
        return None


async def test_with_retry_mechanism():
    """Test the same logic but using the retry mechanism"""
    print("\n🔄 Testing with retry mechanism...")

    # Import the retry mechanism
    from src.retry_mechanism import retry_network_operation

    async def make_llm_request():
        url = "http://127.0.0.1:11434/api/chat"
        headers = {"Content-Type": "application/json"}

        data = {
            "model": "artifish/llama3.2-uncensored:latest",
            "messages": [{"role": "user", "content": "Say hello with retry"}],
            "stream": False,
            "temperature": 0.7,
            "format": "",
        }

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=data) as response:
                response.raise_for_status()
                response_json = await response.json()

                print(
                    f"   Retry mechanism response: {response_json.get('message', {}).get('content', 'No content')}"
                )
                return response_json

    try:
        result = await retry_network_operation(make_llm_request)
        print("✅ Retry mechanism test successful!")
        return result
    except Exception as e:
        print(f"❌ Retry mechanism test failed: {e}")
        import traceback

        traceback.print_exc()
        return None


async def main():
    """Run tests to isolate the issue"""
    print("🚀 LLM Interface Direct Test")
    print("=" * 40)

    # Test without retry
    simple_result = await test_llm_interface_simplified()

    # Test with retry mechanism
    retry_result = await test_with_retry_mechanism()

    if simple_result and retry_result:
        print("\n✅ Both simplified and retry tests work!")
        print("   The issue must be elsewhere in the AutoBot code.")
    elif simple_result and not retry_result:
        print("\n🚨 Retry mechanism is the problem!")
    elif not simple_result:
        print("\n🚨 Basic aiohttp logic is the problem!")


if __name__ == "__main__":
    asyncio.run(main())
