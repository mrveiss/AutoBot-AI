# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for #11830: a connection-manager singleton constructed under
test-stubbed config (MagicMock backend config manager) must not poison later
``get_async_redis_client()`` callers.

- PoolConfig coerces non-numeric field values (MagicMock/None/str) to the
  documented defaults with a single WARNING — never raises (shared
  startup-path code, must-not-crash).
- ``_record_failure`` no longer TypeErrors after a poisoned construction.
- ``RedisConnectionManager.reset_instance()`` drops both the singleton and
  the lazily-cached config-manager stub, so the accessor returns a genuinely
  fresh instance.
"""

import logging
from unittest.mock import MagicMock

import pytest

import autobot_shared.redis_management.connection_manager as cm_module
from autobot_shared.redis_management.config import PoolConfig
from autobot_shared.redis_management.connection_manager import RedisConnectionManager

_CONFIG_LOGGER = "autobot_shared.redis_management.config"


@pytest.fixture()
def clean_singleton():
    """Isolate the singleton and the lazy config-manager cache per test.

    ``reset_instance()`` clears both (per #11830); run it before AND after so
    neither a prior suite's singleton nor ours leaks across tests.
    """
    RedisConnectionManager.reset_instance()
    yield
    RedisConnectionManager.reset_instance()


class TestPoolConfigValidation:
    def test_magicmock_values_fall_back_to_defaults_with_single_warning(self, caplog):
        garbage = MagicMock()
        with caplog.at_level(logging.WARNING, logger=_CONFIG_LOGGER):
            cfg = PoolConfig(
                max_connections=garbage,
                socket_timeout=garbage,
                socket_connect_timeout=garbage,
                retry_on_timeout=garbage,
                max_retries=garbage,
                health_check_interval=garbage,
                circuit_breaker_threshold=garbage,
                circuit_breaker_timeout=garbage,
            )
        assert cfg.max_connections == 20
        assert cfg.socket_timeout == 5.0
        assert cfg.socket_connect_timeout == 5.0
        assert cfg.retry_on_timeout is True
        assert cfg.max_retries == 3
        assert cfg.health_check_interval == 30.0
        assert cfg.circuit_breaker_threshold == 5
        assert cfg.circuit_breaker_timeout == 60
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING and r.name == _CONFIG_LOGGER]
        assert len(warnings) == 1, "exactly one WARNING per construction"
        assert "circuit_breaker_threshold" in warnings[0].getMessage()

    def test_none_and_str_fall_back_to_defaults(self):
        cfg = PoolConfig(circuit_breaker_threshold=None, max_retries="3", backoff_factor="fast")
        assert cfg.circuit_breaker_threshold == 5
        assert cfg.max_retries == 3
        assert cfg.backoff_factor == 2.0

    def test_bool_rejected_for_numeric_field(self):
        cfg = PoolConfig(circuit_breaker_threshold=True)
        assert cfg.circuit_breaker_threshold == 5

    def test_valid_values_pass_through_without_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger=_CONFIG_LOGGER):
            cfg = PoolConfig(circuit_breaker_threshold=7, socket_timeout=2, max_connections=50)
        assert cfg.circuit_breaker_threshold == 7
        assert cfg.socket_timeout == 2.0  # normalized to the field's float type
        assert cfg.max_connections == 50
        assert not [r for r in caplog.records if r.levelno == logging.WARNING and r.name == _CONFIG_LOGGER]

    def test_float_normalized_to_int_for_int_fields(self):
        # redis-py rejects float max_connections — int fields must stay int.
        cfg = PoolConfig(max_connections=100.0, circuit_breaker_threshold=5.0)
        assert cfg.max_connections == 100 and isinstance(cfg.max_connections, int)
        assert cfg.circuit_breaker_threshold == 5 and isinstance(cfg.circuit_breaker_threshold, int)


class TestPoisonedSingleton:
    def test_record_failure_no_typeerror_after_stubbed_construction(self, clean_singleton, monkeypatch):
        """Pre-#11830: constructing under a MagicMock config manager left a
        MagicMock circuit_breaker_threshold and _record_failure raised
        TypeError('>=' not supported between int and MagicMock)."""
        monkeypatch.setattr(cm_module, "_config_manager", MagicMock())
        manager = RedisConnectionManager()
        assert manager._pool_config.circuit_breaker_threshold == 5
        for _ in range(5):
            manager._record_failure("main", Exception("boom"))  # must not raise
        assert manager._circuit_open["main"] is True

    def test_reset_instance_returns_fresh_singleton_from_accessor(self, clean_singleton, monkeypatch):
        from autobot_shared.redis_client import _get_connection_manager

        monkeypatch.setattr(cm_module, "_config_manager", MagicMock())
        poisoned = _get_connection_manager()
        RedisConnectionManager.reset_instance()
        fresh = _get_connection_manager()
        assert fresh is not poisoned, "accessor must return a NEW instance after reset_instance()"
        assert isinstance(fresh._pool_config.circuit_breaker_threshold, int)

    def test_reset_instance_drops_cached_config_manager_stub(self, clean_singleton, monkeypatch):
        monkeypatch.setattr(cm_module, "_config_manager", MagicMock())
        RedisConnectionManager()
        RedisConnectionManager.reset_instance()
        assert cm_module._config_manager is None, "reset must drop the poisoned lazy config-manager cache"
