# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""REDIS_HOST env resolution in RedisConnectionManager._load_redis_config (#12778).

The slm-agent unit sets REDIS_HOST/AUTOBOT_REDIS_HOST, but _load_redis_config
never read either. It asked the backend ConfigManager — unimportable under the
agent's SYSTEM interpreter — and then fell back to NetworkConstants.REDIS_VM_IP,
which resolves to the EMPTY STRING in that context. _validate_config_host
(#11449) then correctly refused to dial a blank host, so the agent silently
dropped every event it collected, including the backend crash-loop transition
that is the one signal that would surface a crashing service in the GUI.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SHARED_ROOT = Path(__file__).resolve().parents[2]


def _load_connection_manager():
    """Load connection_manager.py standalone (heavy package __init__ chain)."""
    name = "_cm_12778"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, _SHARED_ROOT / "autobot_shared" / "redis_management" / "connection_manager.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_cm = pytest.importorskip("redis") and _load_connection_manager()


class TestRedisHostFromEnv:
    def test_reads_redis_host(self, monkeypatch):
        monkeypatch.delenv("AUTOBOT_REDIS_HOST", raising=False)
        monkeypatch.setenv("REDIS_HOST", "127.0.0.1")
        assert _cm.RedisConnectionManager._redis_host_from_env() == "127.0.0.1"

    def test_reads_autobot_redis_host(self, monkeypatch):
        """The slm-agent unit sets BOTH; either alone must work."""
        monkeypatch.delenv("REDIS_HOST", raising=False)
        monkeypatch.setenv("AUTOBOT_REDIS_HOST", "10.0.0.9")
        assert _cm.RedisConnectionManager._redis_host_from_env() == "10.0.0.9"

    def test_prefers_redis_host_over_autobot_prefixed(self, monkeypatch):
        monkeypatch.setenv("REDIS_HOST", "first")
        monkeypatch.setenv("AUTOBOT_REDIS_HOST", "second")
        assert _cm.RedisConnectionManager._redis_host_from_env() == "first"

    def test_blank_and_whitespace_are_not_a_host(self, monkeypatch):
        """An empty env var must not shadow the fallback — a blank host is the
        exact failure mode this issue is about."""
        monkeypatch.setenv("REDIS_HOST", "   ")
        monkeypatch.delenv("AUTOBOT_REDIS_HOST", raising=False)
        assert _cm.RedisConnectionManager._redis_host_from_env() is None

    def test_returns_none_when_unset(self, monkeypatch):
        monkeypatch.delenv("REDIS_HOST", raising=False)
        monkeypatch.delenv("AUTOBOT_REDIS_HOST", raising=False)
        assert _cm.RedisConnectionManager._redis_host_from_env() is None


class TestLoadRedisConfigPrecedence:
    """Order must be: config-manager value > env > NetworkConstants fallback."""

    def _mgr(self):
        return _cm.RedisConnectionManager.__new__(_cm.RedisConnectionManager)

    def test_env_used_when_config_manager_is_unavailable(self, monkeypatch):
        """The agent's actual situation: no importable config layer."""
        monkeypatch.setattr(_cm, "_get_config_manager", lambda: None)
        monkeypatch.setenv("REDIS_HOST", "127.0.0.1")
        assert self._mgr()._load_redis_config()["host"] == "127.0.0.1"

    def test_env_used_when_constants_resolve_empty(self, monkeypatch):
        """NetworkConstants.REDIS_VM_IP is '' outside the backend interpreter —
        the env var must win rather than yielding a blank host."""
        monkeypatch.setattr(_cm, "_get_config_manager", lambda: None)
        monkeypatch.setattr(_cm.NetworkConstants, "REDIS_VM_IP", "", raising=False)
        monkeypatch.setenv("REDIS_HOST", "127.0.0.1")
        assert self._mgr()._load_redis_config()["host"] == "127.0.0.1"

    def test_explicit_config_manager_host_beats_env(self, monkeypatch):
        """A centrally-configured deployment must not be overridden by a stray
        env var."""

        class _CM:
            @staticmethod
            def get_redis_config():
                return {"host": "configured-host", "port": 6379}

        monkeypatch.setattr(_cm, "_get_config_manager", lambda: _CM())
        monkeypatch.setenv("REDIS_HOST", "env-host")
        assert self._mgr()._load_redis_config()["host"] == "configured-host"

    def test_falls_back_to_constants_when_nothing_else_set(self, monkeypatch):
        monkeypatch.setattr(_cm, "_get_config_manager", lambda: None)
        monkeypatch.setattr(_cm.NetworkConstants, "REDIS_VM_IP", "10.0.0.4", raising=False)
        monkeypatch.delenv("REDIS_HOST", raising=False)
        monkeypatch.delenv("AUTOBOT_REDIS_HOST", raising=False)
        assert self._mgr()._load_redis_config()["host"] == "10.0.0.4"
