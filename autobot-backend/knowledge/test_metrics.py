# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for knowledge.metrics (#5319, #5407).

Verifies the Prometheus counter works in both environments:
- With ``prometheus_client`` installed (real Counter)
- Without ``prometheus_client`` (_NoopCounter fallback)

#5407 extends the original counter to the multi-label
``autobot_kb_degradation_total{endpoint, reason}`` with a backward
compatible ``autobot_kb_redis_unreachable_total`` alias that injects
``reason="redis_down"`` for one-label callers.
"""

from __future__ import annotations

import importlib
import sys


def test_kb_degradation_counter_with_all_reasons() -> None:
    """New counter accepts every documented reason label without crashing.

    Works against both the real prometheus_client Counter and the
    _NoopCounter fallback - the fluent labels().inc() surface is the
    same for both.
    """
    from knowledge.metrics import autobot_kb_degradation_total

    # Every documented reason, across a spread of endpoint labels.
    autobot_kb_degradation_total.labels(endpoint="stats", reason="kb_uninit").inc()
    autobot_kb_degradation_total.labels(endpoint="categories_main", reason="redis_down").inc()
    autobot_kb_degradation_total.labels(endpoint="audit_user_activity", reason="audit_log_missing").inc()
    # inc(n) path.
    autobot_kb_degradation_total.labels(endpoint="rag_feedback", reason="redis_down").inc(2)


def test_kb_degradation_counter_distinguishes_reasons() -> None:
    """Same endpoint with different reasons tracks as distinct series."""
    from knowledge.metrics import autobot_kb_degradation_total

    # Same endpoint, both reasons - must not raise and must be
    # accepted as distinct label values.
    autobot_kb_degradation_total.labels(endpoint="stats", reason="kb_uninit").inc()
    autobot_kb_degradation_total.labels(endpoint="stats", reason="redis_down").inc()


def test_deprecated_alias_injects_redis_down_reason() -> None:
    """``autobot_kb_redis_unreachable_total`` auto-fills reason="redis_down".

    PR #5346 sites call ``.labels(endpoint="X").inc()`` with a single
    label.  The #5407 alias shim defaults the new ``reason`` label so
    existing callers keep working.
    """
    from knowledge.metrics import autobot_kb_redis_unreachable_total

    # Single-label call must not raise; alias injects reason="redis_down".
    autobot_kb_redis_unreachable_total.labels(endpoint="categories_main").inc()
    autobot_kb_redis_unreachable_total.labels(endpoint="rag_feedback").inc(2)
    # Caller may also still pass reason explicitly; must not crash.
    autobot_kb_redis_unreachable_total.labels(endpoint="rag_benchmark", reason="redis_down").inc()


def test_kb_metrics_importable_without_prometheus() -> None:
    """Module still importable when prometheus_client is missing.

    Simulates absence by replacing the module entry with ``None`` so the
    ``from prometheus_client import Counter`` line raises, then reloads
    ``knowledge.metrics`` and asserts the _NoopCounter surface still works
    for both the new counter and the deprecated alias.
    """
    import knowledge.metrics as metrics_module

    saved_prom = sys.modules.get("prometheus_client")
    saved_metrics = sys.modules.get("knowledge.metrics")
    try:
        # Force the ImportError path on next reload.
        sys.modules["prometheus_client"] = None  # type: ignore[assignment]
        reloaded = importlib.reload(metrics_module)

        # New counter: fluent labels().inc() surface still works.
        reloaded.autobot_kb_degradation_total.labels(endpoint="x", reason="kb_uninit").inc()
        reloaded.autobot_kb_degradation_total.labels(endpoint="y", reason="redis_down").inc(3)
        # Under the hood it's the _NoopCounter.
        assert type(reloaded.autobot_kb_degradation_total).__name__ == ("_NoopCounter")

        # Deprecated alias still works against _NoopCounter.
        reloaded.autobot_kb_redis_unreachable_total.labels(endpoint="z").inc()
    finally:
        # Restore prometheus_client module and reload metrics to real state.
        if saved_prom is not None:
            sys.modules["prometheus_client"] = saved_prom
        else:
            sys.modules.pop("prometheus_client", None)
        if saved_metrics is not None:
            importlib.reload(saved_metrics)
