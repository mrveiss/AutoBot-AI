# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared Redis client ACL username (#16626): optional, env-sourced, passed to every pool.

Everything behind ``get_redis_client`` builds its pools here. A username must
reach both the async and the sync pool when configured, and must be absent (so
redis-py sends today's password-only ``AUTH``) when it is not.
"""

import pytest

from autobot_shared.redis_management.config import RedisConfig, RedisConfigLoader
from autobot_shared.redis_management.connection_manager import RedisConnectionManager

_ENV = (
    "REDIS_USERNAME",
    "AUTOBOT_REDIS_USERNAME",
    "REDIS_PASSWORD",
    "AUTOBOT_REDIS_PASSWORD",
    "AUTOBOT_REDIS_TLS_ENABLED",
)
#: A fixture value, not a credential.
_PW = "pw"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def _no_redis_env(monkeypatch):
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)


def _manager() -> RedisConnectionManager:
    # Only the pool builders are exercised; they read nothing but the keepalive options.
    manager = object.__new__(RedisConnectionManager)
    manager._tcp_keepalive_options = {}
    return manager


def test_username_is_unset_by_default():
    assert RedisConfig(name="main", db=0).username is None


def test_username_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("AUTOBOT_REDIS_USERNAME", "default")
    assert RedisConfig(name="main", db=0).username == "default"


def test_redis_username_wins_over_the_autobot_name(monkeypatch):
    """Same precedence as the password: REDIS_* first, then AUTOBOT_REDIS_*."""
    monkeypatch.setenv("REDIS_USERNAME", "first")
    monkeypatch.setenv("AUTOBOT_REDIS_USERNAME", "second")
    assert RedisConfig(name="main", db=0).username == "first"


def test_a_yaml_database_entry_carries_its_username():
    config = RedisConfigLoader._parse_database_config("main", {"db": 0, "username": "default"})
    assert config.username == "default"


def test_the_async_pool_gets_the_username():
    config = RedisConfig(name="main", db=0, host="127.0.0.1", password=_PW, username="default")
    assert _manager()._build_async_pool_params(config, "main")["username"] == "default"


def test_the_sync_pool_gets_the_username():
    config = RedisConfig(name="main", db=0, host="127.0.0.1", password=_PW, username="default")
    pool = _manager()._create_sync_pool_with_keepalive("main", config)
    assert pool.connection_kwargs["username"] == "default"


def test_no_username_keeps_the_password_only_pool():
    config = RedisConfig(name="main", db=0, host="127.0.0.1", password=_PW)
    pool = _manager()._create_sync_pool_with_keepalive("main", config)
    assert "username" not in pool.connection_kwargs
    assert pool.connection_kwargs["password"] == _PW
