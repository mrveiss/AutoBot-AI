# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""KB-level Prometheus metrics with no-op fallback (#5319, #5407).

This module exposes Prometheus counters for knowledge-base observability.
It degrades to a no-op implementation when ``prometheus_client`` is not
installed (tests, minimal deployments), so importing is always safe.

Current metrics:

``autobot_kb_degradation_total{endpoint, reason}``
    Incremented whenever a KB endpoint serves a degraded response.  The
    ``reason`` label distinguishes failure modes so operators can separate
    'backend bug / cold start' from 'Redis outage':

    - ``kb_uninit``          - KB instance not yet initialized (cold start
                               or factory config problem).  Fix is a code /
                               deployment change, not an infra page.
    - ``redis_down``         - KB exists but Redis is unreachable
                               (``kb_connected=false``).  Infra page.
    - ``audit_log_missing``  - KB exists but its audit log subsystem is
                               unavailable.

Each call site also emits a ``logger.warning`` so operators can page on
either signal.

``autobot_kb_redis_unreachable_total{endpoint}`` is kept as a deprecated
alias so existing dashboards and PR #5346 imports keep working; it
auto-injects ``reason="redis_down"`` for callers that only pass
``endpoint=``.  New call sites MUST import and use
``autobot_kb_degradation_total`` directly with an explicit reason.

Follows the pattern established by ``knowledge/query_sanitizer.py`` (#5064).
"""

from __future__ import annotations

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class _NoopCounter:
    """Fallback counter used when prometheus_client is unavailable."""

    def labels(self, *_args, **_kwargs) -> "_NoopCounter":
        return self

    def inc(self, *_args, **_kwargs) -> None:
        return None


try:  # pragma: no cover - exercised in environments with the dep
    from prometheus_client import Counter as _PromCounter

    autobot_kb_degradation_total = _PromCounter(
        "autobot_kb_degradation_total",
        (
            "Count of KB requests served with a degraded response, labelled "
            "by endpoint and reason (kb_uninit | redis_down | "
            "audit_log_missing)."
        ),
        ("endpoint", "reason"),
    )
except Exception:  # pragma: no cover - defensive fallback
    autobot_kb_degradation_total = _NoopCounter()


class _RedisUnreachableAlias:
    """Deprecated alias for ``autobot_kb_redis_unreachable_total`` (#5319).

    PR #5346 sites called ``.labels(endpoint="X").inc()`` with a single
    label.  The new counter (#5407) requires a ``reason`` label; this
    shim defaults it to ``redis_down`` so existing imports keep working
    without a silent schema mismatch.
    """

    def labels(self, *args, **kwargs) -> object:
        if "reason" not in kwargs:
            kwargs["reason"] = "redis_down"
        return autobot_kb_degradation_total.labels(*args, **kwargs)


autobot_kb_redis_unreachable_total = _RedisUnreachableAlias()


__all__ = [
    "autobot_kb_degradation_total",
    "autobot_kb_redis_unreachable_total",
]
