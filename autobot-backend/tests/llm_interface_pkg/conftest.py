# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Keep the provider unit tests in this package off the network (#13361).

``BaseProvider.chat_completion`` takes a token from the cross-worker rate
limiter (#8170) before every call, and that limiter reaches Redis.  The
provider tests here drive fully mocked SDK clients and assert nothing about
rate limiting, so whether Redis answers is none of their business — but until
now it decided how long they took.

They were fast only by accident.  ``tests/knowledge/test_cleanup_endpoint.py``
rebound ``redis.Redis`` and ``redis.asyncio.Redis`` to ``MagicMock`` **on the
real module objects** at import time and never put them back, so any session
that collected it handed every later test an instantly-answering Redis.  With
that gone (#13361) the four ``chat_completion`` tests in this package each
spend the client's full connect-and-retry budget — measured at 30s apiece,
120s per session — before the limiter gives up and allows the call.

The fixture makes the limiter's Redis lookup fail immediately, which is the
documented "Redis unavailable -> allow all" path of
``LLMCrossWorkerRateLimiter``, not a bypass of it: ``acquire()`` and
``try_acquire()`` run for real and the fallback they already implement is
what answers.  Nothing is installed in ``sys.modules``, and ``monkeypatch``
undoes the attribute at teardown, so this cannot become the next #13361.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def offline_llm_rate_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the cross-worker rate limiter take its Redis-unavailable path."""

    async def _no_redis(_self: object) -> None:
        raise ConnectionError("Redis is deliberately unavailable in provider unit tests (#13361)")

    monkeypatch.setattr(
        "llm_shared.cross_worker_rate_limiter.LLMCrossWorkerRateLimiter._get_redis",
        _no_redis,
    )
