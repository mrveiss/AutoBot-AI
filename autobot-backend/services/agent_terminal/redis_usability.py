# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Is this object something that can actually serve a Redis call? (#17436)

Split out of ``session_manager`` (#17435): two modules already imported it
across the package boundary, and the file it lived in reached the 600-line
ceiling when this guard and #17422's conversation-ownership refusal landed on
it in the same day. Neither change alone crossed the line, which is why the
split happens here rather than in either of them.

The name is public now. ``api/agent_terminal_access`` was importing
``_usable_redis`` from another module already; a leading underscore that three
modules reach past is documentation that disagrees with the code.
"""

from __future__ import annotations

import inspect

__all__ = ["usable_redis"]


def usable_redis(client: object) -> bool:
    """True only for something that can actually serve a Redis call (#17436).

    NOT a truthiness test, deliberately. A coroutine object is truthy, so
    `if self.redis_client:` passed for the un-awaited
    `get_redis_client(async_client=True)` that `initialization/agent_presence_sync`
    handed in -- and `_persist_session` then ran against a coroutine. So are a
    Mock, a half-built client and a functools.partial: the guard read as a client
    check and was a presence check, which passes for every wrong value anyone has
    actually passed.

    Checked by capability, not isinstance, so a genuine fake still works.

    Rejects a COROUTINE, not everything awaitable. That distinction is the
    whole guard: ``redis.asyncio.Redis`` implements ``__await__`` for its lazy
    connection setup, so ``inspect.isawaitable`` is True for every correct
    async client -- and an earlier version of this function tested exactly
    that, which refused the properly-awaited client it was written to protect.
    ``fakeredis.aioredis.FakeRedis`` is awaitable for the same reason and was
    refused too; ``session_manager_tenant_16975_test`` is what caught it.

    The suite could not have caught it earlier: its double was a hand-rolled
    sync object with the three methods and no ``__await__``, so it passed
    under both the broken check and the correct one. A test double that is
    not awaitable cannot notice a guard that rejects awaitables, which is why
    ``test_a_genuine_async_client_is_usable`` below builds one that is.

    The methods are the ones ``SessionManager`` calls -- measured, not assumed:
    `get`, `setex`, `delete`. An earlier version checked `hgetall`/`hset`,
    carried over from EdgeLearner (#16499) and never called here; such a client
    passed the guard and failed inside `_persist_session`, which catches and
    logs -- session stays in memory, nothing says so. Checking the WRONG
    capability is the truthiness bug again, just harder to see.
    """
    if client is None or inspect.iscoroutine(client):
        return False
    return all(callable(getattr(client, name, None)) for name in ("get", "setex", "delete"))
