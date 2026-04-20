# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for knowledge.metrics (#5319).

Verifies the Prometheus counter works in both environments:
- With ``prometheus_client`` installed (real Counter)
- Without ``prometheus_client`` (_NoopCounter fallback)
"""

from __future__ import annotations

import importlib
import sys


def test_kb_redis_unreachable_counter_increments() -> None:
    """Counter accepts labels().inc() calls without crashing.

    Works against both the real prometheus_client Counter and the
    _NoopCounter fallback - the fluent labels().inc() surface is the
    same for both.
    """
    from knowledge.metrics import autobot_kb_redis_unreachable_total

    autobot_kb_redis_unreachable_total.labels(endpoint="test").inc()
    autobot_kb_redis_unreachable_total.labels(endpoint="test").inc(2)
    # Distinct label values must not crash either.
    autobot_kb_redis_unreachable_total.labels(endpoint="categories_main").inc()


def test_kb_metrics_importable_without_prometheus() -> None:
    """Module still importable when prometheus_client is missing.

    Simulates absence by replacing the module entry with ``None`` so the
    ``from prometheus_client import Counter`` line raises, then reloads
    ``knowledge.metrics`` and asserts the _NoopCounter surface still works.
    """
    import knowledge.metrics as metrics_module

    saved_prom = sys.modules.get("prometheus_client")
    saved_metrics = sys.modules.get("knowledge.metrics")
    try:
        # Force the ImportError path on next reload.
        sys.modules["prometheus_client"] = None  # type: ignore[assignment]
        reloaded = importlib.reload(metrics_module)
        # The exposed counter still accepts the fluent labels().inc() surface.
        reloaded.autobot_kb_redis_unreachable_total.labels(endpoint="x").inc()
        reloaded.autobot_kb_redis_unreachable_total.labels(endpoint="y").inc(3)
        # And it is the _NoopCounter instance under the hood.
        assert type(reloaded.autobot_kb_redis_unreachable_total).__name__ == (
            "_NoopCounter"
        )
    finally:
        # Restore prometheus_client module and reload metrics to real state.
        if saved_prom is not None:
            sys.modules["prometheus_client"] = saved_prom
        else:
            sys.modules.pop("prometheus_client", None)
        if saved_metrics is not None:
            importlib.reload(saved_metrics)
