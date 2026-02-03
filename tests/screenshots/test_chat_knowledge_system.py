#!/usr/bin/env python3
"""
Comprehensive test for the Chat Knowledge Management System
Tests the complete integration of chat context, file associations, and knowledge compilation
"""

import asyncio
import json
import logging
import os
import tempfile
import time
from datetime import datetime

import aiohttp
import pytest

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8001"


class ChatKnowledgeSystemTester:
    """Comprehensive test suite for chat knowledge management system"""

    def __init__(self):
        self.session = None
        self.test_chat_id = None
        self.test_files = []

    async def setup(self):
        """Initialize test session"""
        self.session = aiohttp.ClientSession()
        logger.info("🚀 Starting Chat Knowledge Management System Test")

        # Create a test chat
        async with self.session.post(f"{BASE_URL}/api/chats/new") as response:
            if response.status == 200:
                data = await response.json()
                self.test_chat_id = data.get("chatId")
                logger.info(f"✅ Created test chat: {self.test_chat_id}")
            else:
                raise Exception(f"Failed to create test chat: {response.status}")

    async def cleanup(self):
        """Clean up test resources"""
        # Clean up test files
        for file_path in self.test_files:
            try:
                os.remove(file_path)
                logger.info(f"🧹 Cleaned up test file: {file_path}")
            except OSError:
                pass

        # Close session
        if self.session:
            await self.session.close()

        logger.info("🧹 Test cleanup completed")

    async def test_chat_context_creation(self):
        """Test 1: Chat context creation and topic setting"""
        logger.info("📋 Test 1: Chat Context Creation")

        context_data = {
            "chat_id": self.test_chat_id,
            "topic": "Python Development Best Practices",
            "keywords": ["python", "fastapi", "async", "testing"],
        }

        async with self.session.post(
            f"{BASE_URL}/api/chat_knowledge/context/create", json=context_data
        ) as response:
            if response.status == 200:
                data = await response.json()
                assert data["success"], "Context creation should succeed"
                logger.info("✅ Chat context created successfully")
                return True
            else:
                logger.error(f"❌ Context creation failed: {response.status}")
                return False

    async def test_file_association(self):
        """Test 2: File upload and association with chat"""
        logger.info("📋 Test 2: File Association")

        # Create a temporary test file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                """
# Test Python file for chat knowledge system
def test_function():
    '''Example function for testing'''
    return "Hello from test file"

if __name__ == "__main__":
    print(test_function())
"""
            )
            test_file_path = f.name

        self.test_files.append(test_file_path)

        # Upload file to chat
        try:
            with open(test_file_path, "rb") as f:
                data = aiohttp.FormData()
                data.add_field(
                    "file", f, filename="test_code.py", content_type="text/plain"
                )
                data.add_field("association_type", "upload")

                async with self.session.post(
                    f"{BASE_URL}/api/chat_knowledge/files/upload/{self.test_chat_id}",
                    data=data,
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        assert result["success"], "File upload should succeed"
                        logger.info("✅ File associated with chat successfully")
                        return True
                    else:
                        logger.error(f"❌ File association failed: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"❌ File association error: {e}")
            return False

    async def test_temporary_knowledge_addition(self):
        """Test 3: Add temporary knowledge to chat"""
        logger.info("📋 Test 3: Temporary Knowledge Addition")

        knowledge_items = [
            {
                "content": "FastAPI is a modern web framework for Python that provides automatic API documentation and high performance.",
                "metadata": {"category": "framework", "importance": "high"},
            },
            {
                "content": "Use async/await for I/O operations to improve performance in FastAPI applications.",
                "metadata": {"category": "performance", "importance": "medium"},
            },
            {
                "content": "Pydantic models in FastAPI provide automatic request validation and serialization.",
                "metadata": {"category": "validation", "importance": "high"},
            },
        ]

        success_count = 0
        for item in knowledge_items:
            knowledge_data = {
                "chat_id": self.test_chat_id,
                "content": item["content"],
                "metadata": item["metadata"],
            }

            async with self.session.post(
                f"{BASE_URL}/api/chat_knowledge/knowledge/add_temporary",
                json=knowledge_data,
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    if result["success"]:
                        success_count += 1
                        logger.info(f"✅ Knowledge item {success_count} added")
                    else:
                        logger.error(f"❌ Knowledge item failed: {result}")
                else:
                    logger.error(f"❌ Knowledge addition failed: {response.status}")

        if success_count == len(knowledge_items):
            logger.info(f"✅ All {success_count} knowledge items added successfully")
            return True
        else:
            logger.error(f"❌ Only {success_count}/{len(knowledge_items)} items added")
            return False

    async def test_knowledge_retrieval_and_decisions(self):
        """Test 4: Retrieve pending knowledge and apply decisions"""
        logger.info("📋 Test 4: Knowledge Retrieval and Decisions")

        # Get pending knowledge items
        async with self.session.get(
            f"{BASE_URL}/api/chat_knowledge/knowledge/pending/{self.test_chat_id}"
        ) as response:
            if response.status == 200:
                data = await response.json()
                if data["success"]:
                    pending_items = data["pending_items"]
                    logger.info(
                        f"✅ Retrieved {len(pending_items)} pending knowledge items"
                    )

                    # Apply decisions to knowledge items
                    decisions = [
                        ("add_to_kb", "Adding FastAPI framework knowledge"),
                        ("keep_temporary", "Keeping async/await tip for session"),
                        ("add_to_kb", "Adding Pydantic validation knowledge"),
                    ]

                    success_count = 0
                    for i, (decision, reason) in enumerate(decisions):
                        if i < len(pending_items):
                            decision_data = {
                                "chat_id": self.test_chat_id,
                                "knowledge_id": pending_items[i]["id"],
                                "decision": decision,
                            }

                            async with self.session.post(
                                f"{BASE_URL}/api/chat_knowledge/knowledge/decide",
                                json=decision_data,
                            ) as decision_response:
                                if decision_response.status == 200:
                                    result = await decision_response.json()
                                    if result["success"]:
                                        success_count += 1
                                        logger.info(f"✅ Decision applied: {reason}")
                                    else:
                                        logger.error(f"❌ Decision failed: {result}")
                                else:
                                    logger.error(
                                        f"❌ Decision request failed: {decision_response.status}"
                                    )

                    if success_count == len(decisions):
                        logger.info("✅ All knowledge decisions applied successfully")
                        return True
                    else:
                        logger.error(
                            f"❌ Only {success_count}/{len(decisions)} decisions applied"
                        )
                        return False
                else:
                    logger.error(f"❌ Failed to get pending knowledge: {data}")
                    return False
            else:
                logger.error(f"❌ Knowledge retrieval failed: {response.status}")
                return False

    async def test_chat_search(self):
        """Test 5: Search knowledge within chat context"""
        logger.info("📋 Test 5: Chat Knowledge Search")

        search_queries = [
            "FastAPI framework",
            "async performance",
            "Pydantic validation",
        ]

        success_count = 0
        for query in search_queries:
            search_data = {
                "query": query,
                "chat_id": self.test_chat_id,
                "include_temporary": True,
            }

            async with self.session.post(
                f"{BASE_URL}/api/chat_knowledge/search", json=search_data
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data["success"]:
                        results = data["results"]
                        logger.info(
                            f"✅ Search '{query}' returned {len(results)} results"
                        )
                        success_count += 1

                        # Log first result for verification
                        if results:
                            logger.info(
                                f"   Top result: {results[0]['content'][:100]}..."
                            )
                    else:
                        logger.error(f"❌ Search failed: {data}")
                else:
                    logger.error(f"❌ Search request failed: {response.status}")

        if success_count == len(search_queries):
            logger.info("✅ All search queries completed successfully")
            return True
        else:
            logger.error(
                f"❌ Only {success_count}/{len(search_queries)} searches succeeded"
            )
            return False

    async def test_chat_compilation(self):
        """Test 6: Compile entire chat to knowledge base"""
        logger.info("📋 Test 6: Chat Compilation")

        # First, send a few messages to the chat to create conversation history
        chat_messages = [
            "What are the best practices for FastAPI development?",
            "How do I handle async operations efficiently?",
            "Can you explain Pydantic model validation?",
        ]

        # Add messages to create chat history (simulate conversation)
        for message in chat_messages:
            message_data = {"message": message}
            async with self.session.post(
                f"{BASE_URL}/api/chats/{self.test_chat_id}/message", json=message_data
            ) as response:
                if response.status == 200:
                    logger.info(f"✅ Message sent: {message[:50]}...")
                else:
                    logger.warning(f"⚠️ Message failed: {response.status}")

        # Wait a moment for message processing
        await asyncio.sleep(2)

        # Now compile the chat
        compile_data = {
            "chat_id": self.test_chat_id,
            "title": "FastAPI Development Best Practices - Compiled Knowledge",
            "include_system_messages": False,
        }

        async with self.session.post(
            f"{BASE_URL}/api/chat_knowledge/compile", json=compile_data
        ) as response:
            if response.status == 200:
                data = await response.json()
                if data["success"]:
                    compiled = data["compiled"]
                    logger.info("✅ Chat compiled successfully to knowledge base")
                    logger.info(f"   Title: {compiled.get('title', 'N/A')}")
                    logger.info(f"   KB ID: {compiled.get('kb_id', 'N/A')}")
                    logger.info(f"   Messages: {compiled.get('message_count', 0)}")
                    return True
                else:
                    logger.error(f"❌ Compilation failed: {data}")
                    return False
            else:
                logger.error(f"❌ Compilation request failed: {response.status}")
                return False

    async def test_context_retrieval(self):
        """Test 7: Retrieve complete chat context"""
        logger.info("📋 Test 7: Context Retrieval")

        async with self.session.get(
            f"{BASE_URL}/api/chat_knowledge/context/{self.test_chat_id}"
        ) as response:
            if response.status == 200:
                data = await response.json()
                if data["success"]:
                    context = data["context"]
                    logger.info("✅ Chat context retrieved successfully")
                    logger.info(f"   Topic: {context.get('topic', 'N/A')}")
                    logger.info(f"   Keywords: {context.get('keywords', [])}")
                    logger.info(f"   Files: {context.get('file_count', 0)}")
                    logger.info(
                        f"   Temporary Knowledge: {context.get('temporary_knowledge_count', 0)}"
                    )
                    logger.info(
                        f"   Persistent Knowledge: {context.get('persistent_knowledge_count', 0)}"
                    )
                    return True
                else:
                    logger.error(f"❌ Context retrieval failed: {data}")
                    return False
            else:
                logger.error(f"❌ Context request failed: {response.status}")
                return False

    async def run_all_tests(self):
        """Run complete test suite"""
        logger.info("🎯 Starting Comprehensive Chat Knowledge Management Test")
        logger.info("=" * 80)

        tests = [
            ("Chat Context Creation", self.test_chat_context_creation),
            ("File Association", self.test_file_association),
            ("Temporary Knowledge Addition", self.test_temporary_knowledge_addition),
            ("Knowledge Decisions", self.test_knowledge_retrieval_and_decisions),
            ("Knowledge Search", self.test_chat_search),
            ("Chat Compilation", self.test_chat_compilation),
            ("Context Retrieval", self.test_context_retrieval),
        ]

        results = []
        for test_name, test_func in tests:
            try:
                logger.info("-" * 60)
                start_time = time.time()
                result = await test_func()
                duration = time.time() - start_time

                results.append((test_name, result, duration))
                status = "✅ PASSED" if result else "❌ FAILED"
                logger.info(f"{status} - {test_name} ({duration:.2f}s)")

                # Short delay between tests
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"❌ EXCEPTION in {test_name}: {e}")
                results.append((test_name, False, 0))

        # Print summary
        logger.info("=" * 80)
        logger.info("🎯 TEST SUMMARY")
        logger.info("=" * 80)

        passed = sum(1 for _, result, _ in results if result)
        total = len(results)

        for test_name, result, duration in results:
            status = "✅ PASS" if result else "❌ FAIL"
            logger.info(f"{status} {test_name} ({duration:.2f}s)")

        logger.info("-" * 80)
        logger.info(f"🎯 OVERALL RESULT: {passed}/{total} tests passed")

        if passed == total:
            logger.info(
                "🎉 ALL TESTS PASSED - Chat Knowledge Management System is fully functional!"
            )
        else:
            logger.warning(f"⚠️ {total - passed} tests failed - System needs attention")

        return passed == total


async def main():
    """Main test execution"""
    tester = ChatKnowledgeSystemTester()

    try:
        await tester.setup()
        success = await tester.run_all_tests()
        return success
    except Exception as e:
        logger.error(f"❌ Test execution failed: {e}")
        return False
    finally:
        await tester.cleanup()


if __name__ == "__main__":
    # Check if backend is running
    async def check_backend():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{BASE_URL}/api/system/health") as response:
                    if response.status == 200:
                        return True
        except Exception:
            pass
        return False

    # Run test
    if asyncio.run(check_backend()):
        logger.info("🚀 Backend is running - Starting tests")
        success = asyncio.run(main())
        exit(0 if success else 1)
    else:
        logger.error("❌ Backend is not running at http://localhost:8001")
        logger.error("Please start the backend with: ./run_agent.sh")
        exit(1)
