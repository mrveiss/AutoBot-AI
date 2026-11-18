# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A stale-cache reload that reaches a config reader on the same thread
must neither deadlock nor recurse (#18661).

The real chain is get_nested -> _reload_config -> load_configuration ->
defaults -> network_constants -> registry -> redis -> service registry ->
get. Each test runs the call in a daemon thread and joins with a deadline,
so a regression fails instead of hanging the suite.
"""

import asyncio
import threading

from config.async_ops import AsyncOperationsMixin
from config.sync_ops import SyncOperationsMixin

DEADLINE_S = 5.0


class _ReentrantConfig(SyncOperationsMixin):
    """Minimal mixin host whose reload reads config on the same thread."""

    CACHE_DURATION = 60

    def __init__(self):
        self._sync_lock = None
        self._sync_reloading = False
        self._sync_cache_timestamp = None
        self._config = {"logging": {"file": "old"}}
        self.reloads = 0

    def _reload_config(self):
        self.reloads += 1
        # Re-entry, as the service registry does mid-reload.
        self.get("deployment_mode", "local")
        self.get_nested("logging.file")
        self._config = {"logging": {"file": "new"}}
        self._sync_cache_timestamp = 1e18


def _call_with_deadline(fn):
    result = {}

    def run():
        result["value"] = fn()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(DEADLINE_S)
    assert not t.is_alive(), "config call deadlocked on its own lock (#18661)"
    return result["value"]


def test_get_nested_with_a_stale_cache_survives_reentry_from_the_reload():
    cfg = _ReentrantConfig()
    assert _call_with_deadline(lambda: cfg.get_nested("logging.file")) == "new"
    assert cfg.reloads == 1


def test_get_with_a_stale_cache_survives_reentry_from_the_reload():
    cfg = _ReentrantConfig()
    assert _call_with_deadline(lambda: cfg.get("logging")) == {"file": "new"}
    assert cfg.reloads == 1


def test_explicit_reload_survives_reentry_and_clears_the_flag():
    cfg = _ReentrantConfig()
    _call_with_deadline(cfg.reload)
    assert cfg.reloads == 1
    assert cfg._sync_reloading is False


def test_a_failed_reload_clears_the_reentry_flag():
    cfg = _ReentrantConfig()

    def boom():
        raise RuntimeError("load failed")

    cfg._reload_config = boom
    try:
        cfg.reload()
    except RuntimeError:
        pass
    assert cfg._sync_reloading is False


class _ReentrantAsyncConfig(AsyncOperationsMixin, _ReentrantConfig):
    """The async main-config read shares the sync lock and guard (#18661)."""

    def __init__(self):
        super().__init__()
        self._async_lock = None


def test_async_main_load_reloads_once_when_the_reload_reenters():
    cfg = _ReentrantAsyncConfig()
    got = _call_with_deadline(lambda: asyncio.run(cfg.load_config_async("main")))
    assert got == {"logging": {"file": "new"}}
    assert cfg.reloads == 1
