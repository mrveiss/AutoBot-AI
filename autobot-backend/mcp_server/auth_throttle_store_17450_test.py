# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The shared throttle degrades to per-process, and says so every time (#17450).

The degradation is the owner's decision and its worst case equals what already
ships, so it adds no outage mode and no new attack. The LOGGING is what keeps it
honest: a silent fallback becomes permanent -- the store fails once, nobody
notices, and the control reverts to the per-worker weakness this exists to
remove. **An unlogged degradation is the same defect arriving by another route**,
so it is tested as a behaviour rather than trusted as a comment.

Every test here uses a store that FAILS, because a test against a working store
cannot distinguish shared from degraded -- the same trap as testing a
worker-sharing fix at `--workers 1`.
"""

from __future__ import annotations

import logging

import pytest

from mcp_server.auth_throttle_store import SharedThrottleStore, StoreUnavailable


class _DeadRedis:
    """Every call raises, as an unreachable Redis does."""

    def __getattr__(self, _name: str):
        def _boom(*_a: object, **_k: object):
            raise ConnectionError("redis is down")

        return _boom


class _CountingRedis:
    """Minimal working double, enough to prove the shared path is taken."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._sets: dict[str, set] = {}
        self._keys: dict[str, str] = {}

    def zremrangebyscore(self, key, _lo, _hi):
        self.calls.append("zremrangebyscore")
        return 0

    def zcard(self, key):
        self.calls.append("zcard")
        return len(self._sets.get(key, ()))

    def zadd(self, key, mapping):
        self.calls.append("zadd")
        self._sets.setdefault(key, set()).update(mapping)
        return 1

    def expire(self, _key, _ttl):
        return True

    def setex(self, key, _ttl, value):
        self.calls.append("setex")
        self._keys[key] = value
        return True

    def ttl(self, key):
        return 42 if key in self._keys else -2

    def exists(self, key):
        return 1 if key in self._keys else 0

    def delete(self, *keys):
        for k in keys:
            self._keys.pop(k, None)
            self._sets.pop(k, None)
        return len(keys)


def test_an_unavailable_store_raises_rather_than_answering() -> None:
    """It must never substitute a local answer -- the caller owns degradation."""
    store = SharedThrottleStore(lambda: _DeadRedis())
    with pytest.raises(StoreUnavailable):
        store.failures_in_window("1.2.3.4", 60.0)


def test_degradation_is_logged_the_first_time(caplog) -> None:
    """A silent fallback becomes permanent. This is the assertion that stops it."""
    store = SharedThrottleStore(lambda: _DeadRedis())
    with caplog.at_level(logging.WARNING):
        with pytest.raises(StoreUnavailable):
            store.failures_in_window("1.2.3.4", 60.0)
    assert any(
        "DEGRADED" in r.message or "DEGRADED" in r.getMessage() for r in caplog.records
    ), "degrading to per-process state must be logged, or the control reverts silently"


def test_degradation_is_logged_once_not_per_call(caplog) -> None:
    """Only state CHANGES are logged. Logging every failure would bury the event."""
    store = SharedThrottleStore(lambda: _DeadRedis())
    with caplog.at_level(logging.WARNING):
        for _ in range(5):
            with pytest.raises(StoreUnavailable):
                store.failures_in_window("1.2.3.4", 60.0)
    degraded = [r for r in caplog.records if "DEGRADED" in r.getMessage()]
    assert len(degraded) == 1, f"expected one degradation log, got {len(degraded)}"


def test_recovery_is_logged_as_a_state_change(caplog) -> None:
    """Coming back is as important to see as going down."""
    flaky = {"dead": True}

    def factory():
        return _DeadRedis() if flaky["dead"] else _CountingRedis()

    store = SharedThrottleStore(factory)
    with pytest.raises(StoreUnavailable):
        store.failures_in_window("1.2.3.4", 60.0)

    flaky["dead"] = False
    with caplog.at_level(logging.INFO):
        store.failures_in_window("1.2.3.4", 60.0)
    assert any("RECOVERED" in r.getMessage() for r in caplog.records), "returning to shared state must be logged too"


def test_the_shared_path_is_actually_used_when_the_store_works() -> None:
    """Without this, every other test here passes against a store nobody calls."""
    redis = _CountingRedis()
    store = SharedThrottleStore(lambda: redis)
    store.add_failure("1.2.3.4", 60.0)
    assert "zadd" in redis.calls, "add_failure must reach the shared store"
    assert store.failures_in_window("1.2.3.4", 60.0) == 1


def test_a_lockout_is_reported_from_shared_state() -> None:
    redis = _CountingRedis()
    store = SharedThrottleStore(lambda: redis)
    assert store.lockout_remaining("1.2.3.4") == 0.0
    store.arm_lockout("1.2.3.4", 30.0)
    assert store.lockout_remaining("1.2.3.4") > 0


def test_success_clears_this_ip_but_is_not_a_global_reset() -> None:
    """The global counter must survive a success -- it bounds address rotation.

    Draining it on any single success would hand a rotating attacker a reset
    button. That reasoning predates this change and must survive the port.
    """
    redis = _CountingRedis()
    store = SharedThrottleStore(lambda: redis)
    store.add_failure("1.2.3.4", 60.0)
    store.add_global_failure(60.0)

    store.mark_success("1.2.3.4", 60.0)

    assert store.failures_in_window("1.2.3.4", 60.0) == 0, "the IP's own failures clear"
    assert store.global_failures_in_window(60.0) == 1, "the endpoint-wide count must NOT clear"
