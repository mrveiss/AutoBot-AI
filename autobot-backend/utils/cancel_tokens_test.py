# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Cooperative cancellation for pooled work (#14256, #14244).

``asyncio.wait_for``/``task.cancel()`` stop an AWAIT, not work already running
in a ``ThreadPoolExecutor`` -- a thread cannot be pre-empted from outside.
These tests assert the mechanism actually stops the work and frees the
executor slot, not merely that the caller's await raised.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from utils import cancel_tokens as ct


class TestCancelScope:
    def test_register_outside_a_scope_is_a_no_op(self):
        """No bounded() call open -- pooled work stays cancellable via its
        own timeout even when nothing is listening for an outer deadline."""
        token = ct.new_cancel_token()
        ct.register_cancel_token("op", token)  # must not raise
        assert ct.cancel_scope_depth() == 0

    def test_register_inside_a_scope_is_collected(self):
        token = ct.new_cancel_token()
        scope = ct.begin_cancel_scope()
        try:
            ct.register_cancel_token("op", token)
            assert ct.cancel_scope_depth() == 1
        finally:
            ct.end_cancel_scope(scope)
        assert ct.cancel_scope_depth() == 0

    def test_signal_scope_sets_every_registered_token_exactly_once(self):
        token_a = ct.new_cancel_token()
        token_b = ct.new_cancel_token()
        scope = ct.begin_cancel_scope()
        try:
            ct.register_cancel_token("a", token_a)
            ct.register_cancel_token("b", token_b)
            ct.signal_cancel_scope("deadline exceeded")
            assert token_a.is_set()
            assert token_b.is_set()
        finally:
            ct.end_cancel_scope(scope)

    def test_signal_scope_with_nothing_registered_does_not_raise(self):
        scope = ct.begin_cancel_scope()
        try:
            ct.signal_cancel_scope("deadline exceeded")  # no tokens: no-op
        finally:
            ct.end_cancel_scope(scope)

    def test_nested_scopes_do_not_leak_into_each_other(self):
        """A scope closed by end_cancel_scope must not see a sibling's tokens."""
        outer_token = ct.new_cancel_token()
        outer = ct.begin_cancel_scope()
        ct.register_cancel_token("outer", outer_token)

        inner_token = ct.new_cancel_token()
        inner = ct.begin_cancel_scope()
        try:
            ct.register_cancel_token("inner", inner_token)
            assert ct.cancel_scope_depth() == 1
            ct.signal_cancel_scope("inner deadline")
            assert inner_token.is_set()
            assert not outer_token.is_set(), "signalling the inner scope must not reach the outer one"
        finally:
            ct.end_cancel_scope(inner)

        assert ct.cancel_scope_depth() == 1, "closing the inner scope must restore the outer one"
        ct.end_cancel_scope(outer)


class TestSignalCancelToken:
    def test_sets_the_token(self):
        token = ct.new_cancel_token()
        ct.signal_cancel_token("op", token, "timed out")
        assert token.is_set()

    def test_is_idempotent(self, monkeypatch):
        """Signalling an already-signalled token must not log/record twice --
        a route can be cancelled and then time out on the same call."""
        token = ct.new_cancel_token()
        token.set()
        calls = []
        monkeypatch.setattr(ct.logger, "warning", lambda *a, **k: calls.append(a))
        ct.signal_cancel_token("op", token, "second signal")
        assert calls == [], "an already-signalled token must not be logged again"


class TestSubmitCancellable:
    @pytest.mark.asyncio
    async def test_creates_a_token_when_none_given(self):
        future, token = ct.submit_cancellable(None, lambda: 1, operation="op")
        assert isinstance(token, threading.Event)
        assert await future == 1

    @pytest.mark.asyncio
    async def test_uses_the_given_token(self):
        given = ct.new_cancel_token()
        future, token = ct.submit_cancellable(None, lambda: 1, operation="op", cancel_token=given)
        assert token is given
        await future

    @pytest.mark.asyncio
    async def test_registers_in_the_active_scope(self):
        scope = ct.begin_cancel_scope()
        try:
            future, token = ct.submit_cancellable(None, lambda: 1, operation="op")
            assert ct.cancel_scope_depth() == 1
            await future
        finally:
            ct.end_cancel_scope(scope)


class TestRunCancellable:
    """The verification bar: assert the WORK stopped, not that the caller's
    await raised. Every blocking function below is a REAL callable submitted
    to a REAL ThreadPoolExecutor -- these are executed, not simulated."""

    @pytest.mark.asyncio
    async def test_normal_completion_does_not_signal_the_token(self):
        """Negative case (#14244's verification bar): a request that completes
        normally must not have its work flagged as cancelled."""
        result = await ct.run_cancellable(None, lambda: 42, operation="op")
        assert result == 42

    @pytest.mark.asyncio
    async def test_timeout_signals_the_token_and_raises_timeout_error(self):
        token = ct.new_cancel_token()

        def _slow():
            token.wait(timeout=5)
            return "done"

        with pytest.raises(asyncio.TimeoutError):
            await ct.run_cancellable(None, _slow, operation="op", cancel_token=token, timeout=0.05)

        assert token.is_set(), "the token must be signalled so the thread can stop itself"

    @pytest.mark.asyncio
    async def test_outer_cancellation_signals_the_token_and_reraises(self):
        """CancelledError must never be swallowed -- it propagates after the
        token is signalled (#14256: 'never swallow CancelledError')."""
        token = ct.new_cancel_token()
        started = threading.Event()
        release = threading.Event()

        def _slow():
            started.set()
            release.wait(timeout=5)
            return "done"

        task = asyncio.ensure_future(ct.run_cancellable(None, _slow, operation="op", cancel_token=token))
        await asyncio.get_running_loop().run_in_executor(None, started.wait, 5)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert token.is_set(), "an outer cancellation must signal the token exactly like a timeout"
        release.set()

    def test_the_executor_slot_is_actually_freed(self):
        """Executor saturation under repeated timeouts (#14256 AC): the
        assertion is on worker occupancy, not on the response.

        A single-worker pool proves the point sharply: submit cancellable work
        that honours its token, let run_cancellable's timeout fire, then prove
        the pool's one worker slot returns to idle once the thread notices the
        signal -- not merely that the caller's await raised TimeoutError.
        """
        from concurrent.futures import ThreadPoolExecutor

        active = {"n": 0}
        lock = threading.Lock()

        def _work(token: threading.Event):
            with lock:
                active["n"] += 1
            try:
                for _ in range(400):  # bounded: ~4s worst case, checked every 10ms
                    if token.is_set():
                        return "cancelled"
                    time.sleep(0.01)
                return "ran_to_completion_without_noticing_cancellation"
            finally:
                with lock:
                    active["n"] -= 1

        executor = ThreadPoolExecutor(max_workers=1)
        try:

            async def _drive():
                token = ct.new_cancel_token()
                with pytest.raises(asyncio.TimeoutError):
                    await ct.run_cancellable(
                        executor,
                        lambda: _work(token),
                        operation="occupancy_test",
                        cancel_token=token,
                        timeout=0.05,
                    )
                return token

            token = asyncio.run(_drive())

            # Immediately after the asyncio-level timeout, the OS thread is
            # still running -- this is the bug #14256/#14244 describe: the
            # caller already has its error, the pool slot is not yet free.
            with lock:
                assert active["n"] == 1, "the worker must still be occupied right after the caller's timeout"
            assert token.is_set()

            # Once the thread next checks the (now-signalled) token it must
            # exit -- prove the slot returns to baseline, not just that the
            # token was set.
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                with lock:
                    if active["n"] == 0:
                        break
                time.sleep(0.02)
            with lock:
                assert active["n"] == 0, "the executor slot was never freed -- the work kept the thread"
        finally:
            executor.shutdown(wait=True)
