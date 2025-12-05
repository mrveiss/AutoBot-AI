#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test when research agent is disabled
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Setup logging
logging.basicConfig(level=logging.INFO)


async def test_research_disabled():
    """Test behavior when research is disabled"""
    from src.chat_workflow import ChatWorkflowManager

    print("=== Testing Research Agent Disabled Scenario ===\n")

    # Create workflow manager with research disabled
    workflow = ChatWorkflowManager()
    workflow.web_research_enabled = False  # Simulate disabled research

    try:
        print("Testing unknown topic with research disabled...")
        result = await asyncio.wait_for(
            workflow.process_message("tell me about quantum computing in 2024", "test-chat"),
            timeout=15.0
        )

        print(f"✅ Response: {result.response}")
        print(f"   Knowledge Status: {result.knowledge_status.value}")
        print(f"   Processing Time: {result.processing_time:.2f}s\n")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_research_disabled())
