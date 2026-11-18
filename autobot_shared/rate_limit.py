# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared per-key sliding-window rate limiter (#7271).

Consolidates the duplicated implementation that previously lived (with
subtle differences and at least one P1 bug) in:

  * autobot-backend/api/openai_compat.py:_check_oai_rate_limit  (#6588)
  * autobot-backend/api/a2a.py:_check_rate_limit                (#7270)

State is shared across all uvicorn workers via a Redis sorted-set keyed
by ``f"{key_prefix}:{key}"``. Pipeline of:

    ZREMRANGEBYSCORE  <key>  0  (now - window_seconds)   # drop expired
    ZADD              <key>  now  uuid                   # record this request
    ZCARD             <key>                              # count after add
    EXPIRE            <key>  2 * window_seconds          # auto-evict idle keys

If Redis is unavailable (or the pipeline raises), the limiter falls back
to a per-process in-memory bucket so the endpoint stays responsive.
Degraded mode logs a warning and accepts the per-worker undercount —
strictly better than fail-closed for /v1/chat/completions.

Usage::

    from autobot_shared.rate_limit import IPRateLimiter

    _oai_limiter = IPRateLimiter(
        key_prefix="ratelimit:oai",
        limit_env="AUTOBOT_OAI_RATE_LIMIT",
        default_limit=60,
        window_seconds=60,
    )

    @router.post("/v1/chat/completions")
    async def chat_completions(...) -> None:
        await _oai_limiter.check_or_429(remote_addr)
        ...
"""

from __future__ import annotations

import logging
import os
import time
from typing import Dict, List
from uuid import uuid4

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Default cap on the in-process fallback bucket — prevents unbounded memory
# growth when Redis has been unavailable for an extended window.
_DEFAULT_BUCKET_MAX_KEYS = 10_000


class IPRateLimiter:
    """Per-key sliding-window rate limiter, Redis-backed with in-process fallback.

    Args:
        key_prefix: Stable prefix for Redis keys (e.g. ``"ratelimit:oai"``).
            The full key is ``f"{key_prefix}:{key}"`` where *key* is whatever
            is passed to :meth:`check_or_429` (typically a remote IP).
        limit_env: Environment variable name to read the limit from. If unset
            or unparseable, *default_limit* is used.
        default_limit: Fallback limit when *limit_env* is unset or invalid.
        window_seconds: Sliding window size (default 60).
        bucket_max_keys: Cap on the in-process fallback bucket size before
            stale-key eviction kicks in. Only applies to the fallback path.

    The Redis path is the production-correct enforcement; the in-process
    path exists only so the endpoint stays responsive during Redis outages.
    """

    def __init__(
        self,
        *,
        key_prefix: str,
        limit_env: str,
        default_limit: int,
        window_seconds: int = 60,
        bucket_max_keys: int = _DEFAULT_BUCKET_MAX_KEYS,
    ) -> None:
        self._key_prefix = key_prefix
        self._limit_env = limit_env
        self._default_limit = default_limit
        self._window_seconds = window_seconds
        self._bucket_max_keys = bucket_max_keys
        # Per-process fallback only — production uses Redis sorted-set.
        self._inprocess_buckets: Dict[str, List[float]] = {}

    @property
    def limit(self) -> int:
        """Read the limit from env each call so dynamic config is respected."""
        try:
            return int(os.environ.get(self._limit_env, self._default_limit))  # ssot-config-exempt: dynamic env var name
        except (TypeError, ValueError):
            return self._default_limit

    def _redis_key(self, key: str) -> str:
        return f"{self._key_prefix}:{key}"

    async def check_or_429(self, key: str) -> None:
        """Enforce the limit; raise ``HTTPException(429)`` if exceeded.

        Tries Redis first. On Redis unavailability or pipeline error, falls
        back to the in-process bucket and logs a warning.

        Args:
            key: Stable per-caller identifier — typically remote IP. Combined
                with *key_prefix* to form the Redis key.
        """
        from autobot_shared.redis_client import get_async_redis_client

        redis = await get_async_redis_client()
        if redis is None:
            logger.warning(
                "Redis unavailable for %s rate-limit; falling back to in-process bucket "
                "(per-worker, undercounts under multi-worker)",
                self._key_prefix,
            )
            self._check_inprocess_or_429(key)
            return

        full_key = self._redis_key(key)
        now = time.time()
        window_start = now - self._window_seconds
        try:
            async with redis.pipeline(transaction=False) as pipe:
                pipe.zremrangebyscore(full_key, 0, window_start)
                pipe.zadd(full_key, {f"{now}:{uuid4()}": now})
                pipe.zcard(full_key)
                pipe.expire(full_key, 2 * self._window_seconds)
                results = await pipe.execute()
            count = int(results[2])
        except Exception as exc:
            logger.warning(
                "Redis %s rate-limit pipeline failed (%s) — falling back to in-process",
                self._key_prefix,
                exc,
            )
            self._check_inprocess_or_429(key)
            return

        if count > self.limit:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded ({self.limit} requests/{self._window_seconds}s). Try again later.",
            )

    def _check_inprocess_or_429(self, key: str) -> None:
        """Per-process fallback (#6588 pattern, retained for outage handling).

        State is per-worker — does NOT enforce the documented limit across
        uvicorn workers. Only used when Redis is unreachable.
        """
        now = time.time()
        window_start = now - self._window_seconds
        bucket = [t for t in self._inprocess_buckets.get(key, []) if t > window_start]
        limit = self.limit
        if len(bucket) >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded ({limit} requests/{self._window_seconds}s). Try again later.",
            )
        bucket.append(now)
        self._inprocess_buckets[key] = bucket
        if len(self._inprocess_buckets) > self._bucket_max_keys:
            cutoff = now - self._window_seconds
            stale = [k for k, ts in self._inprocess_buckets.items() if not any(t > cutoff for t in ts)]
            for k in stale:
                del self._inprocess_buckets[k]

    # Test/debug helper — production code should not depend on this.
    def _reset_inprocess(self) -> None:  # pragma: no cover
        self._inprocess_buckets.clear()


__all__ = ["IPRateLimiter"]
