#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""

logger = logging.getLogger(__name__)

Test LLM interface with a simplified version bypassing retry mechanism
"""

import asyncio
import json
import sys
from pathlib import Path

import aiohttp
import logging

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


async def test_llm_interface_simplified():
    """Test LLM interface logic without retry mechanism"""
    logger.info("🤖 Testing simplified LLM interface logic...")

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

    logger.info("Ollama Request URL: %s", url)
    logger.info("Ollama Request Headers: %s", headers)
    logger.info("Ollama Request Data: %s", json.dumps(data, indent=2))

    try:
        # This is exactly the same logic as in LLM interface but without retry wrapper
        timeout = aiohttp.ClientTimeout(total=30)  # Shorter timeout for testing
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=data) as response:
                response.raise_for_status()
                response_json = await response.json()

                logger.info("Ollama Raw Response Status: %s", response.status)
                logger.info("Ollama Raw Response Headers: %s", response.headers)
                logger.info("Ollama Raw Response JSON: %s", response_json)

                return response_json

    except Exception as e:
        logger.info("❌ Simplified LLM interface failed: %s", e)
        import traceback

        traceback.print_exc()
        return None


async def test_with_retry_mechanism():
    """Test the same logic but using the retry mechanism"""
    logger.info("\n🔄 Testing with retry mechanism...")

    # Import the retry mechanism
    from retry_mechanism import retry_network_operation

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

                logger.info(
                    f"   Retry mechanism response: {response_json.get('message', {}).get('content', 'No content')}"
                )
                return response_json

    try:
        result = await retry_network_operation(make_llm_request)
        logger.info("✅ Retry mechanism test successful!")
        return result
    except Exception as e:
        logger.info("❌ Retry mechanism test failed: %s", e)
        import traceback

        traceback.print_exc()
        return None


async def main():
    """Run tests to isolate the issue"""
    logger.info("🚀 LLM Interface Direct Test")
    logger.info("=" * 40)

    # Test without retry
    simple_result = await test_llm_interface_simplified()

    # Test with retry mechanism
    retry_result = await test_with_retry_mechanism()

    if simple_result and retry_result:
        logger.info("\n✅ Both simplified and retry tests work!")
        logger.info("   The issue must be elsewhere in the AutoBot code.")
    elif simple_result and not retry_result:
        logger.info("\n🚨 Retry mechanism is the problem!")
    elif not simple_result:
        logger.info("\n🚨 Basic aiohttp logic is the problem!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
