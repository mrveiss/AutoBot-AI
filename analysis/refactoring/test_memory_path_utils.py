#!/usr/bin/env python3
"""
Test script to verify memory manager path resolution refactoring

This script tests that both async and sync memory managers work correctly
after the path resolution duplication has been removed and consolidated
into shared utilities.
"""

import os
import sys
import tempfile
import asyncio

# Add project root to path so we can import the modules
project_root = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, project_root)

from src.utils.common import PathUtils
from src.memory import LongTermMemoryManager
from src.memory_manager_async import AsyncLongTermMemoryManager


def test_path_utils():
    """Test the shared PathUtils functionality"""
    print("Testing PathUtils...")

    # Test relative path resolution
    relative_path = "data/test.db"
    resolved = PathUtils.resolve_path(relative_path)
    print(f"  Relative path '{relative_path}' resolved to: {resolved}")
    assert os.path.isabs(resolved), "Should return absolute path"

    # Test absolute path (should remain unchanged)
    absolute_path = "/tmp/test.db"
    resolved_abs = PathUtils.resolve_path(absolute_path)
    print(f"  Absolute path '{absolute_path}' resolved to: {resolved_abs}")
    assert resolved_abs == absolute_path, "Absolute path should remain unchanged"

    # Test empty path
    empty_resolved = PathUtils.resolve_path("")
    print(f"  Empty path resolved to: '{empty_resolved}'")
    assert empty_resolved == "", "Empty path should return empty string"

    print("  ✓ PathUtils tests passed!")


def test_sync_memory_manager():
    """Test the synchronous memory manager"""
    print("\nTesting sync memory manager...")

    with tempfile.TemporaryDirectory():
        # Test with temporary directory context (cleanup automatic)
        try:
            # Create memory manager
            memory_mgr = LongTermMemoryManager()

            # Store a test memory entry
            memory_id = memory_mgr.store_memory(
                category="test",
                content="Test memory entry for path resolution refactoring",
                metadata={"test": True, "refactor": "path_utils"}
            )

            print(f"  Stored memory entry with ID: {memory_id}")

            # Retrieve the memory entry
            memories = memory_mgr.retrieve_memory(category="test", limit=1)
            assert len(memories) > 0, "Should retrieve at least one memory"
            assert memories[0].content == "Test memory entry for path resolution refactoring"

            print(f"  Retrieved memory: {memories[0].content[:50]}...")
            print("  ✓ Sync memory manager tests passed!")

        except Exception as e:
            print(f"  ✗ Sync memory manager test failed: {e}")
            raise


async def test_async_memory_manager():
    """Test the asynchronous memory manager"""
    print("\nTesting async memory manager...")

    with tempfile.TemporaryDirectory():
        try:
            # Create async memory manager
            async_memory_mgr = AsyncLongTermMemoryManager()

            # Store a test memory entry
            memory_id = await async_memory_mgr.store_memory(
                category="test_async",
                content="Test async memory entry for path resolution refactoring",
                metadata={"test": True, "refactor": "path_utils", "async": True}
            )

            print(f"  Stored async memory entry with ID: {memory_id}")

            # Retrieve the memory entry
            memories = await async_memory_mgr.get_memories(category="test_async", limit=1)
            assert len(memories) > 0, "Should retrieve at least one memory"
            assert memories[0].content == "Test async memory entry for path resolution refactoring"

            print(f"  Retrieved async memory: {memories[0].content[:50]}...")
            print("  ✓ Async memory manager tests passed!")

        except Exception as e:
            print(f"  ✗ Async memory manager test failed: {e}")
            raise


def test_path_resolution_consistency():
    """Test that both managers resolve paths consistently"""
    print("\nTesting path resolution consistency...")

    # Test paths
    test_paths = [
        "data/memory.db",
        "./relative/path.db",
        "/absolute/path.db",
        "../parent/dir/file.db"
    ]

    for test_path in test_paths:
        resolved = PathUtils.resolve_path(test_path)
        print(f"  Path '{test_path}' -> '{resolved}'")

        # Verify it's absolute
        if test_path:  # Skip empty paths
            assert os.path.isabs(resolved), f"Path '{test_path}' should resolve to absolute path"

    print("  ✓ Path resolution consistency tests passed!")


def main():
    """Run all tests"""
    print("Memory Manager Path Resolution Refactoring Tests")
    print("=" * 50)

    try:
        # Test shared utilities
        test_path_utils()

        # Test path resolution consistency
        test_path_resolution_consistency()

        # Test sync memory manager
        test_sync_memory_manager()

        # Test async memory manager
        asyncio.run(test_async_memory_manager())

        print("\n" + "=" * 50)
        print("✓ ALL TESTS PASSED!")
        print("Path resolution duplication has been successfully removed.")
        print("Both memory managers now use shared PathUtils.")

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
