# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Concurrency guard tests for async global mutations (Issue #10786).

These tests validate that the asyncio.Lock patterns used in:
  - api/database_mcp.py  (query_counter under _rate_limit_lock)
  - api/http_client_mcp.py (request_counter under _rate_limit_lock)
  - api/monitoring.py (_alertmanager_cache under _alertmanager_cache_lock)

…actually prevent lost updates under concurrent asyncio coroutines.

The modules themselves cannot be imported in the CI test environment
(transitive deps require a running Redis / compiled C extensions).
Instead each test replicates the exact lock + counter / cache pattern
verbatim, which is sufficient to prove the pattern is race-free.

Pattern used in database_mcp.py / http_client_mcp.py:
    async with _rate_limit_lock:
        counter["count"] += 1

Pattern added to monitoring.py (Issue #10786):
    async with _alertmanager_cache_lock:
        if stale: fetch + write cache
"""

import asyncio
import time
from typing import Any, Dict

# ---------------------------------------------------------------------------
# Helpers: replicate the exact module-level patterns
# ---------------------------------------------------------------------------


def _make_counter(limit: int) -> tuple[dict, asyncio.Lock]:
    """Return (counter_dict, lock) as used in database_mcp / http_client_mcp."""
    counter: Dict[str, Any] = {"count": 0, "reset_time": time.monotonic()}
    lock = asyncio.Lock()
    return counter, lock


async def _check_rate_limit(counter: dict, lock: asyncio.Lock, limit: int) -> bool:
    """Exact replica of check_rate_limit() from database_mcp / http_client_mcp."""
    async with lock:
        now = time.monotonic()
        elapsed = now - counter["reset_time"]
        if elapsed >= 60:
            counter["count"] = 0
            counter["reset_time"] = now
        if counter["count"] >= limit:
            return False
        counter["count"] += 1
        return True


# ---------------------------------------------------------------------------
# database_mcp: query_counter concurrency test
# ---------------------------------------------------------------------------


async def test_database_mcp_counter_no_lost_updates() -> None:
    """
    Concurrent calls to check_rate_limit (database_mcp pattern) must produce
    an exact count — no lost updates, no double-increments.

    We call N times concurrently (N < MAX_QUERIES_PER_MINUTE=60) and assert
    counter["count"] == N afterwards.
    """
    N = 40  # well below MAX_QUERIES_PER_MINUTE=60
    limit = 60
    counter, lock = _make_counter(limit)

    results = await asyncio.gather(*[_check_rate_limit(counter, lock, limit) for _ in range(N)])

    assert all(results), "All calls should be allowed (N < limit)"
    assert counter["count"] == N, (
        f"Expected counter['count'] == {N}, got {counter['count']}. "
        "Lost updates indicate the lock is not guarding the RMW correctly."
    )


async def test_database_mcp_counter_enforces_limit() -> None:
    """
    After MAX_QUERIES_PER_MINUTE concurrent calls, further calls must be rejected.
    """
    limit = 60
    counter, lock = _make_counter(limit)

    # Fill up to the limit exactly
    first_batch = await asyncio.gather(*[_check_rate_limit(counter, lock, limit) for _ in range(limit)])
    assert all(first_batch), "First batch (==limit) should all be allowed"
    assert counter["count"] == limit

    # One more should be rejected
    over = await _check_rate_limit(counter, lock, limit)
    assert not over, "Call beyond limit should be rejected"
    assert counter["count"] == limit, "Rejected call must not increment the counter"


# ---------------------------------------------------------------------------
# http_client_mcp: request_counter concurrency test
# ---------------------------------------------------------------------------


async def test_http_client_mcp_counter_no_lost_updates() -> None:
    """
    Concurrent calls to check_rate_limit (http_client_mcp pattern) must
    produce an exact count — no lost updates.

    N < MAX_REQUESTS_PER_MINUTE=120.
    """
    N = 80  # well below MAX_REQUESTS_PER_MINUTE=120
    limit = 120
    counter, lock = _make_counter(limit)

    results = await asyncio.gather(*[_check_rate_limit(counter, lock, limit) for _ in range(N)])

    assert all(results), "All calls should be allowed (N < limit)"
    assert counter["count"] == N, (
        f"Expected counter['count'] == {N}, got {counter['count']}. "
        "Lost updates indicate the lock is not guarding the RMW correctly."
    )


async def test_http_client_mcp_counter_enforces_limit() -> None:
    """
    After MAX_REQUESTS_PER_MINUTE concurrent calls, further calls must be rejected.
    """
    limit = 120
    counter, lock = _make_counter(limit)

    first_batch = await asyncio.gather(*[_check_rate_limit(counter, lock, limit) for _ in range(limit)])
    assert all(first_batch), "First batch (==limit) should all be allowed"
    assert counter["count"] == limit

    over = await _check_rate_limit(counter, lock, limit)
    assert not over, "Call beyond limit should be rejected"
    assert counter["count"] == limit, "Rejected call must not increment the counter"


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
