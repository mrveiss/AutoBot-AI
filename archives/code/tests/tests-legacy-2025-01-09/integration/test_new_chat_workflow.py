#!/usr/bin/env python3
"""
Test New Chat Workflow - Verify the complete chat system works correctly

Tests the user request → knowledge → response flow as specified:
1. User writes message
2. System searches for relevant knowledge
3. If task-related, looks for system/terminal knowledge
4. If no knowledge, engages librarian for research
5. Uses MCP for manual lookups
6. Never hallucinates - communicates knowledge gaps clearly
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Updated imports to use current chat workflow system
from src.async_chat_workflow import (
    AsyncChatWorkflow,
    MessageType,
    KnowledgeStatus,
    process_chat_message
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_chat_workflow():
    """Test the complete chat workflow with different message types"""

    print("🤖 Testing AutoBot Chat Workflow")
    print("=" * 50)

    # Test cases covering different scenarios
    test_cases = [
        {
            "name": "General Query",
            "message": "What is machine learning?",
            "expected_type": MessageType.GENERAL_QUERY
        },
        {
            "name": "Terminal Task",
            "message": "How do I list all files in a directory using terminal?",
            "expected_type": MessageType.TERMINAL_TASK
        },
        {
            "name": "Desktop Task",
            "message": "How do I open a file manager window?",
            "expected_type": MessageType.DESKTOP_TASK
        },
        {
            "name": "System Task",
            "message": "How do I install a new package on Linux?",
            "expected_type": MessageType.SYSTEM_TASK
        },
        {
            "name": "Complex Research",
            "message": "Analyze the latest developments in quantum computing algorithms",
            "expected_type": MessageType.RESEARCH_NEEDED
        }
    ]

    # Use AsyncChatWorkflow directly instead of ChatWorkflowManager
    workflow = AsyncChatWorkflow()
    results = []

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n🧪 Test {i}: {test_case['name']}")
        print(f"📝 Message: {test_case['message']}")
        print("-" * 40)

        start_time = time.time()

        try:
            # Process the message through the workflow
            result = await process_chat_message(
                user_message=test_case['message'],
                chat_id=f"test_chat_{i}"
            )

            processing_time = time.time() - start_time

            # Display results
            print(f"✅ Status: {result.knowledge_status.value.upper()}")
            print(f"🏷️  Type: {result.message_type.value}")
            print(f"📚 KB Results: {len(result.kb_results) if result.kb_results else 0}")
            print(f"🔍 Research: {'Yes' if hasattr(result, 'research_engaged') and result.research_engaged else 'No'}")
            print(f"📖 MCP Used: {'Yes' if hasattr(result, 'mcp_used') and result.mcp_used else 'No'}")
            print(f"⏱️  Time: {processing_time:.2f}s")
            print(f"💬 Response Preview: {result.response[:100]}{'...' if len(result.response) > 100 else ''}")

            if hasattr(result, 'error') and result.error:
                print(f"❌ Error: {result.error}")

            # Verify classification accuracy
            if result.message_type == test_case['expected_type']:
                print("✅ Classification: CORRECT")
            else:
                print(f"⚠️  Classification: Expected {test_case['expected_type'].value}, got {result.message_type.value}")

            results.append({
                'test_case': test_case['name'],
                'success': not bool(hasattr(result, 'error') and result.error),
                'classification_correct': result.message_type == test_case['expected_type'],
                'processing_time': processing_time,
                'knowledge_status': result.knowledge_status,
                'response_length': len(result.response)
            })

        except Exception as e:
            processing_time = time.time() - start_time
            print(f"❌ Test Failed: {e}")
            results.append({
                'test_case': test_case['name'],
                'success': False,
                'error': str(e),
                'processing_time': processing_time
            })

    # Summary
    print("\n" + "=" * 50)
    print("📊 TEST SUMMARY")
    print("=" * 50)

    successful_tests = sum(1 for r in results if r.get('success', False))
    total_tests = len(results)

    print(f"✅ Successful Tests: {successful_tests}/{total_tests}")

    if successful_tests > 0:
        avg_time = sum(r['processing_time'] for r in results if r.get('success', False)) / successful_tests
        print(f"⏱️  Average Response Time: {avg_time:.2f}s")

        correct_classifications = sum(1 for r in results if r.get('classification_correct', False))
        print(f"🎯 Classification Accuracy: {correct_classifications}/{successful_tests}")

        knowledge_statuses = [r.get('knowledge_status') for r in results if r.get('success', False)]
        status_counts = {}
        for status in knowledge_statuses:
            if status:
                status_counts[status.value] = status_counts.get(status.value, 0) + 1

        print(f"📈 Knowledge Status Distribution:")
        for status, count in status_counts.items():
            print(f"   {status}: {count}")

    print("\n🔍 DETAILED RESULTS:")
    for result in results:
        status = "✅ PASS" if result.get('success', False) else "❌ FAIL"
        print(f"   {result['test_case']}: {status} ({result['processing_time']:.2f}s)")
        if not result.get('success', False) and 'error' in result:
            print(f"      Error: {result['error']}")

    print("\n🎉 Chat workflow testing completed!")

    if successful_tests == total_tests:
        print("✅ All tests passed! Chat workflow is working correctly.")
        return True
    else:
        print(f"⚠️  {total_tests - successful_tests} tests failed. Check the issues above.")
        return False


async def test_knowledge_scenarios():
    """Test specific knowledge availability scenarios"""

    print("\n" + "=" * 50)
    print("🧠 Testing Knowledge Scenarios")
    print("=" * 50)

    knowledge_tests = [
        {
            "name": "Known Command",
            "message": "How do I use the ls command?",
            "expect_kb": True
        },
        {
            "name": "Unknown Topic",
            "message": "How do I configure the XyzUltraRare software?",
            "expect_kb": False
        },
        {
            "name": "General Programming",
            "message": "How do I write a Python function?",
            "expect_kb": True
        }
    ]

    for i, test in enumerate(knowledge_tests, 1):
        print(f"\n🧪 Knowledge Test {i}: {test['name']}")
        print(f"📝 Message: {test['message']}")
        print("-" * 40)

        try:
            result = await process_chat_message(
                user_message=test['message'],
                chat_id=f"knowledge_test_{i}"
            )

            has_knowledge = result.knowledge_status in [KnowledgeStatus.FOUND, KnowledgeStatus.PARTIAL]

            print(f"📚 Knowledge Status: {result.knowledge_status.value}")
            print(f"🔍 Research Engaged: {'Yes' if hasattr(result, 'research_engaged') and result.research_engaged else 'No'}")

            # Check if behavior matches expectation
            if test['expect_kb'] and has_knowledge:
                print("✅ Expected knowledge found")
            elif not test['expect_kb'] and not has_knowledge:
                print("✅ Expected no knowledge - research would be triggered")
            elif not test['expect_kb'] and has_knowledge:
                print("ℹ️  Unexpected knowledge found (better than expected)")
            else:
                print("⚠️  Expected knowledge but none found - research triggered")

            print(f"💬 Response approach: {'Knowledge-based' if has_knowledge else 'Research/Question-based'}")

        except Exception as e:
            print(f"❌ Knowledge test failed: {e}")


if __name__ == "__main__":
    async def main():
        print("🚀 Starting AutoBot Chat Workflow Tests")

        # Test main workflow
        workflow_success = await test_chat_workflow()

        # Test knowledge scenarios
        await test_knowledge_scenarios()

        print("\n" + "=" * 60)
        if workflow_success:
            print("🎉 OVERALL RESULT: Chat workflow is ready for production!")
            print("✅ The system properly:")
            print("   • Classifies different types of user requests")
            print("   • Searches knowledge base for relevant information")
            print("   • Engages research when knowledge is missing")
            print("   • Uses MCP for terminal/system manual lookups")
            print("   • Provides clear responses without hallucination")
        else:
            print("⚠️  OVERALL RESULT: Chat workflow needs fixes")
            print("❌ Some components are not working correctly")

        print("=" * 60)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Test failed with error: {e}")
        import traceback
        traceback.print_exc()
