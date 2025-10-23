#!/usr/bin/env python3
"""
Quick Test Runner for Memory Graph Integration Tests

This script provides a simple execution environment for Memory Graph integration tests
without the event loop conflicts from pytest-asyncio.

Usage:
    python tests/run_memory_graph_integration_tests.py
    python tests/run_memory_graph_integration_tests.py --verbose
    python tests/run_memory_graph_integration_tests.py --test chat
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.autobot_memory_graph import AutoBotMemoryGraph
from src.chat_history_manager import ChatHistoryManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IntegrationTestRunner:
    """Simple test runner for Memory Graph integration tests"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.passed = 0
        self.failed = 0
        self.errors = []

    def print_header(self, title: str):
        """Print test section header"""
        print(f"\n{'=' * 80}")
        print(f"{title}")
        print(f"{'=' * 80}")

    def print_test(self, test_name: str, status: str, message: str = ""):
        """Print test result"""
        status_symbol = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_symbol} {test_name}: {status}")
        if message and self.verbose:
            print(f"   {message}")

    async def test_basic_entity_creation(self):
        """Test basic entity creation and retrieval"""
        try:
            # Initialize Memory Graph
            memory_graph = AutoBotMemoryGraph(
                redis_host="172.16.168.23",
                redis_port=6379,
                database=9
            )

            initialized = await memory_graph.initialize()
            if not initialized:
                self.print_test("Basic Entity Creation", "FAIL", "Memory Graph initialization failed")
                self.failed += 1
                return

            # Create test entity
            entity = await memory_graph.create_entity(
                entity_type="conversation",
                name="Test Integration Conversation",
                observations=["Test observation 1", "Test observation 2"],
                tags=["integration_test"]
            )

            # Verify entity created
            assert entity is not None
            assert entity["type"] == "conversation"
            assert len(entity["observations"]) == 2

            # Retrieve entity
            retrieved = await memory_graph.get_entity(entity_name="Test Integration Conversation")
            assert retrieved is not None
            assert retrieved["name"] == "Test Integration Conversation"

            # Cleanup
            await memory_graph.delete_entity("Test Integration Conversation")
            await memory_graph.close()

            self.print_test("Basic Entity Creation", "PASS", "Entity created, retrieved, and deleted successfully")
            self.passed += 1

        except Exception as e:
            self.print_test("Basic Entity Creation", "FAIL", f"Error: {e}")
            self.failed += 1
            self.errors.append(("Basic Entity Creation", str(e)))

    async def test_chat_integration(self):
        """Test Chat History Manager integration with Memory Graph"""
        try:
            import tempfile
            import os

            # Create temporary directory for test
            with tempfile.TemporaryDirectory() as tmp_dir:
                # Initialize Chat History Manager
                chat_manager = ChatHistoryManager(
                    history_file=os.path.join(tmp_dir, "test_history.json"),
                    use_redis=False
                )

                # Create session
                session_id = "test-integration-session"
                session = await chat_manager.create_session(
                    session_id=session_id,
                    title="Integration Test Session"
                )

                assert session is not None
                assert session["id"] == session_id

                # Add messages
                await chat_manager.add_message(
                    sender="user",
                    text="Test message 1",
                    session_id=session_id
                )

                await chat_manager.add_message(
                    sender="bot",
                    text="Test response 1",
                    session_id=session_id
                )

                # Verify messages saved
                messages = await chat_manager.get_session_messages(session_id)
                assert len(messages) == 2

                # Cleanup
                await chat_manager.clear_history()

                self.print_test("Chat Integration", "PASS", "Session created, messages added, verified")
                self.passed += 1

        except Exception as e:
            self.print_test("Chat Integration", "FAIL", f"Error: {e}")
            self.failed += 1
            self.errors.append(("Chat Integration", str(e)))

    async def test_conversation_entity_lifecycle(self):
        """Test complete conversation entity lifecycle"""
        try:
            # Initialize systems
            memory_graph = AutoBotMemoryGraph(
                redis_host="172.16.168.23",
                redis_port=6379,
                database=9
            )

            initialized = await memory_graph.initialize()
            if not initialized:
                self.print_test("Conversation Entity Lifecycle", "SKIP", "Memory Graph unavailable")
                return

            # Create conversation entity
            session_id = "lifecycle-test-session"
            entity = await memory_graph.create_conversation_entity(
                session_id=session_id,
                metadata={"purpose": "lifecycle_test"}
            )

            assert entity is not None
            assert entity["type"] == "conversation"

            # Add observations
            await memory_graph.add_observations(
                entity_name=entity["name"],
                observations=["User started conversation", "Discussion about Redis"]
            )

            # Verify observations added
            updated_entity = await memory_graph.get_entity(entity_name=entity["name"])
            assert len(updated_entity["observations"]) >= 2

            # Cleanup
            await memory_graph.delete_entity(entity["name"])
            await memory_graph.close()

            self.print_test("Conversation Entity Lifecycle", "PASS", "Full lifecycle completed")
            self.passed += 1

        except Exception as e:
            self.print_test("Conversation Entity Lifecycle", "FAIL", f"Error: {e}")
            self.failed += 1
            self.errors.append(("Conversation Entity Lifecycle", str(e)))

    async def test_search_functionality(self):
        """Test entity search functionality"""
        try:
            memory_graph = AutoBotMemoryGraph(
                redis_host="172.16.168.23",
                redis_port=6379,
                database=9
            )

            initialized = await memory_graph.initialize()
            if not initialized:
                self.print_test("Search Functionality", "SKIP", "Memory Graph unavailable")
                return

            # Create test entities
            await memory_graph.create_entity(
                entity_type="feature",
                name="Search Test Feature 1",
                observations=["Testing search functionality"]
            )

            await memory_graph.create_entity(
                entity_type="feature",
                name="Search Test Feature 2",
                observations=["Another search test"]
            )

            # Search for entities
            results = await memory_graph.search_entities("search test", limit=10)

            assert len(results) >= 2

            # Cleanup
            for result in results:
                if "Search Test" in result["name"]:
                    await memory_graph.delete_entity(result["name"])

            await memory_graph.close()

            self.print_test("Search Functionality", "PASS", f"Found {len(results)} matching entities")
            self.passed += 1

        except Exception as e:
            self.print_test("Search Functionality", "FAIL", f"Error: {e}")
            self.failed += 1
            self.errors.append(("Search Functionality", str(e)))

    async def test_relation_creation(self):
        """Test entity relation creation"""
        try:
            memory_graph = AutoBotMemoryGraph(
                redis_host="172.16.168.23",
                redis_port=6379,
                database=9
            )

            initialized = await memory_graph.initialize()
            if not initialized:
                self.print_test("Relation Creation", "SKIP", "Memory Graph unavailable")
                return

            # Create two entities
            entity1 = await memory_graph.create_entity(
                entity_type="bug_fix",
                name="Relation Test Bug",
                observations=["Test bug"]
            )

            entity2 = await memory_graph.create_entity(
                entity_type="decision",
                name="Relation Test Decision",
                observations=["Fix decision"]
            )

            # Create relation
            relation = await memory_graph.create_relation(
                from_entity=entity2["name"],
                to_entity=entity1["name"],
                relation_type="fixes"
            )

            assert relation is not None

            # Verify relation exists
            related = await memory_graph.get_related_entities(
                entity_name=entity2["name"],
                relation_type="fixes"
            )

            assert len(related) > 0

            # Cleanup
            await memory_graph.delete_entity(entity1["name"])
            await memory_graph.delete_entity(entity2["name"])
            await memory_graph.close()

            self.print_test("Relation Creation", "PASS", "Relation created and verified")
            self.passed += 1

        except Exception as e:
            self.print_test("Relation Creation", "FAIL", f"Error: {e}")
            self.failed += 1
            self.errors.append(("Relation Creation", str(e)))

    async def run_all_tests(self):
        """Run all integration tests"""
        self.print_header("Memory Graph Integration Tests - Quick Runner")

        tests = [
            ("Basic Entity Creation", self.test_basic_entity_creation),
            ("Chat Integration", self.test_chat_integration),
            ("Conversation Entity Lifecycle", self.test_conversation_entity_lifecycle),
            ("Search Functionality", self.test_search_functionality),
            ("Relation Creation", self.test_relation_creation),
        ]

        for test_name, test_func in tests:
            try:
                await test_func()
            except Exception as e:
                self.print_test(test_name, "ERROR", f"Unexpected error: {e}")
                self.failed += 1
                self.errors.append((test_name, str(e)))

        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print test execution summary"""
        print(f"\n{'=' * 80}")
        print(f"TEST SUMMARY")
        print(f"{'=' * 80}")
        print(f"Total Tests: {self.passed + self.failed}")
        print(f"✅ Passed: {self.passed}")
        print(f"❌ Failed: {self.failed}")

        if self.errors:
            print(f"\n{'=' * 80}")
            print(f"ERRORS:")
            print(f"{'=' * 80}")
            for test_name, error in self.errors:
                print(f"\n{test_name}:")
                print(f"  {error}")

        print(f"\n{'=' * 80}")
        if self.failed == 0:
            print("✅ ALL TESTS PASSED")
        else:
            print(f"❌ {self.failed} TEST(S) FAILED")
        print(f"{'=' * 80}\n")

        return 0 if self.failed == 0 else 1


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Run Memory Graph integration tests")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--test", "-t", choices=["chat", "search", "relations", "all"],
                       default="all", help="Specific test to run")

    args = parser.parse_args()

    runner = IntegrationTestRunner(verbose=args.verbose)

    if args.test == "all":
        return await runner.run_all_tests()
    elif args.test == "chat":
        runner.print_header("Chat Integration Test")
        await runner.test_chat_integration()
        await runner.test_conversation_entity_lifecycle()
        runner.print_summary()
        return 0 if runner.failed == 0 else 1
    elif args.test == "search":
        runner.print_header("Search Functionality Test")
        await runner.test_search_functionality()
        runner.print_summary()
        return 0 if runner.failed == 0 else 1
    elif args.test == "relations":
        runner.print_header("Relation Creation Test")
        await runner.test_relation_creation()
        runner.print_summary()
        return 0 if runner.failed == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
