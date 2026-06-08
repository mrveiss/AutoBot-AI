# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Retry-with-backoff primitive.

See docs/developer/PRIMITIVES.md for the full inventory and #5059/#5060
for the extraction-first methodology.
"""

import asyncio
import logging
from typing import Awaitable, Callable, Tuple, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_DEFAULT_RETRYABLE: Tuple[Type[Exception], ...] = (Exception,)


async def retry_with_backoff(
    fn: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 3,
    base_delay_s: float = 1.0,
    max_delay_s: float = 60.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = _DEFAULT_RETRYABLE,
    label: str = "operation",
) -> T:
    """Call *fn* up to ``max_retries + 1`` times with exponential back-off.

    Back-off formula: ``min(base_delay_s * 2^(attempt-1), max_delay_s)``.
    Re-raises the last exception when all attempts are exhausted.

    Args:
        fn: Zero-argument async callable to retry.
        max_retries: Number of additional attempts after the first failure.
        base_delay_s: Delay before the first retry (seconds).
        max_delay_s: Upper bound on delay (prevents unbounded waits).
        retryable_exceptions: Only retry on these exception types. Defaults
            to ``(Exception,)`` — retry on any non-BaseException.
        label: Human-readable name used in log messages.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except retryable_exceptions as exc:
            last_exc = exc
            if attempt >= max_retries:
                logger.error(
                    "%s failed after %d attempt(s): %s",
                    label,
                    attempt + 1,
                    exc,
                )
                break
            delay = min(base_delay_s * (2**attempt), max_delay_s)
            logger.warning(
                "%s attempt %d/%d failed (%s) — retrying in %.1fs",
                label,
                attempt + 1,
                max_retries + 1,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]
