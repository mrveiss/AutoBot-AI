# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Counters for quality gates that fail open: how often they gave no reading (#21844, #21845).

Both gates let the work through when they cannot judge, by owner decision, so an unchecked action or reply is
invisible in a green run. An audit event records each one; these counters make the rate readable on the
dashboard the other recorders feed.

* ``autobot_verifier_timeout_total{tool}``: a pre-action verifier pass that timed out, per tool.
* ``autobot_turn_not_evaluated_total{reason}``: a turn whose reply the RLM evaluator could not judge.

The recorder registers on the shared manager's registry (``quality_gate_metrics``), so no edit to the
size-ratcheted manager module is needed and the series appear on the existing metrics endpoint.
"""

from __future__ import annotations

import threading
import weakref

from prometheus_client import CollectorRegistry, Counter

from .base import BaseMetricsRecorder
from .label_bounds import BoundedLabels


class QualityGateMetricsRecorder(BaseMetricsRecorder):
    """Recorder for fail-open quality-gate outcomes."""

    def _init_metrics(self) -> None:
        self._labels = BoundedLabels()
        self.verifier_timeout_total = Counter(
            "autobot_verifier_timeout_total",
            "Pre-action verifier passes that timed out and let the action through, by tool",
            ["tool"],
            registry=self.registry,
        )
        self.turn_not_evaluated_total = Counter(
            "autobot_turn_not_evaluated_total",
            "Turns whose reply the RLM evaluator could not judge (timeout or failure), by reason",
            ["reason"],
            registry=self.registry,
        )

    def record_verifier_timeout(self, tool: str) -> None:
        """Count one verifier timeout for *tool* (the label is bounded: a model-invented name cannot grow it)."""
        self.verifier_timeout_total.labels(tool=self._labels.bound("tool", tool)).inc()

    def record_turn_not_evaluated(self, reason: str) -> None:
        """Count one turn the evaluator did not judge, by *reason*."""
        self.turn_not_evaluated_total.labels(reason=self._labels.bound("reason", reason)).inc()


_recorders: "weakref.WeakKeyDictionary[CollectorRegistry, QualityGateMetricsRecorder]" = weakref.WeakKeyDictionary()
_lock = threading.Lock()


def quality_gate_metrics() -> QualityGateMetricsRecorder:
    """The recorder registered on the shared metrics manager's registry (created once per registry)."""
    from autobot_shared.monitoring.prometheus_metrics import get_metrics_manager

    registry = get_metrics_manager().registry
    with _lock:
        if registry not in _recorders:
            _recorders[registry] = QualityGateMetricsRecorder(registry)
        return _recorders[registry]


__all__ = ["QualityGateMetricsRecorder", "quality_gate_metrics"]
