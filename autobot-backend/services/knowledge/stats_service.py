# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical knowledge-base stats fetcher (Issue #11554).

Both ``GET /api/knowledge_base/stats`` and
``GET /api/knowledge-maintenance/health/dashboard`` must return the same
core numbers (total_facts, total_vectors, db_size, categories).  Before
this module they each called ``kb.get_stats()`` independently — correct,
but one extra copy of that call pattern was a drift vector.

Now both endpoints call :func:`fetch_kb_core_stats` so there is exactly
ONE call-site pattern; any future change to what ``get_stats()`` returns
is automatically reflected in both responses.

The function is deliberately thin: it does not add logic, cache, or
transform — just delegates to the KB instance and returns the raw dict
so each endpoint can still shape its own response model independently.
"""

from __future__ import annotations

from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


async def fetch_kb_core_stats(kb: Any) -> Dict[str, Any]:
    """Return raw stats from ``kb.get_stats()`` — the canonical call site.

    Both the knowledge-stats endpoint and the health-dashboard endpoint
    delegate here so they share a single code path and cannot drift from
    each other (Issue #11554).

    Args:
        kb: A KnowledgeBase instance that exposes an async ``get_stats()``
            method (e.g. the composed ``KnowledgeBaseV2``).

    Returns:
        Raw stats dict exactly as returned by ``kb.get_stats()``.  Keys
        include at minimum: ``total_facts``, ``total_vectors``, ``db_size``,
        ``categories``, ``status``, ``last_updated``, ``initialized``.

    Raises:
        Nothing — ``get_stats()`` is already guarded internally; any error
        returns a sentinel dict with ``status="error"``.
    """
    stats = await kb.get_stats()
    logger.debug(
        "fetch_kb_core_stats: facts=%d vectors=%d status=%s",
        stats.get("total_facts", 0),
        stats.get("total_vectors", 0),
        stats.get("status", "unknown"),
    )
    return stats
