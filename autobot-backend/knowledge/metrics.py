# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""KB-level Prometheus metrics with no-op fallback (#5319).

This module exposes Prometheus counters for knowledge-base observability.
It degrades to a no-op implementation when ``prometheus_client`` is not
installed (tests, minimal deployments), so importing is always safe.

Current metrics:

``autobot_kb_redis_unreachable_total{endpoint}``
    Incremented whenever a KB endpoint serves a degraded response because
    Redis is unreachable (i.e. ``kb_connected=false``).  Partners with a
    ``logger.warning`` at the call site so operators can page on either
    signal.

Follows the pattern established by ``knowledge/query_sanitizer.py`` (#5064).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class _NoopCounter:
    """Fallback counter used when prometheus_client is unavailable."""

    def labels(self, *_args, **_kwargs) -> "_NoopCounter":
        return self

    def inc(self, *_args, **_kwargs) -> None:
        return None


try:  # pragma: no cover - exercised in environments with the dep
    from prometheus_client import Counter as _PromCounter

    autobot_kb_redis_unreachable_total = _PromCounter(
        "autobot_kb_redis_unreachable_total",
        "Count of KB requests served with Redis unreachable (kb_connected=false).",
        ("endpoint",),
    )
except Exception:  # pragma: no cover - defensive fallback
    autobot_kb_redis_unreachable_total = _NoopCounter()


__all__ = ["autobot_kb_redis_unreachable_total"]
