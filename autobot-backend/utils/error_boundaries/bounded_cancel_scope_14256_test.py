# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``bounded()`` signals the pooled work it dispatched, not just the wait (#14256, #14244).

#14015/PR #14243 shipped the route deadline: a hung handler now returns a 504
naming itself instead of holding the socket open forever. That turns the
AWAIT into a 504, but ``asyncio.wait_for`` cannot stop work already running in
a ``ThreadPoolExecutor`` -- the thread keeps walking whatever it was walking,
holding a worker slot the next request needs (#12779, #13602).

These tests assert the other half: a cancel token any pooled work registers
via ``utils.cancel_tokens`` gets signalled by ``bounded()`` on expiry (and on
an outer cancellation reaching the route before its own deadline does) --
without ``bounded()`` importing anything about what the handler dispatched.
"""

from __future__ import annotations

import asyncio
import threading

import pytest
from fastapi import HTTPException

from autobot_shared.error_boundaries import bounded
from utils import cancel_tokens as ct


class TestBoundedSignalsOnTimeout:
    @pytest.mark.asyncio
    async def test_a_token_registered_by_the_handler_is_signalled_on_expiry(self):
        """The reproduction: a handler that dispatches pooled work and then
        hangs must leave that work signalled, not merely return a 504."""
        token = ct.new_cancel_token()

        @bounded(0.05, operation="dispatches_pooled_work")
        async def handler():
            ct.register_cancel_token("pooled_work", token)
            await asyncio.Event().wait()  # never returns on its own

        with pytest.raises(HTTPException) as exc:
            await asyncio.wait_for(handler(), timeout=10)

        assert exc.value.status_code == 504
        assert token.is_set(), "bounded() must signal every token the handler registered"

    @pytest.mark.asyncio
    async def test_run_cancellable_registered_work_is_reachable_from_bounded(self):
        """End-to-end: a handler using run_cancellable (the #14244 helper) with
        NO timeout of its own is still stopped by bounded()'s deadline alone."""
        release = threading.Event()

        def _blocks_until_released():
            release.wait(timeout=5)
            return "should never be observed"

        @bounded(0.05, operation="uses_run_cancellable")
        async def handler():
            return await ct.run_cancellable(None, _blocks_until_released, operation="pooled_work")

        with pytest.raises(HTTPException) as exc:
            await asyncio.wait_for(handler(), timeout=10)

        assert exc.value.status_code == 504
        release.set()

    @pytest.mark.asyncio
    async def test_a_call_site_with_no_cancelled_error_handling_of_its_own_is_still_reached(self):
        """The ambient scope's actual value: a call site that does NOT itself
        catch CancelledError (bare submit_cancellable(), unlike
        run_cancellable()) still gets its token signalled -- bounded() reaches
        in via the scope rather than relying on every call site's own
        diligence to propagate the signal. This is what makes the mechanism
        safe by default for a call site added later without that diligence.
        """
        release = threading.Event()
        holder: dict[str, threading.Event] = {}

        def _blocks_until_released():
            release.wait(timeout=5)
            return "should never be observed"

        @bounded(0.05, operation="bare_submit_cancellable")
        async def handler():
            future, token = ct.submit_cancellable(None, _blocks_until_released, operation="pooled_work")
            holder["token"] = token
            return await future  # deliberately no try/except around this

        with pytest.raises(HTTPException) as exc:
            await asyncio.wait_for(handler(), timeout=10)

        assert exc.value.status_code == 504
        assert holder["token"].is_set(), "bounded() must reach a token registered via bare submit_cancellable"
        release.set()


class TestBoundedSignalsOnOuterCancellation:
    @pytest.mark.asyncio
    async def test_a_cancellation_reaching_bounded_before_its_own_deadline_still_signals(self):
        """Reachable via graceful shutdown or a tighter outer deadline (#14256:
        same treatment as a timeout). CancelledError is not TimeoutError and
        must not fall through unsignalled."""
        token = ct.new_cancel_token()
        started = asyncio.Event()

        @bounded(30.0, operation="outlives_the_test")
        async def handler():
            ct.register_cancel_token("pooled_work", token)
            started.set()
            await asyncio.Event().wait()

        task = asyncio.ensure_future(handler())
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert token.is_set(), "an outer cancellation must signal registered tokens exactly like a timeout"


class TestBoundedDoesNotSignalOnSuccess:
    @pytest.mark.asyncio
    async def test_a_request_that_completes_normally_is_not_flagged_cancelled(self):
        """Negative case (#14244's verification bar): success must not be
        reported as an abandoned/cancelled scan."""
        token = ct.new_cancel_token()

        @bounded(5.0, operation="completes_normally")
        async def handler():
            ct.register_cancel_token("pooled_work", token)
            return "ok"

        result = await handler()

        assert result == "ok"
        assert not token.is_set(), "a token from a successful call must never be signalled"


class TestBoundedScopeIsolation:
    @pytest.mark.asyncio
    async def test_a_token_registered_outside_any_bounded_call_is_not_touched(self):
        """register_cancel_token() is a no-op with no scope open -- a token
        created before any bounded() call must be unaffected by one expiring."""
        stray_token = ct.new_cancel_token()  # never registered anywhere

        @bounded(0.05, operation="unrelated")
        async def handler():
            await asyncio.Event().wait()

        with pytest.raises(HTTPException):
            await asyncio.wait_for(handler(), timeout=10)

        assert not stray_token.is_set()

    @pytest.mark.asyncio
    async def test_two_concurrent_bounded_calls_do_not_cross_signal(self):
        """Each bounded() call opens its own scope -- one route's expiry must
        never signal a concurrently-running, unrelated route's pooled work."""
        token_slow = ct.new_cancel_token()
        token_fast = ct.new_cancel_token()

        @bounded(0.05, operation="slow_route")
        async def slow_handler():
            ct.register_cancel_token("slow", token_slow)
            await asyncio.Event().wait()

        @bounded(5.0, operation="fast_route")
        async def fast_handler():
            ct.register_cancel_token("fast", token_fast)
            return "ok"

        with pytest.raises(HTTPException):
            await asyncio.wait_for(
                asyncio.gather(slow_handler(), fast_handler()),
                timeout=10,
            )

        assert token_slow.is_set(), "the route that actually timed out must be signalled"
        assert not token_fast.is_set(), "an unrelated concurrent route must not be cross-signalled"
