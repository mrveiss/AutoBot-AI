#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test the yes/no research dialogue workflow
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Setup logging
logging.basicConfig(level=logging.INFO)


async def test_research_dialogue():
    """Test the research dialogue workflow"""
    from src.chat_workflow import process_chat_message

    print("=== Testing Research Dialogue Workflow ===\n")

    # Test 1: Unknown topic that should trigger research question
    try:
        print("1. Testing unknown topic (should ask for research)...")
        result = await asyncio.wait_for(
            process_chat_message(
                "tell me about quantum computing in 2024", "test-chat"
            ),
            timeout=15.0,
        )

        print(f"✅ Response: {result.response}")
        print(f"   Knowledge Status: {result.knowledge_status.value}")
        print(f"   Processing Time: {result.processing_time:.2f}s\n")

    except Exception as e:
        print(f"❌ Test 1 failed: {e}\n")

    # Test 2: "Yes" response
    try:
        print("2. Testing 'yes' response...")
        result = await asyncio.wait_for(
            process_chat_message("yes", "test-chat"), timeout=10.0
        )

        print(f"✅ Response: {result.response}")
        print(f"   Knowledge Status: {result.knowledge_status.value}\n")

    except Exception as e:
        print(f"❌ Test 2 failed: {e}\n")

    # Test 3: "No" response
    try:
        print("3. Testing 'no' response...")
        result = await asyncio.wait_for(
            process_chat_message("no", "test-chat"), timeout=10.0
        )

        print(f"✅ Response: {result.response}")
        print(f"   Knowledge Status: {result.knowledge_status.value}\n")

    except Exception as e:
        print(f"❌ Test 3 failed: {e}\n")


if __name__ == "__main__":
    asyncio.run(test_research_dialogue())
