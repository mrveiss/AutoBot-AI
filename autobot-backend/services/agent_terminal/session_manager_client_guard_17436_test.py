# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A coroutine is not a Redis client, and truthiness cannot tell (#17436, #16499).

`initialization/agent_presence_sync` called the SYNC `get_redis_client(async_client=True)`
without awaiting it, so the service received a **coroutine object** as its client.
Two things then hid it:

* the service is a process-wide singleton built by whichever caller arrives first,
  and this one runs during startup -- so every later consumer inherited it;
* the guard was `if self.redis_client:`, and **a coroutine is truthy**, so
  `_persist_session` ran against it.

The same fault at a second site (`initialization/neural_mesh_wiring`, #16499) had
the same shape: an un-awaited client handed to a consumer that awaits methods on it.

These tests assert the REFUSAL, not the absence of a RuntimeWarning. A warning
assertion goes green as soon as anyone adds an `await` anywhere, including the
wrong one.
"""

from __future__ import annotations

import pytest

from services.agent_terminal.session_manager import _usable_redis


async def _a_coroutine() -> None:
    """A real coroutine object, which is what the defect actually passed."""


class _FakeRedis:
    """A capability-complete fake: the guard must accept this."""

    async def hgetall(self, *_a: object, **_k: object) -> dict:
        return {}

    async def hset(self, *_a: object, **_k: object) -> int:
        return 1


def test_a_coroutine_is_truthy_which_is_why_the_old_guard_passed() -> None:
    """The defect's mechanism, pinned. If this ever fails, the rest is moot."""
    coro = _a_coroutine()
    try:
        assert bool(coro) is True, "a coroutine is truthy -- that is why `if client:` passed"
    finally:
        coro.close()


def test_the_guard_refuses_a_coroutine() -> None:
    coro = _a_coroutine()
    try:
        assert _usable_redis(coro) is False
    finally:
        coro.close()


def test_the_guard_refuses_none() -> None:
    assert _usable_redis(None) is False


def test_the_guard_refuses_an_object_that_merely_exists() -> None:
    """A Mock, a partial, a half-built client -- all truthy, none usable."""
    assert _usable_redis(object()) is False


def test_the_guard_accepts_a_capability_complete_client() -> None:
    """Checked by capability, not isinstance, so test fakes still work."""
    assert _usable_redis(_FakeRedis()) is True


def test_the_service_refuses_a_coroutine_at_construction() -> None:
    """The singleton must not be constructible with a bad client.

    Refusing at first use would be too late: the instance is shared, so the bad
    client would already be installed for every other consumer.
    """
    from services.agent_terminal.session_manager import SessionManager

    coro = _a_coroutine()
    try:
        with pytest.raises(TypeError, match="not a usable Redis client"):
            SessionManager(redis_client=coro)
    finally:
        coro.close()


def test_the_service_still_accepts_no_client_at_all() -> None:
    """`None` is a supported configuration -- Redis is optional here."""
    from services.agent_terminal.session_manager import SessionManager

    assert SessionManager(redis_client=None) is not None
