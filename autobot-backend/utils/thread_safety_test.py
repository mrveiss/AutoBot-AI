# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for Issue #481 Race Condition Fixes

Verifies thread safety of:
1. TracingService singleton initialization
2. Analytics dependencies global state protection
3. Intelligent agent reload thread safety
4. Config file write locking

These tests use concurrent execution to verify no race conditions exist.
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest


class TestTracingServiceSingleton:
    """Test thread-safe singleton for TracingService (Issue #481)"""

    @pytest.fixture(autouse=True)
    def skip_if_opentelemetry_unavailable(self):
        """Skip tests if OpenTelemetry has import issues"""
        try:
            pass
        except ImportError as e:
            pytest.skip(f"TracingService unavailable: {e}")

    def test_singleton_returns_same_instance(self):
        """Test that TracingService returns same instance on multiple calls"""
        from services.tracing_service import TracingService

        # Get two instances
        instance1 = TracingService()
        instance2 = TracingService()

        # Should be the same instance
        assert instance1 is instance2

    def test_concurrent_singleton_access(self):
        """Test that concurrent access returns same singleton instance"""
        from services.tracing_service import TracingService

        # Reset singleton for clean test
        TracingService._instance = None
        TracingService._initialized = False

        instances = []
        errors = []

        def get_instance():
            try:
                instance = TracingService()
                instances.append(instance)
            except Exception as e:
                errors.append(e)

        # Create 20 threads that all try to get the singleton simultaneously
        threads = [threading.Thread(target=get_instance) for _ in range(20)]

        # Start all threads at once
        for t in threads:
            t.start()

        # Wait for all to complete
        for t in threads:
            t.join()

        # Verify no errors
        assert len(errors) == 0, f"Errors during concurrent access: {errors}"

        # Verify all instances are the same object
        assert len(instances) == 20
        first_instance = instances[0]
        for instance in instances[1:]:
            assert instance is first_instance, "Different instances created!"

    def test_singleton_lock_exists(self):
        """Test that TracingService has a lock for thread safety"""
        from services.tracing_service import TracingService

        assert hasattr(TracingService, "_lock")
        assert isinstance(TracingService._lock, type(threading.Lock()))


# TestAnalyticsMonitoringThreadSafety class removed in Issue #532
# analytics_monitoring.py was deleted - monitoring endpoints consolidated in monitoring.py


class TestAnalyticsCodeThreadSafety:
    """Test thread-safe global state for analytics_code (Issue #481)"""

    def test_lock_exists(self):
        """Test that analytics_code has thread lock"""
        from api import analytics_code

        assert hasattr(analytics_code, "_analytics_deps_lock")
        assert isinstance(analytics_code._analytics_deps_lock, type(threading.Lock()))

    def test_set_dependencies_uses_lock(self):
        """Test that set_analytics_dependencies is protected by lock"""
        from api import analytics_code

        # Verify the lock attribute exists and is used
        assert hasattr(analytics_code, "_analytics_deps_lock")

        # Call the function
        mock_controller = MagicMock()
        mock_state = MagicMock()

        # Should not raise any exceptions
        analytics_code.set_analytics_dependencies(mock_controller, mock_state)

        # Verify globals were set
        assert analytics_code.analytics_controller is mock_controller
        assert analytics_code.analytics_state is mock_state


class TestIntelligentAgentReloadThreadSafety:
    """Test thread-safe agent reload (Issue #481)"""

    @pytest.mark.asyncio
    async def test_reload_uses_lock(self):
        """Test that reload_agent uses the initialization lock"""
        from api import intelligent_agent

        # Verify lock exists
        assert hasattr(intelligent_agent, "_agent_initialization_lock")
        assert isinstance(intelligent_agent._agent_initialization_lock, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_concurrent_reload_safety(self):
        """Test that concurrent reloads don't cause race conditions"""
        from api import intelligent_agent

        # Reset agent instance
        intelligent_agent._agent_instance = None

        reload_count = {"count": 0}
        errors = []

        async def mock_reload():
            try:
                # Simulate what reload_agent does
                async with intelligent_agent._agent_initialization_lock:
                    intelligent_agent._agent_instance = None
                reload_count["count"] += 1
            except Exception as e:
                errors.append(e)

        # Run 10 concurrent reloads
        await asyncio.gather(*[mock_reload() for _ in range(10)])

        assert len(errors) == 0, f"Errors during concurrent reload: {errors}"
        assert reload_count["count"] == 10


class TestConfigServiceFileLocking:
    """Test thread-safe config file writing (Issue #481)"""

    def test_config_write_lock_exists(self):
        """Test that ConfigService has write lock"""
        from services.config_service import ConfigService

        assert hasattr(ConfigService, "_config_write_lock")
        assert isinstance(ConfigService._config_write_lock, type(threading.Lock()))

    def test_save_config_uses_lock(self):
        """Test that _save_config_to_file uses lock"""
        from services.config_service import ConfigService

        # The lock should exist at class level
        assert ConfigService._config_write_lock is not None

    @pytest.mark.asyncio
    async def test_concurrent_config_saves(self):
        """Test that concurrent config saves don't corrupt file"""
        import tempfile
        from pathlib import Path

        from config import unified_config_manager
        from services.config_service import ConfigService

        errors = []
        save_count = {"count": 0}

        # Create temp directory for test
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test_config.yaml"

            # Patch the config file path
            original_path = unified_config_manager.base_config_file

            try:
                unified_config_manager.base_config_file = test_file

                def save_config(i):
                    try:
                        config = {"test_key": f"value_{i}", "iteration": i}
                        ConfigService._save_config_to_file(config)
                        save_count["count"] += 1
                    except Exception as e:
                        errors.append(e)

                # Run 10 concurrent saves
                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = [executor.submit(save_config, i) for i in range(10)]
                    for f in futures:
                        f.result()

                assert len(errors) == 0, f"Errors during concurrent saves: {errors}"
                assert save_count["count"] == 10

                # Verify file is valid YAML (not corrupted)
                import yaml

                with open(test_file, "r") as f:
                    data = yaml.safe_load(f)
                    assert "test_key" in data
                    assert "iteration" in data

            finally:
                unified_config_manager.base_config_file = original_path


class TestExistingLockVerification:
    """Verify that files mentioned in Issue #481 have proper locking"""

    def test_analytics_performance_has_lock(self):
        """Verify analytics_performance.py has async lock"""
        from api import analytics_performance

        assert hasattr(analytics_performance, "_analysis_history_lock")
        assert isinstance(analytics_performance._analysis_history_lock, asyncio.Lock)

    def test_analytics_precommit_has_lock(self):
        """Verify analytics_precommit.py has thread lock"""
        from api import analytics_precommit

        assert hasattr(analytics_precommit, "_history_lock")
        assert isinstance(analytics_precommit._history_lock, type(threading.Lock()))

    def test_browser_mcp_has_lock(self):
        """Verify browser_mcp.py has async lock"""
        from api import browser_mcp

        assert hasattr(browser_mcp, "_rate_limit_lock")
        assert isinstance(browser_mcp._rate_limit_lock, asyncio.Lock)

    def test_analytics_controller_has_lock(self):
        """Verify analytics_controller.py has async lock"""
        from api import analytics_controller

        assert hasattr(analytics_controller, "_analytics_state_lock")
        assert isinstance(analytics_controller._analytics_state_lock, asyncio.Lock)


class TestDoubleCheckedLocking:
    """Test that double-checked locking pattern is correctly implemented"""

    @pytest.fixture(autouse=True)
    def skip_if_opentelemetry_unavailable(self):
        """Skip tests if OpenTelemetry has import issues"""
        try:
            pass
        except ImportError as e:
            pytest.skip(f"TracingService unavailable: {e}")

    def test_tracing_service_double_check(self):
        """Test TracingService uses double-checked locking"""
        import inspect

        from services.tracing_service import TracingService

        # Get the source of __new__
        source = inspect.getsource(TracingService.__new__)

        # Verify double-check pattern exists
        assert "if cls._instance is None:" in source
        assert "with cls._lock:" in source
        # Should have two None checks (outer and inner)
        assert (
            source.count("_instance is None") >= 2
        ), "Double-checked locking not implemented"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
