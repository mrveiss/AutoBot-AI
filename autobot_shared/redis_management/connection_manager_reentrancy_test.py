# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for #13128: RedisConnectionManager.__init__ re-entrancy.

Resolving the manager's own Redis host (``NetworkConstants.REDIS_VM_IP``) can
fall through to ``ConfigRegistry``'s Redis-backed cache tier, which
constructs a Redis client, which constructs this same singleton again while
the first call is still mid-``__init__``. ``__new__`` correctly returns the
same instance, but Python still calls ``__init__`` on it again. These tests
pin that the re-entrant call returns immediately instead of re-running every
init step -- the pre-fix shape (guard set only at the very end of
``__init__``) recursed until ``RecursionError`` (see this module's captured,
literal reproduction in the PR description; ``connection_manager.py``'s own
``__init__`` docstring carries the same traceback shape).
"""

from unittest.mock import patch

from autobot_shared.redis_management import connection_manager as cm_mod
from autobot_shared.redis_management.connection_manager import RedisConnectionManager
from config.registry import ConfigRegistry


def _bare_manager() -> RedisConnectionManager:
    """Uninitialized instance, bypassing __new__'s singleton machinery."""
    return object.__new__(RedisConnectionManager)


class TestReentrantInitGuard:
    """Unit-level: the guard itself, without touching Redis/ConfigRegistry."""

    def test_reentrant_call_returns_immediately(self):
        m = _bare_manager()
        m._initializing = True
        with patch.object(RedisConnectionManager, "_init_configurations") as mock_cfg:
            m.__init__()
        mock_cfg.assert_not_called()
        assert not hasattr(m, "_initialized")

    def test_initializing_set_before_init_configurations_runs(self):
        """The guard must be armed BEFORE any init step, not just at the end --
        the pre-fix ordering set only ``_initialized``, and only after every
        step had already run once."""
        m = _bare_manager()
        seen = []

        def fake_init_configurations(self):
            seen.append(self._initializing)
            self._config = {"host": "127.0.0.1", "port": 6379}
            self._configs = {}
            self._pool_config = None

        with patch.object(RedisConnectionManager, "_init_configurations", fake_init_configurations):
            m.__init__()

        assert seen == [True]
        assert m._initialized is True
        assert m._initializing is False


class TestBoundedRecursion:
    """End-to-end: the actual reported chain (#13128) -- host resolution
    re-entering the singleton -- terminates instead of exhausting the stack.
    """

    def setup_method(self):
        RedisConnectionManager.reset_instance()
        ConfigRegistry.clear_cache()

    def teardown_method(self):
        RedisConnectionManager.reset_instance()
        ConfigRegistry.clear_cache()

    def test_recursion_bounded_to_one_reentrant_level(self, monkeypatch):
        """Force every upper fallback tier empty so ``_load_redis_config``
        reaches ``NetworkConstants.REDIS_VM_IP`` -> ``ConfigRegistry.get`` ->
        ``_get_redis`` -> ``get_redis_client`` -> ``RedisConnectionManager()``
        -- the exact re-entrant chain from the captured traceback. The
        re-entrant call must return at depth 2, never deeper.
        """
        monkeypatch.delenv("REDIS_HOST", raising=False)
        monkeypatch.delenv("AUTOBOT_REDIS_HOST", raising=False)
        monkeypatch.delenv("AUTOBOT_VM_REDIS", raising=False)
        monkeypatch.setattr(cm_mod, "_get_config_manager", lambda: None)

        depths: list[int] = []
        max_depth = [0]
        real_init = RedisConnectionManager.__init__

        def traced_init(self):
            depths.append(1)
            max_depth[0] = max(max_depth[0], len(depths))
            try:
                real_init(self)
            finally:
                depths.pop()

        with patch.object(RedisConnectionManager, "__init__", traced_init):
            RedisConnectionManager()

        assert max_depth[0] == 2
        assert depths == []
