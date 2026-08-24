# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Backend unit tests never open a Redis socket (#13446).

Whether they did used to depend on who imported ``autobot_shared.redis_client``
first — collection order, and under ``-n auto --dist loadscope`` whichever files
the worker happened to be handed. When the genuine module won that race, every
``await get_async_redis_client()`` spent the client's full retry budget: 60s per
call, 121s for the 56 Redis-agnostic tests in
``tests/services/test_claim_verifier.py``.

The backend root conftest now installs a stand-in for exactly the four windows
that belong to that directory. These tests assert both halves of the contract
from inside one of them: the connection factories hand back None, and every
other attribute is still the genuine module's object rather than a MagicMock.
"""

import sys
import time

import pytest

_KEY = "autobot_shared.redis_client"


def test_module_in_scope_is_the_standin():
    """``sys.modules`` holds the stand-in while a backend test runs.

    A bare ``types.ModuleType`` has no ``__file__``; the genuine module does.
    """
    mod = sys.modules.get(_KEY)
    assert mod is not None, f"{_KEY} is not installed at all"
    assert mod.__name__ == _KEY
    assert getattr(mod, "__file__", None) is None, "the genuine module is live — no window opened"


async def test_async_factory_returns_none_without_a_socket():
    """The documented "Redis unavailable" answer, immediately."""
    from autobot_shared.redis_client import get_async_redis_client

    started = time.monotonic()
    assert await get_async_redis_client() is None
    assert await get_async_redis_client(database="main") is None
    # A genuine client spends its retry budget before giving up. The stand-in
    # cannot take a measurable amount of time, so this doubles as the assertion
    # that no connection was attempted.
    assert time.monotonic() - started < 1.0


def test_sync_factory_returns_none_not_a_mock():
    """The sync factory needs the same treatment as the async one.

    ``config.registry._fetch_from_redis()`` treats any truthy client as usable
    and would hand a MagicMock straight back as a configuration *value*.
    """
    from autobot_shared.redis_client import get_redis_client

    assert get_redis_client() is None
    assert get_redis_client(database="main") is None


def test_unrelated_attributes_are_the_genuine_ones():
    """Only the two factories are replaced; everything else delegates.

    ``monitoring/redis_prometheus_metrics_test.py`` drives the real
    ``RedisConnectionManager`` with a mocked metrics manager — a MagicMock in
    its place turns each of its assertions into a tautology.
    """
    pytest.importorskip("redis")
    from autobot_shared.redis_client import RedisConnectionManager

    assert isinstance(RedisConnectionManager, type)
    assert RedisConnectionManager.__module__.startswith("autobot_shared.redis_management")
