# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The 'main' database must not resolve to an empty Redis host (#14299).

Observed on a deployed SLM backend: ``NetworkConstants.REDIS_VM_IP`` depends on
``config.registry.ConfigRegistry``, which lives only in autobot-backend (see
its own docstring: "avoiding dependency issues when autobot_shared is used
independently"). ``autobot-slm-backend/config.py`` is a single file, not a
package, so ``config.registry`` cannot resolve there at all — every tier
before ``autobot_shared.ssot_config`` came up empty on that process, and
`RedisConfig.host`'s dataclass field default froze whatever NetworkConstants
answered at whichever process imported ``redis_management.config`` first.

Two things had to change together for the 'main' database specifically
(#12778's tests already cover ``_load_redis_config``'s OTHER tiers — this
file only adds the new one and the 'main'-specific wiring):

1. ``_ssot_redis_host`` — a new fallback tier in ``_load_redis_config`` that
   consults ``autobot_shared.ssot_config`` (no ConfigRegistry dependency,
   works from any process) before finally defaulting to '127.0.0.1'.
2. ``_init_configurations`` / ``_load_configurations`` — 'main' now takes its
   host from ``self._config["host"]`` (the resolved chain above) instead of
   ``RedisConfig.host``'s frozen class-level default, which never went
   through that chain at all.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SHARED_ROOT = Path(__file__).resolve().parents[2]


def _load_connection_manager():
    """Load connection_manager.py standalone (heavy package __init__ chain)."""
    name = "_cm_14299"
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


def _mgr():
    return _cm.RedisConnectionManager.__new__(_cm.RedisConnectionManager)


@pytest.fixture(autouse=True)
def _fresh_ssot_config():
    """``ssot_config.get_config()`` is process-wide ``@lru_cache(maxsize=1)``
    (#14299) — any test anywhere in the session that already constructed it
    freezes ``.vm.redis`` for the rest of the process, so an env-var change
    here would silently do nothing. Clear before AND after so neither a
    prior test's cache nor this one's env changes leak."""
    import autobot_shared.ssot_config as ssot_config

    ssot_config.get_config.cache_clear()
    yield
    ssot_config.get_config.cache_clear()


class TestSsotRedisHostFallback:
    def test_ssot_config_used_when_network_constants_and_env_both_empty(self, monkeypatch):
        """The exact SLM-backend shape: config-manager unimportable, no env
        vars set, NetworkConstants resolves to '' (ConfigRegistry
        unavailable). ssot_config's own default ('127.0.0.1') must still
        produce a non-empty, connectable host."""
        monkeypatch.setattr(_cm, "_get_config_manager", lambda: None)
        monkeypatch.setattr(_cm.NetworkConstants, "REDIS_VM_IP", "", raising=False)
        monkeypatch.delenv("REDIS_HOST", raising=False)
        monkeypatch.delenv("AUTOBOT_REDIS_HOST", raising=False)

        host = _mgr()._load_redis_config()["host"]

        assert host, "host resolved to empty even after the ssot_config fallback (#14299)"
        assert host.strip() == host, "must already be stripped, not left to the caller"

    def test_ssot_redis_host_defaults_to_loopback_with_nothing_set(self, monkeypatch):
        """Sanity: with nothing set at all, ssot_config's own field default
        must be the loopback — the same co-located default every other
        Ansible-templated component already falls back to."""
        monkeypatch.delenv("AUTOBOT_REDIS_HOST", raising=False)

        assert _cm.RedisConnectionManager._ssot_redis_host() == "127.0.0.1"

    def test_ssot_config_honours_an_explicit_autobot_redis_host(self, monkeypatch):
        """ssot_config reads AUTOBOT_REDIS_HOST itself — a deployment that
        sets it must resolve to the configured value, not the '127.0.0.1'
        default (distinguishes "genuinely unconfigured" from "configured to
        something else")."""
        monkeypatch.setenv("AUTOBOT_REDIS_HOST", "10.0.0.9")

        assert _cm.RedisConnectionManager._ssot_redis_host() == "10.0.0.9"

    def test_ssot_redis_host_never_raises_when_ssot_config_unavailable(self, monkeypatch):
        """A process where autobot_shared.ssot_config itself cannot import
        (e.g. pydantic missing) must degrade to '', not propagate — the
        caller's final `or "127.0.0.1"` is the true last resort."""
        import builtins

        real_import = builtins.__import__

        def _blocked_import(name, *args, **kwargs):
            if name == "autobot_shared.ssot_config" or name.startswith("autobot_shared.ssot_config"):
                raise ImportError("simulated: ssot_config unavailable")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _blocked_import)

        assert _cm.RedisConnectionManager._ssot_redis_host() == ""

    def test_main_database_config_uses_the_resolved_host_not_the_frozen_default(self, monkeypatch):
        """The actual reported symptom: database='main' specifically. A fresh
        manager (full __init__) must not carry an empty host for 'main' when
        every upstream tier is empty and only ssot_config's default answers."""
        monkeypatch.setattr(_cm, "_get_config_manager", lambda: None)
        monkeypatch.setattr(_cm.NetworkConstants, "REDIS_VM_IP", "", raising=False)
        monkeypatch.delenv("REDIS_HOST", raising=False)
        monkeypatch.delenv("AUTOBOT_REDIS_HOST", raising=False)

        _cm.RedisConnectionManager.reset_instance()
        try:
            manager = _cm.RedisConnectionManager()
            main_config = manager._configs["main"]
            assert main_config.host, "'main' resolved to an empty host — the exact #14299 symptom"
        finally:
            _cm.RedisConnectionManager.reset_instance()
