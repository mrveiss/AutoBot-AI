# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Delta Engine — Crucix-pattern Stateful Change Detection (Issue #1947)
=====================================================================

Compares consecutive metric snapshots to detect significant changes.
Each metric has configurable thresholds for *moderate* and *critical* severity.
Consecutive snapshots are compared as a percentage change; if that change
exceeds a threshold the result is flagged accordingly.

A *risk direction summary* aggregates a batch of DeltaResults into a single
directional signal (``"up"``, ``"down"``, or ``"stable"``) that reflects whether
more metrics are moving toward risk than away from it.

Redis hot storage
-----------------
The last three snapshot values for every metric are kept in Redis under the
key ``delta:history:{metric_name}`` as a Redis list (newest at index 0).
This allows cross-process continuity: a new process can pick up where the
previous one left off without losing the last known value.

Key expiry: 24 hours (configurable via ``snapshot_ttl_seconds``).

Usage
-----
    from autobot_shared.delta_engine import DeltaEngine, MetricThreshold

    thresholds = {
        "cpu_percent":  MetricThreshold("cpu_percent",  moderate_pct=10.0, critical_pct=30.0),
        "error_count":  MetricThreshold("error_count",  moderate_pct=25.0, critical_pct=75.0),
    }
    engine = DeltaEngine(thresholds)

    metrics = {"cpu_percent": 82.0, "error_count": 12.0}
    results = engine.compute_batch(metrics)

    direction = engine.get_risk_direction(results)
    # direction == "up"  →  more metrics degrading than improving
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Dict, List

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HISTORY_KEY_PREFIX = "delta:history:"
_DEFAULT_SNAPSHOT_TTL = 86400  # 24 hours
_MAX_HISTORY_SNAPSHOTS = 3


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class MetricThreshold:
    """Per-metric change thresholds used by the delta engine.

    Attributes:
        name: Unique metric identifier (must match the key in the metrics dict).
        moderate_pct: Percentage change that triggers a ``moderate`` severity
            flag.  Defaults to ``10.0`` (i.e. a 10 % change).
        critical_pct: Percentage change that triggers a ``critical`` severity
            flag.  Defaults to ``30.0`` (i.e. a 30 % change).  Must be ≥
            ``moderate_pct``; if not, a warning is logged and the value is
            clamped at construction time.
    """

    name: str
    moderate_pct: float = 10.0
    critical_pct: float = 30.0

    def __post_init__(self) -> None:
        if self.critical_pct < self.moderate_pct:
            logger.warning(
                "delta_engine: MetricThreshold '%s': critical_pct (%.1f) < moderate_pct (%.1f) "
                "— clamping critical_pct to moderate_pct",
                self.name,
                self.critical_pct,
                self.moderate_pct,
            )
            self.critical_pct = self.moderate_pct


@dataclass
class DeltaResult:
    """The outcome of comparing one metric's current value to its previous value.

    Attributes:
        metric_name: Identifier for the metric that was evaluated.
        previous_value: The most recent historical snapshot, or ``None`` if no
            prior value existed (first observation).
        current_value: The value provided in the current batch.
        change_pct: Absolute percentage change relative to ``previous_value``.
            ``0.0`` when ``previous_value`` is ``None`` or zero.
        severity: One of ``"none"``, ``"moderate"``, or ``"critical"``.
        direction: One of ``"up"``, ``"down"``, or ``"stable"``.  For a first
            observation (``previous_value is None``) this is always
            ``"stable"``.
    """

    metric_name: str
    previous_value: float | None
    current_value: float
    change_pct: float
    severity: str  # "none" | "moderate" | "critical"
    direction: str  # "up" | "down" | "stable"


@dataclass
class RiskDirectionSummary:
    """Aggregate risk direction across a batch of DeltaResults.

    Attributes:
        direction: Overall direction — ``"up"`` if more metrics are moving toward
            risk, ``"down"`` if more are improving, ``"stable"`` if balanced or
            no significant movement.
        up_count: Number of metrics whose value increased significantly.
        down_count: Number of metrics whose value decreased significantly.
        stable_count: Number of metrics with no significant change.
        critical_count: Number of metrics flagged as ``critical``.
        moderate_count: Number of metrics flagged as ``moderate``.
    """

    direction: str
    up_count: int = 0
    down_count: int = 0
    stable_count: int = 0
    critical_count: int = 0
    moderate_count: int = 0


# ---------------------------------------------------------------------------
# DeltaEngine
# ---------------------------------------------------------------------------


class DeltaEngine:
    """Stateful change-detection engine using the Crucix delta pattern.

    Compares each incoming metric value against the most recent snapshot
    stored in Redis.  Results are classified by severity and direction.

    Args:
        thresholds: Mapping of metric name → MetricThreshold.  Metrics not
            present in this mapping are evaluated with default thresholds
            (moderate=10 %, critical=30 %).
        database: Redis logical database to use for snapshot storage.
            Defaults to ``"metrics"``.
        snapshot_ttl_seconds: TTL (in seconds) applied to each history key.
            Defaults to 86 400 s (24 hours).
    """

    def __init__(
        self,
        thresholds: Dict[str, MetricThreshold] | None = None,
        database: str = "metrics",
        snapshot_ttl_seconds: int = _DEFAULT_SNAPSHOT_TTL,
    ) -> None:
        self._thresholds: Dict[str, MetricThreshold] = thresholds or {}
        self._database = database
        self._snapshot_ttl = snapshot_ttl_seconds

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_delta(
        self,
        metric_name: str,
        current_value: float,
        threshold: MetricThreshold | None = None,
    ) -> DeltaResult:
        """Compare *current_value* against the most recent stored snapshot.

        Persists *current_value* as the new head of the history list in Redis
        after computing the result, so the next call sees this value as the
        previous snapshot.

        Args:
            metric_name: Unique name for this metric.
            current_value: The freshly sampled value.
            threshold: Override threshold for this call.  If ``None``, the
                engine first looks up ``self._thresholds[metric_name]`` and
                falls back to a default MetricThreshold.

        Returns:
            A populated :class:`DeltaResult`.
        """
        effective_threshold = threshold or self._thresholds.get(metric_name) or MetricThreshold(metric_name)
        previous = self._load_latest_snapshot(metric_name)
        result = _compute_single_delta(metric_name, previous, current_value, effective_threshold)
        self._persist_snapshot(metric_name, current_value)
        return result

    def compute_batch(
        self,
        metrics: Dict[str, float],
        thresholds: Dict[str, MetricThreshold] | None = None,
    ) -> List[DeltaResult]:
        """Compute deltas for all metrics in *metrics* in a single pass.

        Each metric is evaluated independently.  Snapshots are updated
        atomically per metric as :meth:`compute_delta` is called.

        Args:
            metrics: Mapping of metric name → current sampled value.
            thresholds: Optional per-call threshold overrides.  Merged on top
                of ``self._thresholds`` — call-level keys take precedence.

        Returns:
            List of :class:`DeltaResult`, one per entry in *metrics*, in
            iteration order.
        """
        merged_thresholds = {**self._thresholds, **(thresholds or {})}
        results: List[DeltaResult] = []
        for name, value in metrics.items():
            threshold = merged_thresholds.get(name) or MetricThreshold(name)
            result = self.compute_delta(name, value, threshold=threshold)
            results.append(result)
        return results

    def get_risk_direction(self, results: List[DeltaResult]) -> RiskDirectionSummary:
        """Derive an aggregate risk direction from a list of delta results.

        Direction logic:
        - Only results with ``severity != "none"`` are counted as directional.
        - ``"up"`` increments *up_count*; ``"down"`` increments *down_count*.
        - Overall direction is ``"up"`` if *up_count* > *down_count*,
          ``"down"`` if *down_count* > *up_count*, and ``"stable"`` otherwise.

        Args:
            results: List of :class:`DeltaResult` (typically from
                :meth:`compute_batch`).

        Returns:
            A :class:`RiskDirectionSummary` with counts and overall direction.
        """
        summary = RiskDirectionSummary(direction="stable")
        for r in results:
            if r.severity == "critical":
                summary.critical_count += 1
            elif r.severity == "moderate":
                summary.moderate_count += 1

            if r.severity != "none":
                if r.direction == "up":
                    summary.up_count += 1
                elif r.direction == "down":
                    summary.down_count += 1
                else:
                    summary.stable_count += 1
            else:
                summary.stable_count += 1

        if summary.up_count > summary.down_count:
            summary.direction = "up"
        elif summary.down_count > summary.up_count:
            summary.direction = "down"
        else:
            summary.direction = "stable"

        return summary

    def prune_old_snapshots(self, metric_name: str) -> None:
        """Trim the stored history list for *metric_name* to the maximum length.

        Normally the list is kept at most ``_MAX_HISTORY_SNAPSHOTS`` entries by
        :meth:`_persist_snapshot`.  Call this explicitly if you suspect drift
        (e.g. after a Redis restore or bulk import).

        Args:
            metric_name: The metric whose history should be pruned.
        """
        client = self._get_client()
        if client is None:
            return
        key = _history_key(metric_name)
        try:
            client.ltrim(key, 0, _MAX_HISTORY_SNAPSHOTS - 1)
            logger.debug("delta_engine: pruned history for '%s'", metric_name)
        except Exception as exc:
            logger.error(
                "delta_engine: prune_old_snapshots failed for '%s': %s",
                metric_name,
                exc,
            )

    # ------------------------------------------------------------------
    # Internal helpers — Redis I/O
    # ------------------------------------------------------------------

    def _load_latest_snapshot(self, metric_name: str) -> float | None:
        """Return the most recent stored snapshot for *metric_name*, or ``None``."""
        client = self._get_client()
        if client is None:
            return None
        key = _history_key(metric_name)
        try:
            raw = client.lindex(key, 0)
            if raw is None:
                return None
            return float(json.loads(raw))
        except Exception as exc:
            logger.error("delta_engine: failed to load snapshot for '%s': %s", metric_name, exc)
            return None

    def _persist_snapshot(self, metric_name: str, value: float) -> None:
        """Push *value* to the head of the history list and trim to max length."""
        client = self._get_client()
        if client is None:
            return
        key = _history_key(metric_name)
        try:
            pipe = client.pipeline()
            pipe.lpush(key, json.dumps(value))
            pipe.ltrim(key, 0, _MAX_HISTORY_SNAPSHOTS - 1)
            pipe.expire(key, self._snapshot_ttl)
            pipe.execute()
        except Exception as exc:
            logger.error(
                "delta_engine: failed to persist snapshot for '%s': %s",
                metric_name,
                exc,
            )

    def _get_client(self):
        """Return a synchronous Redis client, or ``None`` on failure."""
        try:
            return get_redis_client(async_client=False, database=self._database)
        except Exception as exc:
            logger.error("delta_engine: failed to obtain Redis client: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _history_key(metric_name: str) -> str:
    """Return the Redis key for storing metric history.

    Args:
        metric_name: The metric identifier.

    Returns:
        Redis key string: ``delta:history:{metric_name}``.
    """
    return f"{_HISTORY_KEY_PREFIX}{metric_name}"


def _compute_single_delta(
    metric_name: str,
    previous: float | None,
    current: float,
    threshold: MetricThreshold,
) -> DeltaResult:
    """Compute severity and direction for a single metric value pair.

    Args:
        metric_name: Identifier for logging / result population.
        previous: The last known value, or ``None`` for first observation.
        current: The newly sampled value.
        threshold: Thresholds governing severity classification.

    Returns:
        A fully populated :class:`DeltaResult`.
    """
    if previous is None:
        return DeltaResult(
            metric_name=metric_name,
            previous_value=None,
            current_value=current,
            change_pct=0.0,
            severity="none",
            direction="stable",
        )

    change_pct = _percentage_change(previous, current)
    abs_change = abs(change_pct)

    if abs_change >= threshold.critical_pct:
        severity = "critical"
    elif abs_change >= threshold.moderate_pct:
        severity = "moderate"
    else:
        severity = "none"

    if change_pct > 0:
        direction = "up"
    elif change_pct < 0:
        direction = "down"
    else:
        direction = "stable"

    logger.debug(
        "delta_engine: '%s' previous=%.4f current=%.4f change_pct=%.2f%% severity=%s direction=%s",
        metric_name,
        previous,
        current,
        change_pct,
        severity,
        direction,
    )

    return DeltaResult(
        metric_name=metric_name,
        previous_value=previous,
        current_value=current,
        change_pct=change_pct,
        severity=severity,
        direction=direction,
    )


def _percentage_change(previous: float, current: float) -> float:
    """Compute the signed percentage change from *previous* to *current*.

    When *previous* is exactly zero the change is undefined; returns ``0.0``
    to avoid division-by-zero and logs a debug notice.

    Args:
        previous: Baseline value.
        current: New value.

    Returns:
        Signed percentage change: positive → increase, negative → decrease.
        ``0.0`` when *previous* is zero.
    """
    if previous == 0.0:
        logger.debug("delta_engine: previous value is zero — change_pct returned as 0.0")
        return 0.0
    return ((current - previous) / abs(previous)) * 100.0
