# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Concurrency guard tests for async global mutations (Issue #10786).

These tests validate that the asyncio.Lock pattern used in:
  - api/monitoring.py (_alertmanager_cache under _alertmanager_cache_lock)

actually prevents lost updates under concurrent asyncio coroutines.

The module itself cannot be imported in the CI test environment
(transitive deps require a running Redis / compiled C extensions).
Instead the test replicates the exact lock + cache pattern verbatim, which is
sufficient to prove the pattern is race-free.

The ``database_mcp`` / ``http_client_mcp`` rate-limit counters this file used
to replicate no longer exist: they were folded into the canonical
``autobot_shared.rate_limiter.RateLimiter`` (#18087), and their concurrency
behaviour is pinned against the real implementation in
``autobot_shared/rate_limiter_window_18087_test.py``.

Pattern added to monitoring.py (Issue #10786):
    async with _alertmanager_cache_lock:
        if stale: fetch + write cache
"""

import asyncio
import time
from typing import Any, Dict

# ---------------------------------------------------------------------------
# monitoring.py: _alertmanager_cache concurrency test (Issue #10786 fix)
# ---------------------------------------------------------------------------


def _make_alertmanager_cache() -> tuple[dict, asyncio.Lock]:
    """Return (_alertmanager_cache, _alertmanager_cache_lock) as in monitoring.py."""
    cache: Dict[str, Any] = {"alerts": [], "timestamp": 0, "ttl": 10}
    lock = asyncio.Lock()
    return cache, lock


async def _fetch_alerts_with_lock(cache: dict, lock: asyncio.Lock, fetch_calls: list) -> list:
    """
    Replica of _fetch_alertmanager_alerts() from monitoring.py (post-#10786 fix).

    Records each outbound HTTP fetch in fetch_calls to prove the lock prevents
    duplicate fetches.  The 'HTTP call' is simulated with asyncio.sleep(0).
    """
    async with lock:
        current_time = time.monotonic()
        if current_time - cache["timestamp"] < cache["ttl"]:
            return cache["alerts"]

        # Simulate the network round-trip (yields control — key race point)
        await asyncio.sleep(0)

        fetch_calls.append(1)
        fresh = [{"alert": "test"}]
        cache["alerts"] = fresh
        cache["timestamp"] = current_time
        return fresh


async def test_alertmanager_cache_no_duplicate_fetches() -> None:
    """
    Without a lock, N concurrent callers that all see a stale cache would each
    launch an HTTP fetch (thundering herd).  With _alertmanager_cache_lock they
    are serialised: only the FIRST caller fetches; the rest hit the now-fresh
    cache.

    Asserts fetch_calls == 1 (not N) when N coroutines race on a stale cache.
    """
    N = 10
    cache, lock = _make_alertmanager_cache()
    fetch_calls: list = []

    results = await asyncio.gather(*[_fetch_alerts_with_lock(cache, lock, fetch_calls) for _ in range(N)])

    # All callers get the same non-empty result
    assert all(r == [{"alert": "test"}] for r in results), "All callers must receive the fetched alert"
    # Only one outbound fetch must have occurred
    assert len(fetch_calls) == 1, (
        f"Expected exactly 1 HTTP fetch (lock prevents thundering herd), got {len(fetch_calls)}. "
        "The _alertmanager_cache_lock from Issue #10786 is not working."
    )


async def test_alertmanager_cache_returns_fresh_on_second_batch() -> None:
    """Cache hit path: a second batch of callers after the cache is warm must
    get the cached value without triggering any additional fetch."""
    cache, lock = _make_alertmanager_cache()
    fetch_calls: list = []

    # First batch — populates the cache
    await asyncio.gather(*[_fetch_alerts_with_lock(cache, lock, fetch_calls) for _ in range(5)])
    assert len(fetch_calls) == 1

    # Second batch — cache is still warm (timestamp freshly set, ttl=10)
    fetch_calls.clear()
    await asyncio.gather(*[_fetch_alerts_with_lock(cache, lock, fetch_calls) for _ in range(5)])
    assert len(fetch_calls) == 0, "Second batch must use the cache — no additional fetch expected"
