#!/usr/bin/env python3
"""
Simple test to verify PathUtils functionality without complex dependencies
"""

import logging
import os
import sys

# Add project root to path so we can import the modules
project_root = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, project_root)

# Just test the PathUtils directly
from utils.common import PathUtils

logger = logging.getLogger(__name__)


def test_path_utils():
    """Test the shared PathUtils functionality"""
    logger.info("Testing PathUtils...")

    # Test relative path resolution
    relative_path = "data/test.db"
    resolved = PathUtils.resolve_path(relative_path)
    logger.info(f"  Relative path '{relative_path}' resolved to: {resolved}")
    assert os.path.isabs(resolved), "Should return absolute path"

    # Test absolute path (should remain unchanged)
    absolute_path = "/tmp/test.db"
    resolved_abs = PathUtils.resolve_path(absolute_path)
    logger.info(f"  Absolute path '{absolute_path}' resolved to: {resolved_abs}")
    assert resolved_abs == absolute_path, "Absolute path should remain unchanged"

    # Test empty path
    empty_resolved = PathUtils.resolve_path("")
    logger.info(f"  Empty path resolved to: '{empty_resolved}'")
    assert empty_resolved == "", "Empty path should return empty string"

    # Test normalize_path
    test_path = "some/../complex/./path"
    normalized = PathUtils.normalize_path(test_path)
    logger.info(f"  Normalized path '{test_path}' to: {normalized}")
    assert "/.." not in normalized, "Should resolve relative components"

    # Test ensure_path_exists (for parent directory)
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        test_file_path = os.path.join(temp_dir, "subdir", "test.txt")
        success = PathUtils.ensure_path_exists(test_file_path, is_file=True)
        logger.info(f"  Ensured parent directory for file: {success}")
        assert success, "Should create parent directory"
        assert os.path.exists(
            os.path.dirname(test_file_path)
        ), "Parent directory should exist"

    logger.info("  ✓ PathUtils tests passed!")


def test_path_resolution_consistency():
    """Test that path resolution is consistent"""
    logger.info("\nTesting path resolution consistency...")

    # Test paths
    test_paths = [
        "data/memory.db",
        "./relative/path.db",
        "/absolute/path.db",
        "../parent/dir/file.db",
    ]

    for test_path in test_paths:
        resolved = PathUtils.resolve_path(test_path)
        logger.info(f"  Path '{test_path}' -> '{resolved}'")

        # Verify it's absolute
        if test_path:  # Skip empty paths
            assert os.path.isabs(
                resolved
            ), f"Path '{test_path}' should resolve to absolute path"

    logger.info("  ✓ Path resolution consistency tests passed!")


def verify_no_duplicate_code():
    """Verify that the duplicate _resolve_path methods have been removed"""
    logger.info("\nVerifying duplicate code removal...")

    # Check that both memory manager files exist
    async_memory_path = os.path.join(project_root, "src", "memory_manager_async.py")
    sync_memory_path = os.path.join(project_root, "src", "memory_manager.py")

    assert os.path.exists(async_memory_path), "Async memory manager should exist"
    assert os.path.exists(sync_memory_path), "Sync memory manager should exist"

    # Check that they import PathUtils
    with open(async_memory_path, "r") as f:
        async_content = f.read()

    with open(sync_memory_path, "r") as f:
        sync_content = f.read()

    # Verify PathUtils import exists
    assert (
        "from utils.common import PathUtils" in async_content
    ), "Async memory manager should import PathUtils"
    assert (
        "from utils.common import PathUtils" in sync_content
    ), "Sync memory manager should import PathUtils"

    # Verify old _resolve_path methods are removed
    assert (
        "def _resolve_path(" not in async_content
    ), "Async memory manager should not have _resolve_path method"
    assert (
        "def _resolve_path(" not in sync_content
    ), "Sync memory manager should not have _resolve_path method"

    # Verify PathUtils.resolve_path is used
    assert (
        "PathUtils.resolve_path(" in async_content
    ), "Async memory manager should use PathUtils.resolve_path"
    assert (
        "PathUtils.resolve_path(" in sync_content
    ), "Sync memory manager should use PathUtils.resolve_path"

    logger.info("  ✓ Duplicate code successfully removed!")


def main():
    """Run all tests"""
    logger.info("Memory Manager Path Resolution Refactoring Tests")
    logger.info("=" * 50)

    try:
        # Test shared utilities
        test_path_utils()

        # Test path resolution consistency
        test_path_resolution_consistency()

        # Verify duplicate code removal
        verify_no_duplicate_code()

        logger.info("\n" + "=" * 50)
        logger.info("✓ ALL TESTS PASSED!")
        logger.info("✓ Path resolution duplication has been successfully removed.")
        logger.info("✓ Both memory managers now use shared PathUtils.")
        logger.info("✓ Code duplication eliminated while preserving functionality.")

    except Exception as e:
        logger.info(f"\n✗ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
