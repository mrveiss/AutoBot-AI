# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``autobot_shared.retry_mechanism.RetryStrategy`` serves the rate limiter (#18459).

``rate_limiter`` carried a three-member ``RetryStrategy`` (EXPONENTIAL, LINEAR,
FIXED) that was a strict subset of the shared enum. It now consumes the shared
one; the delay curve for each former member is unchanged.
"""

from autobot_shared.retry_mechanism import RetryStrategy
from llm_shared.optimization import rate_limiter
from llm_shared.optimization.rate_limiter import RateLimitConfig, RateLimitHandler


def _delay(strategy: RetryStrategy, attempt: int) -> float:
    config = RateLimitConfig(base_delay=2.0, max_delay=1000.0, jitter_factor=0.0, strategy=strategy)
    return RateLimitHandler(config=config)._calculate_delay(attempt)


def test_the_rate_limiter_defines_no_retry_strategy_of_its_own():
    assert rate_limiter.RetryStrategy is RetryStrategy
    assert RateLimitConfig().strategy is RetryStrategy.EXPONENTIAL_BACKOFF


def test_each_former_member_keeps_its_delay_curve():
    assert [_delay(RetryStrategy.EXPONENTIAL_BACKOFF, a) for a in range(3)] == [2.0, 4.0, 8.0]
    assert [_delay(RetryStrategy.LINEAR_BACKOFF, a) for a in range(3)] == [2.0, 4.0, 6.0]
    assert [_delay(RetryStrategy.FIXED_DELAY, a) for a in range(3)] == [2.0, 2.0, 2.0]


def test_the_shared_only_member_is_exponential_with_jitter():
    assert _delay(RetryStrategy.JITTERED_BACKOFF, 2) == 8.0
