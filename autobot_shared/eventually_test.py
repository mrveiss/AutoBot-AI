# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for autobot_shared.eventually (#16009)."""

import asyncio

import pytest

from autobot_shared.eventually import eventually


@pytest.mark.asyncio
async def test_a_condition_that_already_holds_returns_at_once():
    await eventually(lambda: True, deadline=1.0)


@pytest.mark.asyncio
async def test_a_condition_made_true_by_another_task_is_waited_for():
    seen: list[int] = []

    async def producer() -> None:
        await asyncio.sleep(0.05)
        seen.append(1)

    task = asyncio.create_task(producer())
    await eventually(lambda: seen, deadline=5.0)
    await task


@pytest.mark.asyncio
async def test_a_condition_that_never_holds_times_out():
    """The deadline is the only thing that can end this wait, so it cannot race."""
    with pytest.raises(asyncio.TimeoutError):
        await eventually(lambda: False, deadline=0.05)


@pytest.mark.asyncio
async def test_a_watched_task_that_raises_surfaces_its_own_error():
    """A loop that died must say why, not wait out the deadline and report a count."""

    async def dies() -> None:
        raise RuntimeError("loop died")

    task = asyncio.create_task(dies())
    with pytest.raises(RuntimeError, match="loop died"):
        await eventually(lambda: False, deadline=5.0, watch=task)


@pytest.mark.asyncio
async def test_a_watched_task_that_returns_early_fails_the_wait():
    async def returns() -> None:
        return None

    task = asyncio.create_task(returns())
    with pytest.raises(AssertionError, match="finished before the condition held"):
        await eventually(lambda: False, deadline=5.0, watch=task)
