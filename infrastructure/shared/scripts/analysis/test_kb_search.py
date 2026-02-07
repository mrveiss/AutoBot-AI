#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test Knowledge Base Documentation Search
"""

import asyncio
import logging
import sys

# Add the project root to the Python path
sys.path.insert(0, "/home/kali/Desktop/AutoBot")

from src.chat_workflow import ChatWorkflowManager
from src.knowledge_base import KnowledgeBase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_kb_search():
    """Test knowledge base search functionality"""

    print("=== Testing Knowledge Base Search ===")

    # Test 1: Initialize Knowledge Base directly
    try:
        print("\n1. Testing Knowledge Base initialization...")
        kb = KnowledgeBase()
        await kb.ainit()

        # Get stats
        stats = await kb.get_stats()
        print(f"KB Stats: {stats}")

        # Test search for documentation
        print("\n2. Testing documentation search...")
        search_queries = [
            "docker deployment guide",
            "API documentation",
            "configuration setup",
            "installation guide",
            "troubleshooting",
        ]

        for query in search_queries:
            print(f"\nSearching for: '{query}'")
            try:
                results = await kb.search_legacy(query, n_results=3)
                print(f"  Found {len(results)} results")

                for i, result in enumerate(results):
                    content_preview = (
                        result["content"][:100] + "..."
                        if len(result["content"]) > 100
                        else result["content"]
                    )
                    print(f"  Result {i+1}: {content_preview}")
                    print(f"    Metadata: {result.get('metadata', {})}")
                    print(f"    Score: {result.get('score', 0.0)}")

            except Exception as e:
                print(f"  Error searching: {e}")

    except Exception as e:
        print(f"KB initialization failed: {e}")
        import traceback

        traceback.print_exc()

    # Test 2: Test Chat Workflow Manager
    try:
        print("\n\n=== Testing Chat Workflow Manager ===")
        workflow = ChatWorkflowManager()

        # Test documentation-related queries
        test_messages = [
            "How do I install AutoBot?",
            "Show me the API documentation",
            "What's in the configuration guide?",
            "Help with Docker deployment",
        ]

        for message in test_messages:
            print(f"\nTesting message: '{message}'")
            try:
                result = await workflow.process_message(message)
                print(f"  Message Type: {result.message_type}")
                print(f"  Knowledge Status: {result.knowledge_status}")
                print(f"  KB Results: {len(result.kb_results)}")
                print(f"  Response preview: {result.response[:200]}...")

                if result.kb_results:
                    print("  Knowledge Base results:")
                    for i, kb_result in enumerate(result.kb_results[:2]):
                        content_preview = kb_result.get("content", "")[:100]
                        print(f"    {i+1}: {content_preview}...")

            except Exception as e:
                print(f"  Error in workflow: {e}")
                import traceback

                traceback.print_exc()

    except Exception as e:
        print(f"Workflow initialization failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_kb_search())
