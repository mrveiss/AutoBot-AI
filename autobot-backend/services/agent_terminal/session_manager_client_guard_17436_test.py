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

import inspect

import pytest

from services.agent_terminal.redis_usability import usable_redis


async def _a_coroutine() -> None:
    """A real coroutine object, which is what the defect actually passed."""


class _FakeRedis:
    """A capability-complete fake: the guard must accept this.

    These are the methods `SessionManager` actually calls. Keeping the fake and
    the guard on the same list is deliberate -- if they drift, the test starts
    certifying a client shape the real code cannot use.
    """

    async def get(self, *_a: object, **_k: object) -> None:
        return None

    async def setex(self, *_a: object, **_k: object) -> bool:
        return True

    async def delete(self, *_a: object, **_k: object) -> int:
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
        assert usable_redis(coro) is False
    finally:
        coro.close()


def test_the_guard_refuses_none() -> None:
    assert usable_redis(None) is False


def test_the_guard_refuses_an_object_that_merely_exists() -> None:
    """A Mock, a partial, a half-built client -- all truthy, none usable."""
    assert usable_redis(object()) is False


def test_the_guard_accepts_a_capability_complete_client() -> None:
    """Checked by capability, not isinstance, so test fakes still work."""
    assert usable_redis(_FakeRedis()) is True


def test_a_genuine_async_client_is_usable_even_though_it_is_awaitable() -> None:
    """The guard must reject a COROUTINE, not everything awaitable (#17435).

    ``redis.asyncio.Redis`` implements ``__await__`` for its lazy connection
    setup, so ``inspect.isawaitable`` is True for every correct async client.
    An earlier version of the guard tested exactly that and therefore refused
    the properly-awaited client it exists to admit --
    ``fakeredis.aioredis.FakeRedis`` was rejected in
    ``session_manager_tenant_16975_test`` for the same reason.

    The double is hand-built rather than imported so this holds without
    fakeredis, and the ``isawaitable`` assertion is not decoration: without it
    someone could drop ``__await__`` from the double and this test would pass
    while testing nothing.
    """

    class _AsyncRedis:
        def __await__(self):
            yield
            return self

        async def get(self, *args, **kwargs):
            return None

        async def setex(self, *args, **kwargs):
            return True

        async def delete(self, *args, **kwargs):
            return 1

    client = _AsyncRedis()

    assert inspect.isawaitable(client) is True, "the double no longer has the property under test"
    assert inspect.iscoroutine(client) is False, "an async client is awaitable but is not a coroutine"
    assert usable_redis(client) is True


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


def test_a_client_missing_the_methods_this_class_calls_is_refused() -> None:
    """The guard must check what SessionManager USES, not what looks Redis-shaped.

    `hgetall`/`hset` is a real Redis client shape and the wrong one here: this
    class calls `get`, `setex` and `delete`. Such a client would pass a
    capability guard aimed at the wrong methods, then fail inside
    `_persist_session` -- which catches and logs, leaving the session in memory
    and nothing to say so.
    """

    class _WrongShape:
        async def hgetall(self, *_a: object, **_k: object) -> dict:
            return {}

        async def hset(self, *_a: object, **_k: object) -> int:
            return 1

    assert usable_redis(_WrongShape()) is False


def test_a_later_usable_client_is_adopted_by_an_existing_singleton(monkeypatch) -> None:
    """Awaiting the client is not enough if the singleton was already built without one.

    `chat_workflow/tool_handler.py` calls `ensure_agent_terminal_service` with no
    `redis_client` at all. On that ordering the singleton is built with `None`,
    and every later client -- however correctly awaited -- was discarded. So the
    await fix alone would have been inert on exactly the path that matters.
    """
    from api import agent_terminal_access as access

    monkeypatch.setattr(access, "_agent_terminal_service_instance", None)
    first = access.ensure_agent_terminal_service(redis_client=None)
    assert first.redis_client is None, "precondition: built without a client"

    client = _FakeRedis()
    second = access.ensure_agent_terminal_service(redis_client=client)

    assert second is first, "the singleton must not be rebuilt"
    assert second.redis_client is client, "a usable later client must be adopted"
    assert second.session_manager.redis_client is client, "the collaborator must be updated too"


def test_an_unusable_later_client_is_not_adopted(monkeypatch) -> None:
    """The upgrade only ever installs something usable."""
    from api import agent_terminal_access as access

    monkeypatch.setattr(access, "_agent_terminal_service_instance", None)
    service = access.ensure_agent_terminal_service(redis_client=None)

    coro = _a_coroutine()
    try:
        access.ensure_agent_terminal_service(redis_client=coro)
    finally:
        coro.close()

    assert service.redis_client is None, "a coroutine must never be adopted"


def test_a_working_client_is_not_swapped_out(monkeypatch) -> None:
    """Never replace a usable client -- in-flight callers hold it."""
    from api import agent_terminal_access as access

    monkeypatch.setattr(access, "_agent_terminal_service_instance", None)
    original = _FakeRedis()
    service = access.ensure_agent_terminal_service(redis_client=original)

    access.ensure_agent_terminal_service(redis_client=_FakeRedis())

    assert service.redis_client is original, "a usable client must not be replaced"
