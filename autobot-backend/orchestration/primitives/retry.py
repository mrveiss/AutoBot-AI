# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Retry-with-backoff primitive.

See docs/developer/PRIMITIVES.md for the full inventory and #5059/#5060
for the extraction-first methodology.

The back-off itself is `autobot_shared.retry_mechanism` (#17855): this keeps the primitive's
contract (the last exception propagates unchanged, no jitter) over the one implementation.
"""

from typing import Awaitable, Callable, Tuple, Type, TypeVar

from autobot_shared.retry_mechanism import RetryExhaustedError, RetryMechanism, RetryPolicy, RetryStrategy

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
    policy = RetryPolicy(
        max_attempts=max_retries + 1,
        base_delay=base_delay_s,
        max_delay=max_delay_s,
        backoff_multiplier=2.0,
        jitter=False,
        strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
        retryable_exceptions=retryable_exceptions,
        non_retryable_exceptions=(),
    )
    try:
        return await RetryMechanism(policy).execute_async(fn, operation_name=label)
    except RetryExhaustedError as exhausted:
        raise exhausted.last_exception from None
