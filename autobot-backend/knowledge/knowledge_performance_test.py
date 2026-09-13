#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Manager Performance Testing
GitHub Issue #163 - Task 4.3: Performance Testing with Large Datasets

Four load scenarios against the *deployed* knowledge base API:

1. Category filtering under concurrency
2. Bulk vectorization-status loading across batch sizes
3. Rapid sequential filtering (a user clicking through categories)
4. Concurrent mixed operations (filter + stats + entries)

Before #14979 this was a driver script: ``KnowledgePerformanceTest.__init__``
made the class uncollectable by pytest, each ``test_*`` method returned a
``PerformanceMetrics`` object into ``run_comprehensive_test_suite()``, and the
verdict lived in a printed summary and a JSON report nothing read. Four
scenarios that collected zero items now collect four, and each one asserts.

**What the assertions check.** A wall-clock budget on a shared runner is flaky,
so each scenario asserts a *correctness* property first and only then a
deliberately generous latency ceiling set an order of magnitude above the #163
target (2s against a 200ms filter target, 5s against a 500ms status-load
target). Those ceilings catch a knowledge base that has fallen over or hung, not
one that is merely busy. The three concurrent scenarios apply their ceiling to
*amortised per-request wall time* rather than p95, because firing N requests at
once makes each one queue behind the other N-1 — see :func:`_amortised_ms`. The
sequential scenario, which is the one #163's 200ms actually describes, keeps
p95. The #163 targets are kept as constants and logged, so a
run still reports how far from them the deployment sits.

The correctness property is the one ``comprehensive_system_validation_test.py``
settled on for live-stack suites: *every route is served (not 404) and the
backend did not fault (not 5xx)*. It is stated that way because a deployment may
require authentication, and an unauthenticated client then gets 401 from every
knowledge base route — that is the route answering, not the knowledge base being
slow. Payload-shape assertions are therefore applied whenever a request did come
back 200. Giving this suite credentials would let it assert on real result sets;
until then it measures the full request path and catches unmounted routers,
server faults and hangs.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import aiohttp
import pytest

from autobot_shared.live_service_probe import require_live_endpoint
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

# #14979: real load against a deployed backend — excluded from the unit gate,
# selected by marker-tests.yml.
pytestmark = pytest.mark.performance

logger = get_logger(__name__)

# SSOT (#1618): the endpoint comes from config, never from a literal.
BACKEND_URL = config.backend_url
KB_PREFIX = "/api/knowledge_base"

# Performance targets from Issue #163 — reported, not asserted (see docstring).
CATEGORY_FILTER_TARGET_MS = 200.0
STATUS_LOAD_TARGET_MS = 500.0
RAPID_FILTER_TARGET_MS = 200.0

# Order-of-magnitude ceilings, generous by design so a shared runner does not
# turn an ordinary slow moment into a red build.
CATEGORY_FILTER_CEILING_MS = 2000.0
STATUS_LOAD_CEILING_MS = 5000.0
RAPID_FILTER_CEILING_MS = 2000.0
MIXED_OPERATION_CEILING_MS = 5000.0

# Scenario sizes.
FILTER_ITERATIONS = 50
RAPID_FILTER_OPERATIONS = 100
CONCURRENT_MIXED_OPERATIONS = 20
STATUS_LOAD_FACT_COUNT = 1000
STATUS_LOAD_BATCH_SIZES: tuple[int, ...] = (100, 250, 500, 1000)

#: The batch status route. The driver script posted to
#: ``/api/knowledge_base/bulk/vectorization_status``, which no router has ever
#: served -- the same defect class #15133 removed from the multi-agent probe
#: list. ``api/knowledge_vectorization.py`` mounts it without the ``bulk``
#: segment, and that is what the frontend composable calls too.
STATUS_LOAD_PATH = f"{KB_PREFIX}/vectorization_status"

REQUEST_TIMEOUT_SECONDS = 10.0
USER_THINK_TIME_SECONDS = 0.1


@pytest.fixture(autouse=True)
def _require_live_backend() -> None:
    """Skip when the AutoBot backend API is absent (#14930).

    Every scenario drives the knowledge base over HTTP. On a runner without a
    backend the results were refused connections reported as performance
    failures — a measurement of the runner's inventory, not of the knowledge
    base.
    """
    require_live_endpoint(BACKEND_URL, what="the AutoBot backend API")


@pytest.fixture
async def kb_session() -> Any:
    """An ``aiohttp`` session bound to the backend, closed after each test."""
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        yield session


def _p95_ms(latencies: list[float]) -> float:
    """The 95th-percentile sample, or 0.0 for an empty series."""
    if not latencies:
        return 0.0
    ordered = sorted(latencies)
    return ordered[min(int(len(ordered) * 0.95), len(ordered) - 1)]


async def _amortised_ms(operations: list[Any]) -> tuple[list[Any], float]:
    """Run *operations* together; return their results and the per-request wall time.

    Concurrent scenarios are bounded on this rather than on p95. Firing N
    requests at once makes every one of them queue behind the other N-1, so the
    per-request latency it produces is a function of N, not the quantity the #163
    targets describe. Throughput is: it stays flat while the service keeps up and
    collapses the moment it stops, which is the regression worth catching.
    """
    started = time.perf_counter()
    results = await asyncio.gather(*operations)
    return list(results), (time.perf_counter() - started) * 1000 / max(len(results), 1)


async def _timed_get(session: aiohttp.ClientSession, path: str, params: dict | None = None) -> tuple[int, float]:
    """GET *path* on the backend and return ``(status, elapsed_ms)``."""
    start = time.perf_counter()
    async with session.get(f"{BACKEND_URL}{path}", params=params) as response:
        await response.json(content_type=None)
        return response.status, (time.perf_counter() - start) * 1000


def _assert_served_and_sound(response_status: int, path: str) -> None:
    """Assert one route is mounted and did not fault."""
    assert response_status != 404, f"{path} is not served — the knowledge base router is not mounted"
    assert response_status < 500, f"{path} faulted with HTTP {response_status}"


async def _fetch_categories(session: aiohttp.ClientSession) -> list[str]:
    """Return the knowledge base's category list, or ``[]`` when it is not readable.

    An empty list is returned only when the stats route answered without giving
    us the data (an auth challenge, typically); it never hides a 404 or a fault,
    both of which fail here.
    """
    async with session.get(f"{BACKEND_URL}{KB_PREFIX}/stats") as response:
        _assert_served_and_sound(response.status, f"{KB_PREFIX}/stats")
        if response.status != 200:
            return []
        stats = await response.json(content_type=None)

    categories = stats.get("categories", []) if isinstance(stats, dict) else []
    assert categories, (
        "the knowledge base answered 200 but reports no categories, so every filtering "
        "scenario below would measure an empty result set. Populate it before running this "
        f"suite (see POST {KB_PREFIX}/populate_system_commands)."
    )
    return list(categories)


async def _fetch_fact_ids(session: aiohttp.ClientSession, limit: int) -> list[str]:
    """Return up to *limit* fact identifiers, falling back to probe ids.

    The fallback keeps the bulk-status request shapes real (the batch sizes are
    what that scenario measures) when the entries route will not hand out ids.
    """
    async with session.get(f"{BACKEND_URL}{KB_PREFIX}/entries", params={"limit": limit}) as response:
        _assert_served_and_sound(response.status, f"{KB_PREFIX}/entries")
        readable = response.status == 200
        entries = (await response.json(content_type=None) or {}).get("entries", []) if readable else []

    fact_ids = []
    for entry in entries[:limit]:
        raw = entry.get("id") or entry.get("key") or entry.get("fact_id")
        if raw:
            fact_ids.append(str(raw)[5:] if str(raw).startswith("fact:") else str(raw))

    if readable:
        assert fact_ids, (
            f"{KB_PREFIX}/entries returned {len(entries)} entries but none carried an id, key "
            f"or fact_id — the bulk status scenario has nothing to look up"
        )
        return fact_ids
    return [f"perf-probe-{index}" for index in range(limit)]


def _assert_all_served(outcomes: list[tuple[int, float]], scenario: str) -> list[float]:
    """Assert every request was served and none faulted; return the latency series."""
    unserved = [status for status, _latency in outcomes if status == 404]
    assert not unserved, f"{len(unserved)} of {len(outcomes)} {scenario} requests hit an unmounted route (404)"

    faulted = [status for status, _latency in outcomes if status >= 500]
    assert not faulted, (
        f"{len(faulted)} of {len(outcomes)} {scenario} requests faulted " f"(statuses seen: {sorted(set(faulted))})"
    )
    return [latency for _status, latency in outcomes]


class TestKnowledgePerformance:
    """Filtering, bulk status loading and mixed-operation load on the knowledge base."""

    async def test_category_filter_performance(self, kb_session: aiohttp.ClientSession) -> None:
        """Concurrent category filters are all served and stay under the filter ceiling."""
        categories = await _fetch_categories(kb_session)

        async def filter_once(index: int) -> tuple[int, float]:
            params: dict[str, Any] = {"limit": 100}
            if categories and index % 5:  # every fifth request asks for all categories
                params["category"] = categories[index % len(categories)]
            return await _timed_get(kb_session, f"{KB_PREFIX}/facts/by_category", params)

        outcomes, amortised_ms = await _amortised_ms([filter_once(index) for index in range(FILTER_ITERATIONS)])
        latencies = _assert_all_served(outcomes, "category filter")
        logger.info(
            "category filter scenario complete",
            iterations=FILTER_ITERATIONS,
            amortised_ms=amortised_ms,
            p95_ms=_p95_ms(latencies),
            target_ms=CATEGORY_FILTER_TARGET_MS,
        )

        assert amortised_ms < CATEGORY_FILTER_CEILING_MS, (
            f"category filtering managed {amortised_ms:.0f}ms per request across "
            f"{FILTER_ITERATIONS} concurrent filters (#163 target "
            f"{CATEGORY_FILTER_TARGET_MS:.0f}ms), at or beyond the "
            f"{CATEGORY_FILTER_CEILING_MS:.0f}ms ceiling"
        )

    async def test_vectorization_status_load(self, kb_session: aiohttp.ClientSession) -> None:
        """Bulk vectorization-status lookups are served at every batch size."""
        fact_ids = await _fetch_fact_ids(kb_session, STATUS_LOAD_FACT_COUNT)

        async def status_for_batch(batch_size: int) -> tuple[int, float]:
            payload = {"fact_ids": fact_ids[: min(batch_size, len(fact_ids))], "include_dimensions": True}
            start = time.perf_counter()
            async with kb_session.post(f"{BACKEND_URL}{STATUS_LOAD_PATH}", json=payload) as response:
                await response.json(content_type=None)
                return response.status, (time.perf_counter() - start) * 1000

        outcomes, amortised_ms = await _amortised_ms([status_for_batch(size) for size in STATUS_LOAD_BATCH_SIZES])
        latencies = _assert_all_served(outcomes, "bulk vectorization status")
        logger.info(
            "vectorization status scenario complete",
            fact_ids=len(fact_ids),
            batch_sizes=list(STATUS_LOAD_BATCH_SIZES),
            amortised_ms=amortised_ms,
            p95_ms=_p95_ms(latencies),
            target_ms=STATUS_LOAD_TARGET_MS,
        )

        assert amortised_ms < STATUS_LOAD_CEILING_MS, (
            f"bulk vectorization status managed {amortised_ms:.0f}ms per batch over "
            f"{len(fact_ids)} facts in batches {list(STATUS_LOAD_BATCH_SIZES)} (#163 target "
            f"{STATUS_LOAD_TARGET_MS:.0f}ms), at or beyond the {STATUS_LOAD_CEILING_MS:.0f}ms ceiling"
        )

    async def test_rapid_sequential_filtering(self, kb_session: aiohttp.ClientSession) -> None:
        """A user clicking rapidly through categories is served every time."""
        categories = await _fetch_categories(kb_session)

        outcomes: list[tuple[int, float]] = []
        for index in range(RAPID_FILTER_OPERATIONS):
            params: dict[str, Any] = {"limit": 50}
            if categories:
                params["category"] = categories[index % len(categories)]
            outcomes.append(await _timed_get(kb_session, f"{KB_PREFIX}/facts/by_category", params))
            await asyncio.sleep(USER_THINK_TIME_SECONDS)  # user think time between clicks

        latencies = _assert_all_served(outcomes, "rapid sequential filter")
        logger.info(
            "rapid filtering scenario complete",
            operations=RAPID_FILTER_OPERATIONS,
            p95_ms=_p95_ms(latencies),
            target_ms=RAPID_FILTER_TARGET_MS,
        )

        assert _p95_ms(latencies) < RAPID_FILTER_CEILING_MS, (
            f"rapid sequential filter p95 was {_p95_ms(latencies):.0f}ms across "
            f"{RAPID_FILTER_OPERATIONS} clicks (#163 target {RAPID_FILTER_TARGET_MS:.0f}ms), at "
            f"or beyond the {RAPID_FILTER_CEILING_MS:.0f}ms ceiling — the UI would freeze"
        )

    async def test_concurrent_mixed_operations(self, kb_session: aiohttp.ClientSession) -> None:
        """Filter, stats and entries calls issued together are all served."""
        categories = await _fetch_categories(kb_session)

        async def mixed_operation(op_id: int) -> tuple[int, float]:
            if op_id % 3 == 0:
                params: dict[str, Any] = {"limit": 50}
                if categories:
                    params["category"] = categories[op_id % len(categories)]
                return await _timed_get(kb_session, f"{KB_PREFIX}/facts/by_category", params)
            if op_id % 3 == 1:
                return await _timed_get(kb_session, f"{KB_PREFIX}/stats")
            return await _timed_get(kb_session, f"{KB_PREFIX}/entries", {"limit": 20})

        outcomes, amortised_ms = await _amortised_ms(
            [mixed_operation(op_id) for op_id in range(CONCURRENT_MIXED_OPERATIONS)]
        )
        latencies = _assert_all_served(outcomes, "concurrent mixed knowledge base")
        logger.info(
            "concurrent mixed scenario complete",
            operations=CONCURRENT_MIXED_OPERATIONS,
            amortised_ms=amortised_ms,
            p95_ms=_p95_ms(latencies),
        )

        assert amortised_ms < MIXED_OPERATION_CEILING_MS, (
            f"concurrent mixed operations managed {amortised_ms:.0f}ms per request across "
            f"{CONCURRENT_MIXED_OPERATIONS} interleaved filter/stats/entries calls, at or beyond "
            f"the {MIXED_OPERATION_CEILING_MS:.0f}ms ceiling"
        )
