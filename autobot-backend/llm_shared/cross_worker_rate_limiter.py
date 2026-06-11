# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Centralized LLM Rate Limiter — Shared Across All Uvicorn Workers (Issue #8170)

When uvicorn runs with ``--workers N``, each worker is a separate OS process
with its own memory space.  An in-process rate limiter (e.g., a Python
``asyncio.Semaphore``) is invisible to sibling workers — so the effective
aggregate rate is N× the configured limit, causing provider 429s.

This module implements a **proactive** Redis-backed token-bucket rate limiter
for each LLM provider.  Before issuing any request to a provider's API, callers
acquire a token.  If the bucket is empty they wait (or raise immediately,
depending on the ``blocking`` flag).  All workers share the same Redis keys, so
the aggregate rate is correctly bounded regardless of worker count.

Token bucket algorithm
----------------------
Each provider bucket has two parameters:

- ``capacity`` (burst capacity, tokens)
- ``refill_rate`` (tokens per second, i.e. sustained RPM / 60)

Redis stores ``(tokens_float, last_refill_timestamp)`` per provider in a
single hash key using a Lua script for atomic check-and-decrement.

Key naming: ``autobot:llm:rl:{provider}``

Provider defaults
-----------------
Defaults are conservative approximations of free-tier limits.  Operators
should override via environment variables or ``ssot_config`` for their actual
provider plan:

  AUTOBOT_LLM_RL_{PROVIDER}_RPM   (requests per minute)
  AUTOBOT_LLM_RL_{PROVIDER}_BURST (burst tokens, defaults to RPM)

Usage::

    limiter = get_llm_rate_limiter()
    async with limiter.acquire("openai"):
        response = await openai_client.chat(...)

    # Or non-blocking:
    allowed, retry_after = await limiter.try_acquire("anthropic")
    if not allowed:
        raise RateLimitError(f"Retry after {retry_after:.1f}s", retry_after=retry_after)
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Optional, Tuple

from autobot_shared.env_utils import env_int

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider defaults  (RPM = requests per minute)
# ---------------------------------------------------------------------------
_PROVIDER_DEFAULTS: Dict[str, Tuple[int, int]] = {
    # (rpm, burst)
    "openai": (500, 500),
    "anthropic": (60, 60),
    "groq": (30, 30),
    "ollama": (600, 600),  # local, generous
    "vllm": (600, 600),  # local
    "huggingface": (30, 30),
    "openrouter": (60, 60),
    "custom_openai": (120, 120),
    "default": (60, 60),
}

# Lua script: atomic token-bucket check-and-decrement.
# Keys[1]  = hash key, e.g. "autobot:llm:rl:openai"
# Args[1]  = capacity (float string)
# Args[2]  = refill_rate (tokens/second, float string)
# Args[3]  = current timestamp (float string)
# Returns: "1" if token acquired, "0:{retry_after_seconds}" if denied
_LUA_ACQUIRE = """
local key      = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate     = tonumber(ARGV[2])
local now      = tonumber(ARGV[3])

local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1]) or capacity
local ts     = tonumber(data[2]) or now

-- Refill
local elapsed = math.max(0, now - ts)
tokens = math.min(capacity, tokens + elapsed * rate)

if tokens >= 1 then
    -- Consume one token
    tokens = tokens - 1
    redis.call('HMSET', key, 'tokens', tostring(tokens), 'ts', tostring(now))
    redis.call('EXPIRE', key, 3600)
    return '1'
else
    -- Return seconds until one token is available
    local wait = (1 - tokens) / rate
    return '0:' .. tostring(wait)
end
"""

_KEY_PREFIX = "autobot:llm:rl"


def _provider_limits(provider: str) -> Tuple[float, float]:
    """Return (capacity, refill_rate_tokens_per_second) for a provider."""
    pname = provider.upper()
    rpm_key = f"AUTOBOT_LLM_RL_{pname}_RPM"
    burst_key = f"AUTOBOT_LLM_RL_{pname}_BURST"
    defaults = _PROVIDER_DEFAULTS.get(provider.lower(), _PROVIDER_DEFAULTS["default"])
    rpm = env_int(rpm_key, defaults[0])
    burst = env_int(burst_key, defaults[1])
    return float(burst), float(rpm) / 60.0  # capacity, tokens/sec


class LLMCrossWorkerRateLimiter:
    """
    Redis-backed proactive token-bucket rate limiter for LLM providers.

    Shared across all uvicorn workers via Redis.  Falls back gracefully to
    allow-all when Redis is unavailable, ensuring a Redis outage never
    hard-blocks LLM calls.
    """

    def __init__(self) -> None:
        self._redis_available = True
        self._script_sha: Optional[str] = None  # cached EVALSHA
        self._local_fallback: asyncio.Semaphore | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def acquire(
        self,
        provider: str,
        timeout: float = 30.0,
    ) -> AsyncIterator[None]:
        """
        Async context manager that blocks until a token is available.

        Raises ``asyncio.TimeoutError`` if *timeout* seconds elapse without
        a token becoming available.
        """
        deadline = time.monotonic() + timeout
        while True:
            allowed, retry_after = await self.try_acquire(provider)
            if allowed:
                yield
                return
            if time.monotonic() + retry_after > deadline:
                raise asyncio.TimeoutError(
                    f"LLM rate limiter: timed out waiting for {provider!r} token (timeout={timeout}s)"
                )
            await asyncio.sleep(min(retry_after, 1.0))

    async def try_acquire(self, provider: str) -> Tuple[bool, float]:
        """
        Non-blocking token acquire attempt.

        Returns:
            (True, 0.0)              if a token was granted.
            (False, retry_after_sec) if the bucket is empty.
        """
        try:
            return await self._redis_try_acquire(provider)
        except Exception:
            logger.debug(
                "LLM rate limiter: Redis unavailable — allowing request (provider=%s)", provider, exc_info=True
            )
            self._redis_available = False
            return True, 0.0

    async def peek_tokens(self, provider: str) -> float:
        """
        Return the approximate number of tokens currently available for *provider*.
        Useful for monitoring / metrics endpoints.
        """
        try:
            redis = await self._get_redis()
            data = await redis.hmget(f"{_KEY_PREFIX}:{provider}", "tokens", "ts")
            capacity, rate = _provider_limits(provider)
            tokens_raw, ts_raw = data
            tokens = float(tokens_raw) if tokens_raw else capacity
            ts = float(ts_raw) if ts_raw else time.time()
            elapsed = max(0.0, time.time() - ts)
            return min(capacity, tokens + elapsed * rate)
        except Exception:
            return -1.0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _get_redis(self):
        from autobot_shared.redis_client import get_async_redis_client  # noqa: PLC0415

        return await get_async_redis_client()

    async def _load_script(self, redis) -> str:
        if self._script_sha is None:
            self._script_sha = await redis.script_load(_LUA_ACQUIRE)
        return self._script_sha

    async def _redis_try_acquire(self, provider: str) -> Tuple[bool, float]:
        redis = await self._get_redis()
        sha = await self._load_script(redis)
        capacity, rate = _provider_limits(provider)
        key = f"{_KEY_PREFIX}:{provider}"
        now = time.time()

        result: bytes = await redis.evalsha(
            sha,
            1,  # numkeys
            key,
            str(capacity),
            str(rate),
            str(now),
        )
        result_str = result.decode() if isinstance(result, bytes) else str(result)

        if result_str == "1":
            return True, 0.0
        parts = result_str.split(":", 1)
        retry_after = float(parts[1]) if len(parts) == 2 else 1.0
        return False, retry_after


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_limiter: Optional[LLMCrossWorkerRateLimiter] = None


def get_llm_rate_limiter() -> LLMCrossWorkerRateLimiter:
    """Return the shared LLM rate limiter singleton."""
    global _limiter
    if _limiter is None:
        _limiter = LLMCrossWorkerRateLimiter()
    return _limiter
