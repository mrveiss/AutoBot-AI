#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Simple test to verify ChatWorkflowManager without KB blocking
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Setup logging
logging.basicConfig(level=logging.INFO)


async def test_chat():
    """Test the chat workflow with a simple message"""
    from src.chat_workflow import process_chat_message

    try:
        print("Testing chat workflow...")
        result = await asyncio.wait_for(
            process_chat_message("hello", "test-chat"), timeout=10.0
        )

        print(f"✅ Success! Response: {result.response[:100]}...")
        print(f"   Knowledge Status: {result.knowledge_status.value}")
        print(f"   Message Type: {result.message_type.value}")
        print(f"   Processing Time: {result.processing_time:.2f}s")

    except asyncio.TimeoutError:
        print("❌ Test timed out after 10 seconds")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_chat())
