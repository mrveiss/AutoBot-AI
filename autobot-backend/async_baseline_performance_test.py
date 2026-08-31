#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
AutoBot Async Operations Baseline Performance Testing
Week 2-3: Task 2.5 - Performance Load Testing

Four load scenarios against the *deployed* stack:

1. Concurrent chat requests through the backend API
2. Concurrent Redis set/get round-trips
3. Mixed file I/O and Redis operations
4. Cross-VM concurrent requests (frontend, NPU worker, AI stack)

Before #14979 this was a driver script: ``AsyncBaselineTest.__init__`` made the
class uncollectable, each ``test_*`` method returned a ``PerformanceMetrics``
object into ``run_comprehensive_baseline()``, and the only verdict was a printed
summary plus a JSON report nothing read. Four scenarios that collected zero
items now collect four, and each one asserts.

**What the assertions check.** A wall-clock budget on a shared runner is flaky,
so each scenario asserts a *correctness* property first — every concurrent
request completed, every Redis round-trip returned the value written, every file
round-trip read back what it wrote — and only then a deliberately generous
order-of-magnitude throughput ceiling (30s per chat turn, 1s per Redis
round-trip, measured as amortised wall time per request rather than p95 — see
:func:`_run_concurrently`). Those ceilings sit one to three orders of magnitude
above healthy values; they catch a stack that has fallen over, not one that is
merely busy.
Every ceiling and scenario size is a module constant so a fleet
run can widen them without editing a call site.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

import aiofiles
import aiohttp
import pytest

from autobot_shared.live_service_probe import require_live_endpoint, require_real_redis_client
from autobot_shared.logging_manager import get_logger

# Import canonical Redis client pattern
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.ssot_config import config
from autobot_shared.ssot_constants import TTL_1_MINUTE

# #14979: real load against a deployed stack — excluded from the unit gate,
# selected by marker-tests.yml.
pytestmark = pytest.mark.performance

logger = get_logger(__name__)

# SSOT (#1618): every endpoint comes from config, never from a literal.
BACKEND_URL = config.backend_url
REDIS_URL = config.redis_url
CROSS_VM_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("frontend", f"{config.frontend_url}/"),
    ("npu-worker", f"{config.npu_worker_url}/health"),
    ("ai-stack", f"{config.aistack_url}/health"),
)

# Scenario sizes — module constants; scaling them for a fleet run is a code
# change, matching the module-constant rule used for every other tunable here.
CONCURRENT_CHAT_USERS = 50
REDIS_OPERATION_COUNT = 100
MIXED_IO_OPERATION_COUNT = 50
CROSS_VM_REQUEST_COUNT = 20

# Order-of-magnitude ceilings, not budgets. Healthy values are ~1ms (Redis),
# ~10ms (cross-VM) and <2s (chat); these sit far above that so a shared runner's
# jitter never decides the verdict.
CHAT_CEILING_MS = 30000.0
REDIS_CEILING_MS = 1000.0
MIXED_IO_CEILING_MS = 2000.0
CROSS_VM_CEILING_MS = 1000.0

CHAT_REQUEST_TIMEOUT_SECONDS = 60.0
CROSS_VM_REQUEST_TIMEOUT_SECONDS = 10.0
CHAT_TEST_MESSAGE = "What is AutoBot's architecture?"
REDIS_TEST_DATABASE = "metrics"


@pytest.fixture(autouse=True)
def _require_live_stack() -> None:
    """Skip when the AutoBot backend API is absent (#14930).

    Every scenario loads the deployed stack, and the backend is the piece all of
    them are measured against. On a runner without one the results were refused
    connections reported as performance failures. The two Redis scenarios add
    their own preconditions via :func:`_require_live_redis`, so a missing Redis
    skips those two by name instead of taking the HTTP scenarios with it.
    """
    require_live_endpoint(BACKEND_URL, what="the AutoBot backend API")


def _require_live_redis() -> None:
    """Skip the calling scenario when a real Redis connection is unavailable.

    Two conditions, both structural, both reported by name: nothing listening on
    the configured Redis endpoint, and ``autobot-backend/conftest.py`` owning
    ``autobot_shared.redis_client`` with a socket-free stand-in whose
    ``get_async_redis_client()`` returns ``None`` (#14932).
    """
    require_live_endpoint(REDIS_URL, what="the AutoBot Redis instance")
    require_real_redis_client("the async baseline performance suite")


def _p95_ms(latencies: list[float]) -> float:
    """The 95th-percentile sample, or 0.0 for an empty series."""
    if not latencies:
        return 0.0
    ordered = sorted(latencies)
    return ordered[min(int(len(ordered) * 0.95), len(ordered) - 1)]


async def _run_concurrently(factory: Callable[[int], Awaitable[Any]], count: int) -> tuple[list[Any], float]:
    """Launch *count* operations at once; return their results and per-request wall time.

    Exceptions propagate rather than being folded into a failure tally: a load
    scenario that swallowed them would report a broken stack as a slow one.

    Every scenario here is bounded on the amortised wall time this returns rather
    than on p95. Firing N requests at once makes each one queue behind the other
    N-1, so the per-request latency that produces is a function of N, not of the
    stack. Throughput is the quantity that stays flat while the stack keeps up
    and collapses when the event loop blocks — the regression these scenarios
    exist to catch.
    """
    started = time.perf_counter()
    results = await asyncio.gather(*(factory(index) for index in range(count)))
    return list(results), (time.perf_counter() - started) * 1000 / max(count, 1)


class TestAsyncBaseline:
    """Baseline load behaviour of chat, Redis, mixed I/O and cross-VM paths."""

    async def test_concurrent_chat_requests(self) -> None:
        """Every one of N concurrent chat turns completes without a server error."""
        url = f"{BACKEND_URL}/api/chat"
        timeout = aiohttp.ClientTimeout(total=CHAT_REQUEST_TIMEOUT_SECONDS)

        async with aiohttp.ClientSession(timeout=timeout) as session:

            async def chat(user_id: int) -> tuple[int, float]:
                payload = {"message": CHAT_TEST_MESSAGE, "session_id": f"baseline_test_session_{user_id}"}
                start = time.perf_counter()
                async with session.post(url, json=payload) as response:
                    await response.text()
                    return response.status, (time.perf_counter() - start) * 1000

            outcomes, amortised_ms = await _run_concurrently(chat, CONCURRENT_CHAT_USERS)

        statuses = [status for status, _latency in outcomes]
        latencies = [latency for _status, latency in outcomes]
        logger.info(
            "concurrent chat scenario complete",
            users=CONCURRENT_CHAT_USERS,
            amortised_ms=amortised_ms,
            p95_ms=_p95_ms(latencies),
        )

        server_errors = [status for status in statuses if status >= 500]
        assert not server_errors, (
            f"{len(server_errors)} of {CONCURRENT_CHAT_USERS} concurrent chat requests hit a "
            f"server error (statuses: {sorted(set(server_errors))}) — the chat path fails under "
            f"concurrency"
        )
        assert amortised_ms < CHAT_CEILING_MS, (
            f"the chat path managed {amortised_ms:.0f}ms per request under "
            f"{CONCURRENT_CHAT_USERS} concurrent users (p95 {_p95_ms(latencies):.0f}ms), at or "
            f"beyond the {CHAT_CEILING_MS:.0f}ms ceiling — the event loop is blocking, not "
            f"merely busy"
        )

    async def test_concurrent_redis_operations(self) -> None:
        """Every concurrent Redis round-trip reads back exactly what it wrote."""
        _require_live_redis()
        redis_client = await get_async_redis_client(database=REDIS_TEST_DATABASE)

        async def round_trip(op_id: int) -> tuple[bool, float]:
            key, value = f"baseline_test_key_{op_id}", f"baseline_test_value_{op_id}"
            start = time.perf_counter()
            await redis_client.set(key, value, ex=TTL_1_MINUTE)
            retrieved = await redis_client.get(key)
            latency = (time.perf_counter() - start) * 1000
            decoded = retrieved.decode("utf-8") if isinstance(retrieved, bytes) else retrieved
            return decoded == value, latency

        try:
            outcomes, amortised_ms = await _run_concurrently(round_trip, REDIS_OPERATION_COUNT)
        finally:
            await redis_client.close()

        mismatches = [index for index, (matched, _latency) in enumerate(outcomes) if not matched]
        latencies = [latency for _matched, latency in outcomes]
        logger.info(
            "concurrent redis scenario complete",
            operations=REDIS_OPERATION_COUNT,
            amortised_ms=amortised_ms,
            p95_ms=_p95_ms(latencies),
        )

        assert not mismatches, (
            f"{len(mismatches)} of {REDIS_OPERATION_COUNT} concurrent Redis round-trips did not "
            f"read back the value written (first failing op ids: {mismatches[:5]}) — concurrent "
            f"access is corrupting or losing writes"
        )
        assert amortised_ms < REDIS_CEILING_MS, (
            f"Redis set+get managed {amortised_ms:.0f}ms per round-trip across "
            f"{REDIS_OPERATION_COUNT} concurrent operations (p95 {_p95_ms(latencies):.0f}ms), at "
            f"or beyond the {REDIS_CEILING_MS:.0f}ms ceiling"
        )

    async def test_mixed_io_operations(self, tmp_path: Path) -> None:
        """Concurrent file writes and Redis caches both round-trip intact."""
        _require_live_redis()
        redis_client = await get_async_redis_client(database=REDIS_TEST_DATABASE)

        async def mixed_io(op_id: int) -> tuple[bool, float]:
            payload = json.dumps({"op_id": op_id, "timestamp": datetime.now().isoformat()})
            file_path = tmp_path / f"test_file_{op_id}.json"
            cache_key = f"baseline_cache_{op_id}"

            start = time.perf_counter()
            async with aiofiles.open(file_path, "w", encoding="utf-8") as handle:
                await handle.write(payload)
            await redis_client.set(cache_key, payload, ex=TTL_1_MINUTE)
            async with aiofiles.open(file_path, "r", encoding="utf-8") as handle:
                file_content = await handle.read()
            cached = await redis_client.get(cache_key)
            latency = (time.perf_counter() - start) * 1000

            decoded = cached.decode("utf-8") if isinstance(cached, bytes) else cached
            return file_content == payload and decoded == payload, latency

        try:
            outcomes, amortised_ms = await _run_concurrently(mixed_io, MIXED_IO_OPERATION_COUNT)
        finally:
            await redis_client.close()

        mismatches = [index for index, (matched, _latency) in enumerate(outcomes) if not matched]
        latencies = [latency for _matched, latency in outcomes]
        logger.info(
            "mixed I/O scenario complete",
            operations=MIXED_IO_OPERATION_COUNT,
            amortised_ms=amortised_ms,
            p95_ms=_p95_ms(latencies),
        )

        assert not mismatches, (
            f"{len(mismatches)} of {MIXED_IO_OPERATION_COUNT} mixed file+Redis round-trips did "
            f"not read back what they wrote (first failing op ids: {mismatches[:5]}) — "
            f"concurrent file and cache writes are interfering"
        )
        assert amortised_ms < MIXED_IO_CEILING_MS, (
            f"mixed file+Redis managed {amortised_ms:.0f}ms per round-trip across "
            f"{MIXED_IO_OPERATION_COUNT} concurrent operations (p95 "
            f"{_p95_ms(latencies):.0f}ms), at or beyond the {MIXED_IO_CEILING_MS:.0f}ms "
            f"ceiling — file I/O is blocking the event loop"
        )

    async def test_cross_vm_latency(self) -> None:
        """Every peer VM answers every concurrent request, Redis included."""
        for vm_name, endpoint in CROSS_VM_ENDPOINTS:
            require_live_endpoint(endpoint, what=f"the AutoBot {vm_name} service")

        timeout = aiohttp.ClientTimeout(total=CROSS_VM_REQUEST_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:

            async def probe(index: int) -> tuple[str, int, float]:
                vm_name, endpoint = CROSS_VM_ENDPOINTS[index % len(CROSS_VM_ENDPOINTS)]
                start = time.perf_counter()
                async with session.get(endpoint) as response:
                    await response.text()
                    return vm_name, response.status, (time.perf_counter() - start) * 1000

            http_outcomes, amortised_ms = await _run_concurrently(
                probe, CROSS_VM_REQUEST_COUNT * len(CROSS_VM_ENDPOINTS)
            )

        latencies = [latency for _vm, _status, latency in http_outcomes]
        logger.info(
            "cross-VM scenario complete",
            requests=len(latencies),
            amortised_ms=amortised_ms,
            p95_ms=_p95_ms(latencies),
        )

        failures = [(vm, status) for vm, status, _latency in http_outcomes if status >= 400]
        assert not failures, "cross-VM requests failed: " + ", ".join(
            f"{vm} -> HTTP {status}" for vm, status in sorted(set(failures))
        )
        assert amortised_ms < CROSS_VM_CEILING_MS, (
            f"cross-VM traffic managed {amortised_ms:.0f}ms per request across {len(latencies)} "
            f"requests to {[name for name, _ in CROSS_VM_ENDPOINTS]} (p95 "
            f"{_p95_ms(latencies):.0f}ms), at or beyond the {CROSS_VM_CEILING_MS:.0f}ms ceiling"
        )
