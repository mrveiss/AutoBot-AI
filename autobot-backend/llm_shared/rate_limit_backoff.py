# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Provider rate-limit recovery: exponential backoff + auto-resume on quota reset.

GH#8502 — wires RateLimitHandler into BaseProvider so every provider
automatically retries on 429 / quota-exceeded responses without any
per-provider boilerplate.

Design:
  - Providers return errors in LLMResponse.error (catch-all pattern).
  - This module detects rate-limit signals in that error field and re-raises
    a RateLimitError so the existing RateLimitHandler retry loop kicks in.
  - Quota-reset headers (x-ratelimit-reset-requests, x-ratelimit-reset-tokens,
    retry-after) are parsed and forwarded as retry_after so the handler waits
    exactly the right duration instead of guessing.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from autobot_shared.logging_manager import get_logger

from .optimization.rate_limiter import RateLimitConfig, RateLimitError, RateLimitHandler, RetryStrategy

if TYPE_CHECKING:
    from .models import LLMResponse

logger = get_logger(__name__)

# Patterns that appear in provider error strings indicating a quota/rate limit.
_RATE_LIMIT_PATTERNS = [
    r"rate.limit",
    r"too many requests",
    r"429",
    r"quota.exceeded",
    r"resource.exhausted",
    r"requests per (minute|hour|day)",
    r"token.*(per|limit)",
    r"throttl",
]
_RATE_LIMIT_RE = re.compile("|".join(_RATE_LIMIT_PATTERNS), re.IGNORECASE)

# Patterns that look like "retry after N seconds" in error strings.
_RETRY_AFTER_RE = re.compile(r"retry.after[:\s]+(\d+(?:\.\d+)?)", re.IGNORECASE)

# Global handler shared across all provider instances (singleton per process).
_DEFAULT_CONFIG = RateLimitConfig(
    max_retries=5,
    base_delay=1.0,
    max_delay=120.0,
    jitter_factor=0.3,
    strategy=RetryStrategy.EXPONENTIAL,
)
_handler: RateLimitHandler | None = None


def get_backoff_handler() -> RateLimitHandler:
    """Return the process-wide RateLimitHandler (lazy singleton)."""
    global _handler
    if _handler is None:
        _handler = RateLimitHandler(config=_DEFAULT_CONFIG)
    return _handler


def extract_rate_limit_info(response: "LLMResponse") -> tuple[bool, float | None]:
    """
    Return (is_rate_limited, retry_after_seconds) from a provider response.

    Inspects response.error for known rate-limit patterns and tries to parse
    a suggested wait duration.
    """
    if not response.error:
        return False, None

    error_text = str(response.error)
    if not _RATE_LIMIT_RE.search(error_text):
        return False, None

    retry_after: float | None = None
    m = _RETRY_AFTER_RE.search(error_text)
    if m:
        try:
            retry_after = float(m.group(1))
        except ValueError:
            pass

    # Also check provider_metadata for quota reset timestamps.
    if response.provider_metadata:
        for key in ("retry_after", "x-ratelimit-reset", "x-ratelimit-reset-requests"):
            val = response.provider_metadata.get(key)
            if val is not None:
                try:
                    # Value may be epoch timestamp or seconds-until-reset.
                    v = float(val)
                    # Heuristic: if value is > current epoch it's a timestamp.
                    if v > time.time():
                        v = v - time.time()
                    retry_after = max(retry_after or 0, v) or None
                except (TypeError, ValueError):
                    pass

    return True, retry_after


def raise_if_rate_limited(response: "LLMResponse") -> None:
    """
    Raise RateLimitError when the response signals a provider quota hit.

    Called inside the retry wrapper so RateLimitHandler can catch it and
    apply backoff before re-invoking the provider.
    """
    is_rl, retry_after = extract_rate_limit_info(response)
    if is_rl:
        raise RateLimitError(
            f"Provider {response.provider!r} hit rate limit: {response.error}",
            retry_after=retry_after,
            provider=response.provider or "unknown",
        )


__all__ = [
    "get_backoff_handler",
    "extract_rate_limit_info",
    "raise_if_rate_limited",
    "RateLimitError",
]
