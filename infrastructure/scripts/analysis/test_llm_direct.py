#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test LLM interface directly to see if it's hanging
"""

import asyncio
import sys
import time
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.agents.llm_failsafe_agent import get_robust_llm_response


async def test_llm_direct():
    """Test LLM directly with a simple prompt"""
    print("🤖 Testing LLM Failsafe Agent directly...")

    start_time = time.time()

    try:
        # Simple test prompt
        prompt = "Say hello back to the user."

        print(f"   Sending prompt: {prompt}")
        print("   Waiting for response...")

        # Get response with 15 second timeout to see if it's faster than 30s
        response = await asyncio.wait_for(
            get_robust_llm_response(prompt, context={"test": True}), timeout=15.0
        )

        elapsed = time.time() - start_time

        print(f"✅ LLM response received in {elapsed:.2f}s:")
        print(f"   Tier used: {response.tier_used.value}")
        print(f"   Model: {response.model_used}")
        print(f"   Success: {response.success}")
        print(f"   Content: {response.content[:100]}...")
        print(f"   Warnings: {response.warnings}")

        return True

    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        print(f"❌ LLM request timed out after {elapsed:.2f}s")
        return False

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ LLM request failed after {elapsed:.2f}s: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_classification_direct():
    """Test classification agent directly"""
    print("\n🔍 Testing Classification Agent directly...")

    start_time = time.time()

    try:
        from src.agents.classification_agent import ClassificationAgent

        agent = ClassificationAgent()

        print("   Classifying 'hello'...")

        # Test with shorter timeout to isolate the issue
        result = await asyncio.wait_for(agent.classify_request("hello"), timeout=10.0)

        elapsed = time.time() - start_time

        print(f"✅ Classification completed in {elapsed:.2f}s:")
        print(f"   Complexity: {result.complexity.value}")
        print(f"   Confidence: {result.confidence}")
        print(f"   Reasoning: {result.reasoning[:50]}...")

        return True

    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        print(f"❌ Classification timed out after {elapsed:.2f}s")
        return False

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ Classification failed after {elapsed:.2f}s: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_kb_search():
    """Test knowledge base search directly"""
    print("\n📚 Testing Knowledge Base search...")

    start_time = time.time()

    try:
        from src.agents import get_kb_librarian

        kb_librarian = get_kb_librarian()

        print("   Searching KB for 'hello'...")

        # Test KB search with timeout
        result = await asyncio.wait_for(
            kb_librarian.search_knowledge_base(
                query="hello", max_results=5, threshold=0.1
            ),
            timeout=8.0,
        )

        elapsed = time.time() - start_time

        print(f"✅ KB search completed in {elapsed:.2f}s:")
        if result and result.get("documents"):
            print(f"   Found {len(result['documents'])} documents")
        else:
            print("   No documents found")

        return True

    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        print(f"❌ KB search timed out after {elapsed:.2f}s")
        return False

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ KB search failed after {elapsed:.2f}s: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Run all direct tests to isolate the hanging component"""
    print("🚀 AutoBot Direct Component Test")
    print("=" * 50)

    # Test each component individually with timeouts
    tests = [
        ("Classification Agent", test_classification_direct()),
        ("Knowledge Base Search", test_kb_search()),
        ("LLM Failsafe Agent", test_llm_direct()),
    ]

    for test_name, test_coro in tests:
        print(f"\n📋 Running {test_name}...")
        try:
            success = await test_coro
            if not success:
                print(f"🚨 {test_name} is the likely culprit!")
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")

    print("\n" + "=" * 50)
    print("🔍 Test completed. Check above for timeouts or failures.")


if __name__ == "__main__":
    asyncio.run(main())
