#!/usr/bin/env python3
"""
Comprehensive Test Suite for Knowledge Manager.

Tests features including:
- temporal_knowledge_manager.py (time-based knowledge expiry)
- UnifiedKnowledgeManager (template management, machine adaptation)
"""

import asyncio
import hashlib
import os

# Test imports
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.knowledge_manager import (
    IMachineAwareManager,
    ISystemKnowledgeManager,
    ITemporalManager,
    UnifiedKnowledgeManager,
    get_unified_knowledge_manager,
)
from temporal_knowledge_manager import (
    FreshnessStatus,
    InvalidationJob,
    KnowledgePriority,
    TemporalKnowledgeManager,
    TemporalMetadata,
)

# ============================================================================
# MOCK OBJECTS - Minimal mocking for isolation
# ============================================================================


class MockKnowledgeBase:
    """Mock KnowledgeBase for testing"""

    def __init__(self):
        self.redis_client = MagicMock()
        self.data = {}
        self.categories = {
            "documentation": {},
            "system": {},
            "configuration": {},
            "tools": {},
            "workflows": {},
        }

    async def get_tool_knowledge(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Mock get_tool_knowledge"""
        return self.data.get(f"tool:{tool_name}")

    async def store_knowledge(
        self, category: str, content_id: str, content: Dict[str, Any]
    ):
        """Mock store_knowledge"""
        self.data[f"{category}:{content_id}"] = content

    async def store_fact(self, content: str, metadata: Optional[Dict[str, Any]] = None):
        """Mock store_fact (required by librarian)"""
        fact_id = f"fact:{len(self.data)}"
        self.data[fact_id] = {"content": content, "metadata": metadata or {}}
        return fact_id

    async def remove_knowledge(self, content_id: str):
        """Mock remove_knowledge"""
        if content_id in self.data:
            del self.data[content_id]


class MockSystemKnowledgeManager:
    """Mock SystemKnowledgeManager for testing - no actual initialization"""

    def __init__(self, knowledge_base):
        self.knowledge_base = knowledge_base
        self.initialized = False
        self.runtime_knowledge_dir = Path(tempfile.gettempdir()) / "runtime_knowledge"
        self.runtime_knowledge_dir.mkdir(parents=True, exist_ok=True)

    async def initialize_system_knowledge(self, force_reinstall: bool = False):
        """Mock initialize - doesn't actually import anything"""
        self.initialized = True

    async def reload_system_knowledge(self):
        """Mock reload"""

    def get_knowledge_categories(self) -> Dict[str, Any]:
        """Mock get_knowledge_categories"""
        return {
            "success": True,
            "categories": {
                "documentation": {"count": 10},
                "system": {"count": 5},
                "configuration": {"count": 3},
            },
        }

    async def _backup_current_knowledge(self):
        """Mock backup"""


class MockMachineAwareSystemKnowledgeManager(MockSystemKnowledgeManager):
    """Mock MachineAwareSystemKnowledgeManager for testing"""

    def __init__(self, knowledge_base):
        super().__init__(knowledge_base)
        self.current_machine_profile = MagicMock()
        self.current_machine_profile.to_dict.return_value = {
            "machine_id": "test-machine-001",
            "hostname": "test-host",
            "os_type": "Linux",
            "distro": "Kali",
            "available_tools": {"grep", "sed", "awk"},
            "architecture": "x86_64",
            "capabilities": ["forensics", "networking"],
        }
        self.machine_profiles_dir = Path(tempfile.gettempdir()) / "machine_profiles"
        self.machine_profiles_dir.mkdir(parents=True, exist_ok=True)

    async def initialize_machine_aware_knowledge(self, force_reinstall: bool = False):
        """Mock machine-aware initialize"""
        self.initialized = True

    async def get_machine_info(self) -> Optional[Dict[str, Any]]:
        """Mock get_machine_info"""
        return self.current_machine_profile.to_dict()

    async def search_man_page_knowledge(self, query: str) -> List[Dict[str, Any]]:
        """Mock man page search"""
        if not query:
            return []
        return [
            {
                "command": "grep",
                "description": "Search text using patterns",
                "category": "text",
            },
            {
                "command": "sed",
                "description": "Stream editor",
                "category": "text",
            },
        ]

    async def get_man_page_summary(self) -> Dict[str, Any]:
        """Mock man page summary"""
        return {
            "total_pages": 150,
            "categories": {"text": 50, "file": 30, "network": 70},
            "last_updated": datetime.now().isoformat(),
        }


# ============================================================================
# TEST SUITE
# ============================================================================


def test_1_import_verification():
    """Test 1: Verify all components can be imported"""
    print("\n[TEST 1] Import verification...")  # noqa: print

    # Verify main class
    assert UnifiedKnowledgeManager is not None

    # Verify protocols
    assert ITemporalManager is not None
    assert ISystemKnowledgeManager is not None
    assert IMachineAwareManager is not None

    # Verify enums from temporal manager
    assert KnowledgePriority is not None
    assert FreshnessStatus is not None

    # Verify data models
    assert TemporalMetadata is not None
    assert InvalidationJob is not None

    # Verify global instance function
    assert get_unified_knowledge_manager is not None

    print("✅ PASSED: All components imported successfully")  # noqa: print


async def test_2_temporal_manager_features():
    """Test 2: Temporal manager features (register, access tracking, expiry)"""
    print("\n[TEST 2] Temporal manager features...")  # noqa: print

    kb = MockKnowledgeBase()
    manager = UnifiedKnowledgeManager(
        knowledge_base=kb, enable_temporal=True, enable_machine_aware=False
    )

    # Register content with temporal tracking
    content_hash = hashlib.md5(b"test content").hexdigest()
    metadata = manager.register_content(
        "tool:steghide", {"category": "tools"}, content_hash
    )

    assert metadata is not None, "Failed to register content"
    assert metadata.content_id == "tool:steghide"
    assert metadata.priority == KnowledgePriority.MEDIUM
    assert metadata.ttl_hours == 168.0

    # Update access tracking
    manager.update_content_access("tool:steghide")
    status = manager.get_content_status("tool:steghide")
    assert status is not None
    assert status["access_count"] == 1

    # Update modification tracking
    new_hash = hashlib.md5(b"updated content").hexdigest()
    manager.update_content_modification("tool:steghide", new_hash)

    print("✅ PASSED: Temporal manager features work correctly")  # noqa: print


async def test_3_system_knowledge_features():
    """Test 3: System knowledge features (import, templates, change detection)"""
    print("\n[TEST 3] System knowledge features...")  # noqa: print

    kb = MockKnowledgeBase()
    mock_system = MockSystemKnowledgeManager(kb)

    manager = UnifiedKnowledgeManager(
        knowledge_base=kb,
        enable_temporal=False,
        enable_machine_aware=False,
        system_manager=mock_system,
    )

    # Initialize system knowledge
    await manager.initialize_system_knowledge(force_reinstall=False)
    assert mock_system.initialized, "System knowledge not initialized"

    # Reload system knowledge
    await manager.reload_system_knowledge()

    # Get knowledge categories
    categories = manager.get_knowledge_categories()
    assert categories["success"] is True
    assert "documentation" in categories["categories"]
    assert "system" in categories["categories"]

    print("✅ PASSED: System knowledge features work correctly")  # noqa: print


async def test_4_machine_aware_features():
    """Test 4: Machine-aware features (detection, adaptation, man pages)"""
    print("\n[TEST 4] Machine-aware features...")  # noqa: print

    kb = MockKnowledgeBase()
    mock_machine = MockMachineAwareSystemKnowledgeManager(kb)

    manager = UnifiedKnowledgeManager(
        knowledge_base=kb,
        enable_temporal=False,
        enable_machine_aware=True,
        system_manager=mock_machine,
    )

    # Initialize with machine awareness
    await manager.initialize_machine_aware_knowledge(force_reinstall=False)
    assert mock_machine.initialized, "Machine-aware knowledge not initialized"

    # Get machine info
    machine_info = await manager.get_machine_info()
    assert machine_info is not None
    assert machine_info["machine_id"] == "test-machine-001"
    assert machine_info["os_type"] == "Linux"
    assert "grep" in machine_info["available_tools"]

    # Search man pages
    results = await manager.search_man_page_knowledge("grep")
    assert len(results) == 2
    assert results[0]["command"] == "grep"

    # Get man page summary
    summary = await manager.get_man_page_summary()
    assert summary["total_pages"] == 150

    print("✅ PASSED: Machine-aware features work correctly")  # noqa: print


async def test_5_unified_operations():
    """Test 5: Unified operations (import_with_tracking, search, status)"""
    print("\n[TEST 5] Unified operations...")  # noqa: print

    kb = MockKnowledgeBase()
    mock_system = MockSystemKnowledgeManager(kb)

    manager = UnifiedKnowledgeManager(
        knowledge_base=kb,
        enable_temporal=True,
        enable_machine_aware=False,
        system_manager=mock_system,
    )

    # Create temp test file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write("name: test\ndescription: test tool\n")
        temp_file = f.name

    try:
        # Import knowledge with tracking
        result = await manager.import_knowledge_with_tracking(
            category="tools", files=[temp_file], metadata={"source": "test"}
        )

        assert result["imported_count"] == 1
        assert result["tracked_count"] == 1
        assert result["temporal_tracking_enabled"] is True
    finally:
        Path(temp_file).unlink()

    # Get comprehensive status
    status = await manager.get_knowledge_status()
    assert "initialized" in status
    assert status["temporal_enabled"] is True
    assert "system_knowledge" in status
    assert "temporal_analytics" in status

    # Search knowledge
    search_results = await manager.search_knowledge("test", include_man_pages=False)
    assert search_results["query"] == "test"

    print("✅ PASSED: Unified operations work correctly")  # noqa: print


async def test_6_optional_components():
    """Test 6: Optional components (temporal disabled, machine-aware disabled)"""
    print("\n[TEST 6] Optional components...")  # noqa: print

    kb = MockKnowledgeBase()

    # Test with temporal disabled
    manager_no_temporal = UnifiedKnowledgeManager(
        knowledge_base=kb, enable_temporal=False, enable_machine_aware=False
    )

    metadata = manager_no_temporal.register_content("test", {"cat": "test"}, "a" * 32)
    assert metadata is None, "Should return None when temporal disabled"

    analytics = await manager_no_temporal.get_temporal_analytics()
    assert analytics["temporal_tracking_enabled"] is False

    # Test with machine-aware disabled
    machine_info = await manager_no_temporal.get_machine_info()
    assert machine_info is None, "Should return None when machine-aware disabled"

    # Test that machine-aware methods raise errors when disabled
    try:
        await manager_no_temporal.initialize_machine_aware_knowledge()
        assert False, "Should raise RuntimeError"
    except RuntimeError as e:
        assert "not enabled" in str(e)

    print("✅ PASSED: Optional components work correctly")  # noqa: print


async def test_7_backward_compatibility():
    """Test 7: Backward compatibility (individual managers still work)"""
    print("\n[TEST 7] Backward compatibility...")  # noqa: print

    kb = MockKnowledgeBase()

    # Test that individual managers can still be used directly
    temporal_mgr = TemporalKnowledgeManager()
    assert temporal_mgr is not None

    # Register content directly with temporal manager
    content_hash = hashlib.md5(b"test").hexdigest()
    meta = temporal_mgr.register_content("test-001", {}, content_hash)
    assert meta is not None
    assert meta.content_id == "test-001"

    # Test system manager can be used independently
    mock_system = MockSystemKnowledgeManager(kb)
    await mock_system.initialize_system_knowledge()
    assert mock_system.initialized

    print("✅ PASSED: Backward compatibility preserved")  # noqa: print


async def test_8_singleton_pattern():
    """Test 8: Singleton pattern (get_unified_knowledge_manager)"""
    print("\n[TEST 8] Singleton pattern...")  # noqa: print

    # Reset global instance (for testing only)
    import unified_knowledge_manager as ukm_module

    ukm_module._unified_knowledge_manager_instance = None

    kb = MockKnowledgeBase()

    # First call - should create instance
    manager1 = get_unified_knowledge_manager(
        knowledge_base=kb, enable_temporal=True, enable_machine_aware=False
    )
    assert manager1 is not None

    # Second call - should return same instance
    manager2 = get_unified_knowledge_manager()
    assert manager1 is manager2, "Should return same singleton instance"

    # Test error on first call without knowledge_base
    ukm_module._unified_knowledge_manager_instance = None
    try:
        get_unified_knowledge_manager()
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "knowledge_base required" in str(e)

    print("✅ PASSED: Singleton pattern works correctly")  # noqa: print


async def test_9_input_validation():
    """Test 9: Input validation (invalid parameters rejected)"""
    print("\n[TEST 9] Input validation...")  # noqa: print

    kb = MockKnowledgeBase()
    mock_system = MockSystemKnowledgeManager(kb)

    manager = UnifiedKnowledgeManager(
        knowledge_base=kb,
        enable_temporal=True,
        enable_machine_aware=False,
        system_manager=mock_system,
    )

    # Test invalid knowledge_base in constructor
    try:
        UnifiedKnowledgeManager(knowledge_base=None)
        assert False, "Should raise ValueError for None knowledge_base"
    except ValueError as e:
        assert "cannot be None" in str(e)

    # Test invalid content_id
    try:
        manager.register_content("", {}, "a" * 32)
        assert False, "Should raise ValueError for empty content_id"
    except ValueError as e:
        assert "cannot be empty" in str(e)

    # Test invalid content_hash
    try:
        manager.register_content("test", {}, "invalid_hash")
        assert False, "Should raise ValueError for invalid hash"
    except ValueError as e:
        assert "valid MD5 hash" in str(e)

    # Test invalid query
    try:
        await manager.search_knowledge("")
        assert False, "Should raise ValueError for empty query"
    except ValueError as e:
        assert "cannot be empty" in str(e)

    # Test invalid category
    try:
        await manager.import_knowledge_with_tracking("", ["file.yaml"])
        assert False, "Should raise ValueError for empty category"
    except ValueError as e:
        assert "cannot be empty" in str(e)

    print("✅ PASSED: Input validation works correctly")  # noqa: print


async def test_10_thread_safety():
    """Test 10: Thread safety (concurrent initialization)"""
    print("\n[TEST 10] Thread safety...")  # noqa: print

    kb = MockKnowledgeBase()
    mock_system = MockSystemKnowledgeManager(kb)
    manager = UnifiedKnowledgeManager(
        knowledge_base=kb,
        enable_temporal=False,
        enable_machine_aware=False,
        system_manager=mock_system,
    )

    # Concurrent initialization attempts
    tasks = [
        manager._ensure_initialized(),
        manager._ensure_initialized(),
        manager._ensure_initialized(),
    ]

    await asyncio.gather(*tasks)

    # Should only initialize once
    assert manager._initialized is True

    print("✅ PASSED: Thread safety works correctly")  # noqa: print


async def test_11_integration():
    """Test 11: Integration (temporal + system + machine)"""
    print("\n[TEST 11] Full integration...")  # noqa: print

    kb = MockKnowledgeBase()
    mock_machine = MockMachineAwareSystemKnowledgeManager(kb)

    manager = UnifiedKnowledgeManager(
        knowledge_base=kb,
        enable_temporal=True,
        enable_machine_aware=True,
        system_manager=mock_machine,
    )

    # Initialize all components
    await manager.initialize(force_reinstall=False)

    # Register content with temporal tracking
    content_hash = hashlib.md5(b"integrated content").hexdigest()
    meta = manager.register_content(
        "tool:integrated", {"category": "tools"}, content_hash
    )
    assert meta is not None

    # Get comprehensive status (all components)
    status = await manager.get_knowledge_status()
    assert status["temporal_enabled"] is True
    assert status["machine_aware_enabled"] is True
    assert "temporal_analytics" in status
    assert "machine_profile" in status
    assert "system_knowledge" in status

    print("✅ PASSED: Full integration works correctly")  # noqa: print


async def test_12_analytics():
    """Test 12: Analytics (temporal analytics, knowledge status)"""
    print("\n[TEST 12] Analytics...")  # noqa: print

    kb = MockKnowledgeBase()
    mock_system = MockSystemKnowledgeManager(kb)

    manager = UnifiedKnowledgeManager(
        knowledge_base=kb,
        enable_temporal=True,
        enable_machine_aware=False,
        system_manager=mock_system,
    )

    # Register multiple content items
    for i in range(5):
        content_hash = hashlib.md5(f"content-{i}".encode()).hexdigest()
        manager.register_content(f"item-{i}", {"category": "test"}, content_hash)

    # Get temporal analytics
    analytics = await manager.get_temporal_analytics()
    assert analytics["temporal_tracking_enabled"] is True
    assert analytics["total_content"] == 5
    assert "status_distribution" in analytics
    assert "priority_distribution" in analytics
    assert "averages" in analytics

    # Get knowledge status
    status = await manager.get_knowledge_status()
    assert "temporal_analytics" in status
    assert status["temporal_analytics"]["total_content"] == 5

    print("✅ PASSED: Analytics work correctly")  # noqa: print


async def test_13_background_processing():
    """Test 13: Background processing (start/stop temporal task)"""
    print("\n[TEST 13] Background processing...")  # noqa: print

    kb = MockKnowledgeBase()
    mock_system = MockSystemKnowledgeManager(kb)

    manager = UnifiedKnowledgeManager(
        knowledge_base=kb,
        enable_temporal=True,
        enable_machine_aware=False,
        system_manager=mock_system,
    )

    # Test start with temporal disabled should fail
    manager_no_temporal = UnifiedKnowledgeManager(
        knowledge_base=kb, enable_temporal=False, enable_machine_aware=False
    )

    try:
        await manager_no_temporal.start_temporal_background_processing()
        assert False, "Should raise RuntimeError"
    except RuntimeError as e:
        assert "not enabled" in str(e)

    # Test invalid interval
    try:
        await manager.start_temporal_background_processing(check_interval_minutes=0)
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "must be positive" in str(e)

    # Test stop (should not raise even if not started)
    await manager.stop_temporal_background_processing()

    print("✅ PASSED: Background processing works correctly")  # noqa: print


async def test_14_error_handling():
    """Test 14: Error handling (graceful failures)"""
    print("\n[TEST 14] Error handling...")  # noqa: print

    kb = MockKnowledgeBase()
    mock_system = MockSystemKnowledgeManager(kb)

    manager = UnifiedKnowledgeManager(
        knowledge_base=kb,
        enable_temporal=True,
        enable_machine_aware=False,
        system_manager=mock_system,
    )

    # Test get_content_status with invalid ID
    try:
        manager.get_content_status("")
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "cannot be empty" in str(e)

    # Test update_content_access with invalid ID
    try:
        manager.update_content_access("")
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "cannot be empty" in str(e)

    # Test update_content_modification with invalid hash
    try:
        manager.update_content_modification("test", "bad_hash")
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "valid MD5 hash" in str(e)

    # Test process_invalidation_job with None
    try:
        await manager.process_invalidation_job(None)
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "cannot be None" in str(e)

    print("✅ PASSED: Error handling works correctly")  # noqa: print


async def test_15_feature_completeness():
    """Test 15: Feature completeness (all methods work)"""
    print("\n[TEST 15] Feature completeness...")  # noqa: print

    kb = MockKnowledgeBase()
    mock_machine = MockMachineAwareSystemKnowledgeManager(kb)

    manager = UnifiedKnowledgeManager(
        knowledge_base=kb,
        enable_temporal=True,
        enable_machine_aware=True,
        system_manager=mock_machine,
    )

    # Verify all main methods exist and are callable
    methods = [
        # Initialization
        "initialize",
        "reload",
        # System knowledge
        "initialize_system_knowledge",
        "reload_system_knowledge",
        "get_knowledge_categories",
        # Machine awareness
        "initialize_machine_aware_knowledge",
        "get_machine_info",
        "list_supported_machines",
        "search_man_page_knowledge",
        "get_man_page_summary",
        # Temporal tracking
        "register_content",
        "update_content_access",
        "update_content_modification",
        "scan_for_expired_content",
        "process_invalidation_job",
        "get_temporal_analytics",
        "start_temporal_background_processing",
        "stop_temporal_background_processing",
        "get_content_status",
        # Unified operations
        "import_knowledge_with_tracking",
        "get_knowledge_status",
        "search_knowledge",
        # Backup & maintenance
        "backup_knowledge",
        "cleanup_expired_content",
    ]

    for method_name in methods:
        assert hasattr(manager, method_name), f"Missing method: {method_name}"
        method = getattr(manager, method_name)
        assert callable(method), f"Method not callable: {method_name}"

    # Test a few key methods to ensure they work
    await manager.initialize()
    categories = manager.get_knowledge_categories()
    assert categories["success"] is True

    machine_info = await manager.get_machine_info()
    assert machine_info is not None

    analytics = await manager.get_temporal_analytics()
    assert analytics["temporal_tracking_enabled"] is True

    status = await manager.get_knowledge_status()
    assert "initialized" in status

    print("✅ PASSED: All features complete and working")  # noqa: print


def run_all_tests():
    """Run all tests"""
    print("=" * 80)  # noqa: print
    print("TESTING P6 UNIFIED KNOWLEDGE MANAGER")  # noqa: print
    print("=" * 80)  # noqa: print

    try:
        # Test 1: Imports (sync)
        test_1_import_verification()

        # Test 2: Temporal features (async)
        asyncio.run(test_2_temporal_manager_features())

        # Test 3: System knowledge (async)
        asyncio.run(test_3_system_knowledge_features())

        # Test 4: Machine-aware (async)
        asyncio.run(test_4_machine_aware_features())

        # Test 5: Unified operations (async)
        asyncio.run(test_5_unified_operations())

        # Test 6: Optional components (async)
        asyncio.run(test_6_optional_components())

        # Test 7: Backward compatibility (async)
        asyncio.run(test_7_backward_compatibility())

        # Test 8: Singleton pattern (async)
        asyncio.run(test_8_singleton_pattern())

        # Test 9: Input validation (async)
        asyncio.run(test_9_input_validation())

        # Test 10: Thread safety (async)
        asyncio.run(test_10_thread_safety())

        # Test 11: Integration (async)
        asyncio.run(test_11_integration())

        # Test 12: Analytics (async)
        asyncio.run(test_12_analytics())

        # Test 13: Background processing (async)
        asyncio.run(test_13_background_processing())

        # Test 14: Error handling (async)
        asyncio.run(test_14_error_handling())

        # Test 15: Feature completeness (async)
        asyncio.run(test_15_feature_completeness())

        print("\n" + "=" * 80)  # noqa: print
        print("ALL TESTS PASSED! ✅")  # noqa: print
        print("=" * 80)  # noqa: print
        print("\nResults: 15/15 tests passed")  # noqa: print
        print("- Import verification: ✅")  # noqa: print
        print("- Temporal manager features: ✅")  # noqa: print
        print("- System knowledge features: ✅")  # noqa: print
        print("- Machine-aware features: ✅")  # noqa: print
        print("- Unified operations: ✅")  # noqa: print
        print("- Optional components: ✅")  # noqa: print
        print("- Backward compatibility: ✅")  # noqa: print
        print("- Singleton pattern: ✅")  # noqa: print
        print("- Input validation: ✅")  # noqa: print
        print("- Thread safety: ✅")  # noqa: print
        print("- Integration: ✅")  # noqa: print
        print("- Analytics: ✅")  # noqa: print
        print("- Background processing: ✅")  # noqa: print
        print("- Error handling: ✅")  # noqa: print
        print("- Feature completeness: ✅")  # noqa: print

        return True

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")  # noqa: print
        import traceback

        traceback.print_exc()
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {e}")  # noqa: print
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
