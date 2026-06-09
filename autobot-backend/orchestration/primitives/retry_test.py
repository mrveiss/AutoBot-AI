# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for orchestration/primitives/retry.py (#5060)."""

from unittest.mock import AsyncMock, patch

import pytest

from orchestration.primitives.retry import retry_with_backoff


class _Boom(Exception):
    pass


class _Permanent(Exception):
    pass


@pytest.mark.asyncio
async def test_success_on_first_attempt():
    fn = AsyncMock(return_value="ok")
    result = await retry_with_backoff(fn, max_retries=3, label="test")
    assert result == "ok"
    fn.assert_awaited_once()


@pytest.mark.asyncio
async def test_retries_then_succeeds():
    call_count = 0

    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise _Boom("transient")
        return "success"

    with patch("orchestration.primitives.retry.asyncio.sleep", new_callable=AsyncMock):
        result = await retry_with_backoff(flaky, max_retries=3, label="test")

    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_raises_after_exhausted_retries():
    fn = AsyncMock(side_effect=_Boom("always fails"))

    with patch("orchestration.primitives.retry.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(_Boom, match="always fails"):
            await retry_with_backoff(fn, max_retries=2, label="test")

    assert fn.await_count == 3  # 1 initial + 2 retries


@pytest.mark.asyncio
async def test_non_retryable_exception_propagates_immediately():
    fn = AsyncMock(side_effect=_Permanent("not retryable"))

    with patch("orchestration.primitives.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with pytest.raises(_Permanent):
            await retry_with_backoff(
                fn,
                max_retries=3,
                retryable_exceptions=(_Boom,),
                label="test",
            )

    fn.assert_awaited_once()
    mock_sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_backoff_delay_grows_exponentially():
    call_count = 0

    async def always_fail():
        nonlocal call_count
        call_count += 1
        raise _Boom("fail")

    delays = []
    with patch("orchestration.primitives.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = lambda d: delays.append(d)
        with pytest.raises(_Boom):
            await retry_with_backoff(
                always_fail,
                max_retries=3,
                base_delay_s=1.0,
                max_delay_s=60.0,
                label="test",
            )

    assert delays == [1.0, 2.0, 4.0]


@pytest.mark.asyncio
async def test_max_delay_caps_backoff():
    async def always_fail():
        raise _Boom("fail")

    delays = []
    with patch("orchestration.primitives.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = lambda d: delays.append(d)
        with pytest.raises(_Boom):
            await retry_with_backoff(
                always_fail,
                max_retries=5,
                base_delay_s=10.0,
                max_delay_s=15.0,
                label="test",
            )

    assert all(d <= 15.0 for d in delays)
