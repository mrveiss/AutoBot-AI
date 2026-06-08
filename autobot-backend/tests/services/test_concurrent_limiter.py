# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for ConcurrentWorkflowLimiter DROP_OLDEST policy. Issue #2573."""

import asyncio

import pytest

from services.workflow_automation.concurrent_limiter import (
    ConcurrencyLimitError,
    ConcurrentWorkflowLimiter,
    OverflowPolicy,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_limiter(max_concurrent: int = 1, callback=None) -> ConcurrentWorkflowLimiter:
    """Create a fresh DROP_OLDEST limiter (not the singleton)."""
    return ConcurrentWorkflowLimiter(
        max_concurrent=max_concurrent,
        overflow_policy=OverflowPolicy.DROP_OLDEST,
        cancel_callback=callback,
    )


async def _noop_callback(workflow_id: str) -> None:
    """Callback that does nothing — tests that poll the slot handle cleanup."""


# ---------------------------------------------------------------------------
# DROP_OLDEST: no callback registered → ConcurrencyLimitError
# ---------------------------------------------------------------------------


class TestDropOldestNoCallback:
    """DROP_OLDEST without a cancel callback must raise ConcurrencyLimitError."""

    @pytest.mark.asyncio
    async def test_raises_when_no_callback(self) -> None:
        limiter = _make_limiter(max_concurrent=1, callback=None)
        await limiter.acquire("wf-a")

        with pytest.raises(ConcurrencyLimitError) as exc_info:
            await limiter.acquire("wf-b")

        assert exc_info.value.workflow_id == "wf-b"
        assert exc_info.value.limit == 1

    @pytest.mark.asyncio
    async def test_raises_after_callback_cleared(self) -> None:
        """Setting callback to None after registration must re-raise the error."""
        limiter = _make_limiter(max_concurrent=1)
        limiter.register_cancel_callback(None)  # type: ignore[arg-type]
        await limiter.acquire("wf-a")

        with pytest.raises(ConcurrencyLimitError):
            await limiter.acquire("wf-b")


# ---------------------------------------------------------------------------
# DROP_OLDEST: callback invoked and slot claimed
# ---------------------------------------------------------------------------


class TestDropOldestCallbackInvoked:
    """Verify the cancel callback receives the correct workflow_id."""

    @pytest.mark.asyncio
    async def test_callback_called_with_oldest_id(self) -> None:
        evicted: list[str] = []

        async def track_cancel(workflow_id: str) -> None:
            evicted.append(workflow_id)

        limiter = _make_limiter(max_concurrent=1, callback=track_cancel)
        await limiter.acquire("wf-old")

        # Simulate callback also releasing the slot (normal teardown path)
        async def releasing_cancel(workflow_id: str) -> None:
            evicted.append(workflow_id)
            await limiter.release(workflow_id)

        limiter.register_cancel_callback(releasing_cancel)
        await limiter.acquire("wf-new")

        assert evicted == ["wf-old"], f"Expected ['wf-old'], got {evicted}"

    @pytest.mark.asyncio
    async def test_new_workflow_claims_slot_after_eviction(self) -> None:
        async def releasing_cancel(workflow_id: str) -> None:
            await limiter.release(workflow_id)

        limiter = _make_limiter(max_concurrent=1, callback=releasing_cancel)
        await limiter.acquire("wf-old")

        await limiter.acquire("wf-new")

        assert "wf-new" in limiter._running
        assert "wf-old" not in limiter._running
        assert limiter.running_count == 1

    @pytest.mark.asyncio
    async def test_oldest_workflow_is_evicted_not_newest(self) -> None:
        """With max=2 and 2 running, the one started first must be evicted."""
        evicted: list[str] = []

        async def releasing_cancel(workflow_id: str) -> None:
            evicted.append(workflow_id)
            await limiter.release(workflow_id)

        limiter = _make_limiter(max_concurrent=2, callback=releasing_cancel)
        await limiter.acquire("wf-first")
        # Brief sleep so timestamps differ reliably
        await asyncio.sleep(0.01)
        await limiter.acquire("wf-second")

        await limiter.acquire("wf-third")

        assert evicted == ["wf-first"], f"Expected ['wf-first'], got {evicted}"
        assert "wf-third" in limiter._running
        assert "wf-second" in limiter._running
        assert "wf-first" not in limiter._running


# ---------------------------------------------------------------------------
# DROP_OLDEST: late callback registration via register_cancel_callback
# ---------------------------------------------------------------------------


class TestRegisterCancelCallback:
    """register_cancel_callback enables DROP_OLDEST after construction."""

    @pytest.mark.asyncio
    async def test_late_registration_enables_drop_oldest(self) -> None:
        limiter = _make_limiter(max_concurrent=1, callback=None)
        await limiter.acquire("wf-a")

        async def releasing_cancel(workflow_id: str) -> None:
            await limiter.release(workflow_id)

        limiter.register_cancel_callback(releasing_cancel)

        # Must succeed — no longer raises NotImplementedError or ConcurrencyLimitError
        await limiter.acquire("wf-b")

        assert "wf-b" in limiter._running
        assert "wf-a" not in limiter._running

    @pytest.mark.asyncio
    async def test_callback_can_be_replaced(self) -> None:
        """A second register_cancel_callback call replaces the previous one."""
        call_log: list[str] = []

        async def first_cb(workflow_id: str) -> None:
            call_log.append(f"first:{workflow_id}")
            await limiter.release(workflow_id)

        async def second_cb(workflow_id: str) -> None:
            call_log.append(f"second:{workflow_id}")
            await limiter.release(workflow_id)

        limiter = _make_limiter(max_concurrent=1, callback=first_cb)
        await limiter.acquire("wf-a")
        limiter.register_cancel_callback(second_cb)
        await limiter.acquire("wf-b")

        assert call_log == ["second:wf-a"]


# ---------------------------------------------------------------------------
# DROP_OLDEST: force-eviction when callback does NOT call release()
# ---------------------------------------------------------------------------


class TestDropOldestForceEviction:
    """When callback does not call release(), limiter force-removes after timeout."""

    @pytest.mark.asyncio
    async def test_force_eviction_after_stale_callback(self) -> None:
        """Callback that never calls release() — slot must still be reclaimed."""

        async def stale_cancel(workflow_id: str) -> None:
            # Intentionally does NOT call limiter.release()
            pass

        limiter = _make_limiter(max_concurrent=1, callback=stale_cancel)
        await limiter.acquire("wf-stuck")

        # Monkey-patch the deadline to be very short so the test doesn't take 5 s
        import time as _time

        original_monotonic = _time.monotonic
        call_count = 0

        def fast_monotonic():
            nonlocal call_count
            call_count += 1
            # Return a value past the 5-second deadline after the first call
            return original_monotonic() + 10.0

        import unittest.mock as _mock

        with _mock.patch(
            "services.workflow_automation.concurrent_limiter.time.monotonic",
            side_effect=fast_monotonic,
        ):
            await limiter.acquire("wf-new")

        assert "wf-new" in limiter._running
        assert "wf-stuck" not in limiter._running


# ---------------------------------------------------------------------------
# Backward compatibility: REJECT and QUEUE policies unchanged
# ---------------------------------------------------------------------------


class TestExistingPoliciesUnchanged:
    """Ensure REJECT and QUEUE still work correctly after the refactor."""

    @pytest.mark.asyncio
    async def test_reject_still_raises(self) -> None:
        limiter = ConcurrentWorkflowLimiter(max_concurrent=1, overflow_policy=OverflowPolicy.REJECT)
        await limiter.acquire("wf-a")

        with pytest.raises(ConcurrencyLimitError):
            await limiter.acquire("wf-b")

    @pytest.mark.asyncio
    async def test_queue_still_waits(self) -> None:
        limiter = ConcurrentWorkflowLimiter(max_concurrent=1, overflow_policy=OverflowPolicy.QUEUE)
        await limiter.acquire("wf-a")

        acquired = False

        async def acquire_and_flag():
            nonlocal acquired
            await limiter.acquire("wf-b")
            acquired = True

        task = asyncio.create_task(acquire_and_flag())
        await asyncio.sleep(0.05)
        assert not acquired, "wf-b should still be queued"

        await limiter.release("wf-a")
        await asyncio.sleep(0.05)
        assert acquired, "wf-b should have been promoted after wf-a released"

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
