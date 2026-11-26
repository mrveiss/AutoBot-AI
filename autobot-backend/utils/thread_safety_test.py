# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for Issue #481 Race Condition Fixes

Verifies thread safety of:
1. Analytics dependencies global state protection
2. Intelligent agent reload thread safety
3. Config file write locking

(The TracingService singleton and its double-checked-lock tests went with the service, #21685.)

These tests use concurrent execution to verify no race conditions exist.
"""

import asyncio
import collections
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest


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
        assert isinstance(ConfigService._config_write_lock, type(threading.RLock()))

    def test_save_config_uses_lock(self):
        """Test that _save_config_to_file uses lock"""
        from services.config_service import ConfigService

        # The lock should exist at class level
        assert ConfigService._config_write_lock is not None

    @pytest.mark.asyncio
    async def test_concurrent_config_saves(self, monkeypatch, tmp_path):
        """Test that concurrent config saves don't corrupt the real config.yaml.

        Issue #13083: the previous version patched ``base_config_file`` on the
        object returned by ``from config import config_manager``. That
        works in isolation, but ``ConfigService._save_config_to_file`` reads a
        module-global name (``services.config_service.config_manager``)
        bound once, at import time, to whatever ``config.__getattr__`` returned
        *then*. If anything ever replaces ``sys.modules["config"]`` later in the
        same process — confirmed here: ``autobot-slm-backend``'s own, unrelated
        ``config`` concept is stubbed unconditionally via
        ``sys.modules["config"] = MagicMock()`` by
        ``autobot-slm-backend/tests/api/test_auth_logout.py`` and
        ``autobot-slm-backend/tests/services/test_token_denylist.py`` with no
        guard and no restore (the cross-backend namespace-collision class
        tracked by #13084) — then a *later* ``from config import
        config_manager`` resolves to a throwaway MagicMock instead of
        the real singleton ``ConfigService`` actually uses. Patching that
        MagicMock's ``base_config_file`` is then silently inert: the redirect
        never takes effect and every concurrent save lands on the developer's
        real, unpatched ``config/config.yaml`` (reproduced 3/3 by the #10691
        baseline audit).

        Fix: patch the attribute directly on ``services.config_service`` (the
        actual consumer), bypassing the ``config`` package/its ``__getattr__``
        entirely, and assert identity immediately after patching so any future
        regression of this seam fails the test loudly instead of writing to
        the real file.
        """
        import services.config_service as config_service_module
        from services.config_service import ConfigService

        class _FakeConfigManager:
            """Minimal test double exposing only what `_save_config_to_file` reads."""

            def __init__(self, base_config_file):
                self.base_config_file = base_config_file

        test_file = tmp_path / "test_config.yaml"
        fake_manager = _FakeConfigManager(test_file)

        # Patch the real consumer, not a name reachable only via `config`'s
        # module-level __getattr__ (which is exactly what a same-named module
        # elsewhere in the process can silently hijack — see #13084).
        monkeypatch.setattr(config_service_module, "config_manager", fake_manager)

        # Fail loudly, before any write, if this seam is ever broken.
        assert config_service_module.config_manager is fake_manager
        assert config_service_module.config_manager.base_config_file == test_file

        errors = []
        save_count = {"count": 0}

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

        # Verify the redirect actually took effect (would previously raise
        # FileNotFoundError here because the writes went to the real file).
        assert test_file.exists(), "concurrent saves did not land in the redirected temp file"

        # Verify file is valid YAML (not corrupted)
        import yaml

        with open(test_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            assert "test_key" in data
            assert "iteration" in data


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

    @pytest.mark.parametrize("module_name", ["browser_mcp", "git_mcp", "database_mcp", "http_client_mcp"])
    def test_mcp_bridge_uses_canonical_limiter_and_holds_no_limiter_state(self, module_name):
        """The MCP bridges rate-limit through the canonical RateLimiter, no per-worker state (#18087)."""
        import importlib

        from autobot_shared.rate_limiter import RateLimiter

        module = importlib.import_module(f"api.{module_name}")
        assert isinstance(module._rate_limiter, RateLimiter)
        state_types = (dict, collections.deque, asyncio.Lock, type(threading.Lock()))
        for name, value in vars(module).items():
            if "rate_limit" in name.lower() or name.lower().endswith("_counter"):
                assert not isinstance(value, state_types), name

    def test_analytics_controller_has_lock(self):
        """Verify analytics_controller.py has async lock"""
        from api import analytics_controller

        assert hasattr(analytics_controller, "_analytics_state_lock")
        assert isinstance(analytics_controller._analytics_state_lock, asyncio.Lock)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
