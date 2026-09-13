# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Non-blocking Redis writes for observability records (#15637).

This module used to be called ``autobot_shared/fire_and_forget.py`` and it was
the wrong thing under the obvious name. Two helpers existed:

* ``autobot_shared.async_compat.fire_and_forget`` — retains the task until it
  finishes and logs a failure. Correct, but filed under a name nobody reaches
  for.
* ``autobot_shared.fire_and_forget.run_redis_write`` — a second, *non*-retaining
  implementation, with more than twice the consumers.

Anyone importing by the obvious name got the weaker one, and its docstring read
as though it were the safe one. The file is now named for what it actually
provides — one Redis-write helper — and the launch itself delegates to the
single canonical retaining implementation in ``async_compat``.

## Why the retention matters here specifically

``run_redis_write`` carries audit-log, JWT-revocation and event-log writes. The
event loop keeps only a WEAK reference to a task, so a launch whose handle is
discarded can be garbage-collected mid-flight (#15522). For an audit trail that
is a record that silently never lands, under load, non-deterministically — and
the old failure path logged at ``debug``, so it produced no warning and no gap
anyone would notice. Failures now surface at ``error`` through
``fire_and_forget``'s done callback.

## What it still does NOT do

The write is not awaited: the caller returns before the record is durable. All
five call sites were checked against that, and every one of them is a thin
fire-and-forget wrapper over a coroutine a caller can await directly when it
needs the record confirmed — ``audit.emit`` over ``record``, ``audit_log``'s
wrapper over ``record_event``, ``event_log``'s over ``_write_event``,
``mcp_process``'s trace span over ``write_span``.

``run_jwt.revoke_run_jwt`` is the one with a security edge, and the codebase
already answers it: ``revoke_run_jwt_async`` awaits the same denylist write and
its docstring names breach response as the case that must use it. The
fire-and-forget variant is documented for end-of-run cleanup, and the denylist
entry's TTL is the token's own remaining lifetime — so a lost write shortens
revocation to that remaining lifetime rather than failing open indefinitely.
"""

from __future__ import annotations

from typing import Any, Coroutine

from autobot_shared.async_compat import fire_and_forget
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def run_redis_write(coro: Coroutine[Any, Any, None], *, label: str) -> None:
    """Schedule *coro* as a retained background task and return immediately.

    The task is held by :func:`autobot_shared.async_compat.fire_and_forget`
    until it completes, so it cannot be collected before it runs, and a failure
    is logged at ``error`` by that helper's done callback instead of vanishing.
    Nothing is raised to the caller either way — an observability write must not
    break the hot path it hangs off.

    Args:
        coro: Coroutine to run (typically a Redis write).
        label: Identifies the call site in the background-task logs.
    """
    try:
        fire_and_forget(coro, name=label)
    except RuntimeError:
        # No running loop in this thread: ``create_task`` cannot schedule
        # anything. Close the coroutine so it does not emit a "never awaited"
        # warning at collection time, and say so — a skipped audit write is not
        # a debug-level event.
        logger.warning("%s: no running event loop — background write skipped", label)
        coro.close()
