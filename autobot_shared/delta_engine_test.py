# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for the Crucix-pattern delta engine (Issue #1947).

Uses a stub ``autobot_shared.redis_client`` injected before the module under
test is imported — the same pattern used by ``alert_cooldown_test.py`` — so a
live Redis connection is never required.
"""

import json
import sys
import types
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Install redis_client stub BEFORE importing delta_engine
# ---------------------------------------------------------------------------


def _install_redis_stub() -> None:
    """Inject a fake autobot_shared.redis_client into sys.modules."""
    mod_name = "autobot_shared.redis_client"
    if mod_name in sys.modules:
        return
    stub = types.ModuleType(mod_name)
    stub.get_redis_client = MagicMock(name="stub_get_redis_client")
    sys.modules[mod_name] = stub


_install_redis_stub()

# Safe to import now
from autobot_shared.delta_engine import (  # noqa: E402
    DeltaEngine,
    DeltaResult,
    MetricThreshold,
    RiskDirectionSummary,
    _compute_single_delta,
    _history_key,
    _percentage_change,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_redis_client(*, stored_value: float = None):
    """Return a mock synchronous Redis client.

    Args:
        stored_value: The float that ``lindex(key, 0)`` will return (as a
            JSON-encoded bytes string), or ``None`` to simulate a missing key.
    """
    client = MagicMock()

    raw = json.dumps(stored_value).encode() if stored_value is not None else None
    client.lindex = MagicMock(return_value=raw)

    pipe = MagicMock()
    pipe.lpush = MagicMock()
    pipe.ltrim = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = MagicMock(return_value=[1, True, True])
    client.pipeline = MagicMock(return_value=pipe)

    client.ltrim = MagicMock()

    return client


def _make_engine(redis_client, **kwargs) -> DeltaEngine:
    """Return a DeltaEngine whose _get_client() returns the supplied mock."""
    engine = DeltaEngine(**kwargs)
    engine._get_client = MagicMock(return_value=redis_client)
    return engine


# ---------------------------------------------------------------------------
# Tests — _percentage_change helper
# ---------------------------------------------------------------------------


class TestPercentageChange:
    def test_increase(self) -> None:
        assert _percentage_change(100.0, 110.0) == 10.0

    def test_decrease(self) -> None:
        assert _percentage_change(100.0, 90.0) == -10.0

    def test_no_change(self) -> None:
        assert _percentage_change(50.0, 50.0) == 0.0

    def test_previous_zero_returns_zero(self) -> None:
        """Division by zero must be avoided; returns 0.0."""
        assert _percentage_change(0.0, 42.0) == 0.0

    def test_large_increase(self) -> None:
        assert _percentage_change(10.0, 40.0) == 300.0

    def test_negative_baseline(self) -> None:
        """abs(previous) used as denominator so sign of previous is handled."""
        result = _percentage_change(-100.0, -80.0)
        # (-80 - -100) / abs(-100) * 100 = 20/100*100 = 20.0
        assert result == 20.0

    def test_decrease_to_zero(self) -> None:
        assert _percentage_change(50.0, 0.0) == -100.0


# ---------------------------------------------------------------------------
# Tests — _history_key helper
# ---------------------------------------------------------------------------


class TestHistoryKey:
    def test_prefix_applied(self) -> None:
        assert _history_key("cpu_percent") == "delta:history:cpu_percent"

    def test_special_chars_preserved(self) -> None:
        assert _history_key("node:1:mem") == "delta:history:node:1:mem"


# ---------------------------------------------------------------------------
# Tests — MetricThreshold dataclass
# ---------------------------------------------------------------------------


class TestMetricThreshold:
    def test_defaults(self) -> None:
        t = MetricThreshold("latency_ms")
        assert t.moderate_pct == 10.0
        assert t.critical_pct == 30.0

    def test_custom_values(self) -> None:
        t = MetricThreshold("error_rate", moderate_pct=5.0, critical_pct=20.0)
        assert t.moderate_pct == 5.0
        assert t.critical_pct == 20.0

    def test_critical_clamped_when_below_moderate(self) -> None:
        """critical_pct < moderate_pct: critical_pct is clamped to moderate_pct."""
        t = MetricThreshold("x", moderate_pct=20.0, critical_pct=5.0)
        assert t.critical_pct == 20.0

    def test_equal_thresholds_allowed(self) -> None:
        t = MetricThreshold("x", moderate_pct=15.0, critical_pct=15.0)
        assert t.moderate_pct == t.critical_pct == 15.0


# ---------------------------------------------------------------------------
# Tests — _compute_single_delta (pure logic, no Redis)
# ---------------------------------------------------------------------------


class TestComputeSingleDelta:
    def _threshold(self, moderate=10.0, critical=30.0):
        return MetricThreshold("m", moderate_pct=moderate, critical_pct=critical)

    def test_first_observation_no_previous(self) -> None:
        result = _compute_single_delta("cpu", None, 80.0, self._threshold())
        assert result.previous_value is None
        assert result.current_value == 80.0
        assert result.change_pct == 0.0
        assert result.severity == "none"
        assert result.direction == "stable"

    def test_no_change(self) -> None:
        result = _compute_single_delta("cpu", 80.0, 80.0, self._threshold())
        assert result.severity == "none"
        assert result.direction == "stable"
        assert result.change_pct == 0.0

    def test_below_moderate_threshold(self) -> None:
        """< 10 % change → severity none."""
        result = _compute_single_delta("cpu", 100.0, 105.0, self._threshold())
        assert result.severity == "none"
        assert result.direction == "up"

    def test_exactly_moderate_threshold(self) -> None:
        """Exactly at moderate boundary → severity moderate."""
        result = _compute_single_delta("cpu", 100.0, 110.0, self._threshold(moderate=10.0))
        assert result.severity == "moderate"
        assert result.direction == "up"

    def test_between_moderate_and_critical(self) -> None:
        """Between moderate and critical → severity moderate."""
        result = _compute_single_delta("cpu", 100.0, 120.0, self._threshold(moderate=10.0, critical=30.0))
        assert result.severity == "moderate"
        assert result.direction == "up"

    def test_exactly_critical_threshold(self) -> None:
        """Exactly at critical boundary → severity critical."""
        result = _compute_single_delta("cpu", 100.0, 130.0, self._threshold(moderate=10.0, critical=30.0))
        assert result.severity == "critical"
        assert result.direction == "up"

    def test_above_critical_threshold(self) -> None:
        """Well above critical → severity critical."""
        result = _compute_single_delta("cpu", 100.0, 200.0, self._threshold())
        assert result.severity == "critical"
        assert result.direction == "up"

    def test_direction_down_on_decrease(self) -> None:
        result = _compute_single_delta("cpu", 100.0, 60.0, self._threshold(moderate=10.0, critical=30.0))
        assert result.severity == "critical"
        assert result.direction == "down"

    def test_direction_down_moderate(self) -> None:
        result = _compute_single_delta("mem", 200.0, 178.0, self._threshold(moderate=10.0, critical=30.0))
        assert result.severity == "moderate"
        assert result.direction == "down"

    def test_metric_name_preserved(self) -> None:
        result = _compute_single_delta("disk_io", 50.0, 55.0, self._threshold())
        assert result.metric_name == "disk_io"

    def test_change_pct_sign_matches_direction(self) -> None:
        result = _compute_single_delta("x", 100.0, 90.0, self._threshold())
        assert result.change_pct < 0
        assert result.direction == "down"


# ---------------------------------------------------------------------------
# Tests — DeltaEngine.compute_delta (with mocked Redis)
# ---------------------------------------------------------------------------


class TestDeltaEngineComputeDelta:
    def test_first_observation_no_prior_snapshot(self) -> None:
        """When Redis has no stored value, result is first-observation (stable/none)."""
        client = _make_redis_client(stored_value=None)
        engine = _make_engine(client)
        result = engine.compute_delta("cpu", 75.0)

        assert result.previous_value is None
        assert result.severity == "none"
        assert result.direction == "stable"

    def test_snapshot_persisted_after_compute(self) -> None:
        """compute_delta must call lpush + ltrim + expire via pipeline."""
        client = _make_redis_client(stored_value=None)
        engine = _make_engine(client)
        engine.compute_delta("cpu", 75.0)

        pipe = client.pipeline.return_value
        pipe.lpush.assert_called_once()
        pipe.ltrim.assert_called_once()
        pipe.expire.assert_called_once()
        pipe.execute.assert_called_once()

    def test_stored_value_becomes_previous(self) -> None:
        """The value from lindex(0) must be used as previous_value."""
        client = _make_redis_client(stored_value=70.0)
        engine = _make_engine(
            client,
            thresholds={"cpu": MetricThreshold("cpu", moderate_pct=5.0, critical_pct=20.0)},
        )
        result = engine.compute_delta("cpu", 77.0)

        assert result.previous_value == 70.0
        assert result.current_value == 77.0
        # (77-70)/70*100 ≈ 10 % → moderate
        assert result.severity == "moderate"
        assert result.direction == "up"

    def test_threshold_override_at_call_level(self) -> None:
        """Explicit threshold argument overrides engine-level thresholds."""
        client = _make_redis_client(stored_value=100.0)
        engine = _make_engine(
            client,
            thresholds={"cpu": MetricThreshold("cpu", moderate_pct=5.0, critical_pct=10.0)},
        )
        # Use a stricter override
        override = MetricThreshold("cpu", moderate_pct=50.0, critical_pct=80.0)
        result = engine.compute_delta("cpu", 110.0, threshold=override)

        # 10 % change is below override's moderate threshold of 50 % → none
        assert result.severity == "none"

    def test_returns_delta_result_instance(self) -> None:
        client = _make_redis_client(stored_value=None)
        engine = _make_engine(client)
        result = engine.compute_delta("x", 1.0)
        assert isinstance(result, DeltaResult)

    def test_redis_unavailable_falls_back_gracefully(self) -> None:
        """When _get_client returns None, previous is None → first-observation."""
        engine = DeltaEngine()
        engine._get_client = MagicMock(return_value=None)
        result = engine.compute_delta("x", 99.0)
        assert result.previous_value is None
        assert result.severity == "none"

    def test_lpush_key_contains_metric_name(self) -> None:
        """The Redis key passed to lpush must embed the metric name."""
        client = _make_redis_client(stored_value=None)
        engine = _make_engine(client)
        engine.compute_delta("disk_io", 50.0)

        pipe = client.pipeline.return_value
        lpush_key = pipe.lpush.call_args[0][0]
        assert "disk_io" in lpush_key


# ---------------------------------------------------------------------------
# Tests — DeltaEngine.compute_batch
# ---------------------------------------------------------------------------


class TestDeltaEngineComputeBatch:
    def test_returns_one_result_per_metric(self) -> None:
        client = _make_redis_client(stored_value=None)
        engine = _make_engine(client)
        metrics = {"cpu": 80.0, "mem": 60.0, "disk": 40.0}
        results = engine.compute_batch(metrics)
        assert len(results) == 3

    def test_result_metric_names_match_input(self) -> None:
        client = _make_redis_client(stored_value=None)
        engine = _make_engine(client)
        metrics = {"alpha": 1.0, "beta": 2.0}
        results = engine.compute_batch(metrics)
        names = {r.metric_name for r in results}
        assert names == {"alpha", "beta"}

    def test_call_level_thresholds_override_engine_thresholds(self) -> None:
        """Thresholds passed to compute_batch take precedence."""
        client = _make_redis_client(stored_value=100.0)
        engine_thresholds = {"cpu": MetricThreshold("cpu", moderate_pct=5.0, critical_pct=15.0)}
        engine = _make_engine(client, thresholds=engine_thresholds)

        # A very high threshold means 20 % change is not significant
        call_thresholds = {"cpu": MetricThreshold("cpu", moderate_pct=50.0, critical_pct=80.0)}
        results = engine.compute_batch({"cpu": 120.0}, thresholds=call_thresholds)

        assert results[0].severity == "none"

    def test_empty_metrics_returns_empty_list(self) -> None:
        client = _make_redis_client(stored_value=None)
        engine = _make_engine(client)
        assert engine.compute_batch({}) == []

    def test_default_threshold_applied_for_unknown_metric(self) -> None:
        """Metrics without a threshold entry use MetricThreshold defaults (10/30 %)."""
        client = _make_redis_client(stored_value=100.0)
        engine = _make_engine(client, thresholds={})
        # 15 % increase → above 10 % moderate default
        results = engine.compute_batch({"unknown_metric": 115.0})
        assert results[0].severity == "moderate"


# ---------------------------------------------------------------------------
# Tests — DeltaEngine.get_risk_direction
# ---------------------------------------------------------------------------


class TestGetRiskDirection:
    def _make_result(self, severity, direction):
        return DeltaResult("m", 100.0, 110.0, 10.0, severity, direction)

    def test_all_stable_returns_stable(self) -> None:
        results = [self._make_result("none", "stable")] * 5
        engine = DeltaEngine()
        summary = engine.get_risk_direction(results)
        assert summary.direction == "stable"
        assert summary.up_count == 0
        assert summary.down_count == 0

    def test_more_up_than_down_returns_up(self) -> None:
        results = [
            self._make_result("moderate", "up"),
            self._make_result("moderate", "up"),
            self._make_result("moderate", "down"),
        ]
        engine = DeltaEngine()
        summary = engine.get_risk_direction(results)
        assert summary.direction == "up"
        assert summary.up_count == 2
        assert summary.down_count == 1

    def test_more_down_than_up_returns_down(self) -> None:
        results = [
            self._make_result("critical", "down"),
            self._make_result("critical", "down"),
            self._make_result("moderate", "up"),
        ]
        engine = DeltaEngine()
        summary = engine.get_risk_direction(results)
        assert summary.direction == "down"

    def test_equal_up_down_returns_stable(self) -> None:
        results = [
            self._make_result("moderate", "up"),
            self._make_result("moderate", "down"),
        ]
        engine = DeltaEngine()
        summary = engine.get_risk_direction(results)
        assert summary.direction == "stable"

    def test_only_none_severity_counted_as_stable(self) -> None:
        """Results with severity='none' must not contribute to up/down counts."""
        results = [
            self._make_result("none", "up"),
            self._make_result("none", "down"),
        ]
        engine = DeltaEngine()
        summary = engine.get_risk_direction(results)
        assert summary.up_count == 0
        assert summary.down_count == 0
        assert summary.stable_count == 2

    def test_critical_count_tracked(self) -> None:
        results = [
            self._make_result("critical", "up"),
            self._make_result("critical", "up"),
            self._make_result("moderate", "up"),
        ]
        engine = DeltaEngine()
        summary = engine.get_risk_direction(results)
        assert summary.critical_count == 2
        assert summary.moderate_count == 1

    def test_empty_results_returns_stable(self) -> None:
        engine = DeltaEngine()
        summary = engine.get_risk_direction([])
        assert summary.direction == "stable"
        assert summary.up_count == 0
        assert summary.down_count == 0

    def test_returns_risk_direction_summary_instance(self) -> None:
        engine = DeltaEngine()
        result = engine.get_risk_direction([])
        assert isinstance(result, RiskDirectionSummary)


# ---------------------------------------------------------------------------
# Tests — DeltaEngine.prune_old_snapshots
# ---------------------------------------------------------------------------


class TestPruneOldSnapshots:
    def test_calls_ltrim_with_correct_bounds(self) -> None:
        client = _make_redis_client()
        engine = _make_engine(client)
        engine.prune_old_snapshots("cpu")

        client.ltrim.assert_called_once_with("delta:history:cpu", 0, 2)

    def test_no_error_when_redis_unavailable(self) -> None:
        """prune_old_snapshots must not raise when Redis is None."""
        engine = DeltaEngine()
        engine._get_client = MagicMock(return_value=None)
        engine.prune_old_snapshots("cpu")  # Should not raise


# ---------------------------------------------------------------------------
# Tests — Redis hot storage round-trip
# ---------------------------------------------------------------------------


class TestRedisHotStorage:
    def test_snapshot_stored_with_correct_json(self) -> None:
        """The value pushed to Redis must be valid JSON-encoded float."""
        client = _make_redis_client(stored_value=None)
        engine = _make_engine(client)
        engine.compute_delta("latency", 123.456)

        pipe = client.pipeline.return_value
        pushed_value = pipe.lpush.call_args[0][1]
        assert json.loads(pushed_value) == 123.456

    def test_snapshot_ttl_applied(self) -> None:
        """expire() must be called with the configured snapshot TTL."""
        client = _make_redis_client(stored_value=None)
        engine = _make_engine(client, snapshot_ttl_seconds=3600)
        engine.compute_delta("x", 1.0)

        pipe = client.pipeline.return_value
        expire_call = pipe.expire.call_args
        assert expire_call[0][1] == 3600

    def test_ltrim_limits_to_max_history(self) -> None:
        """After lpush, ltrim must be called to cap history at 3 entries."""
        client = _make_redis_client(stored_value=None)
        engine = _make_engine(client)
        engine.compute_delta("x", 5.0)

        pipe = client.pipeline.return_value
        # ltrim(key, 0, MAX-1) where MAX=3 → end=2
        ltrim_call = pipe.ltrim.call_args
        assert ltrim_call[0][1] == 0
        assert ltrim_call[0][2] == 2

    def test_lindex_called_with_index_zero(self) -> None:
        """_load_latest_snapshot must always read index 0 (most recent)."""
        client = _make_redis_client(stored_value=55.0)
        engine = _make_engine(client)
        engine.compute_delta("net_in", 60.0)

        client.lindex.assert_called_once_with("delta:history:net_in", 0)

    def test_corrupt_redis_value_falls_back_to_none(self) -> None:
        """A non-JSON value in Redis must be handled gracefully → first-observation."""
        client = _make_redis_client()
        client.lindex = MagicMock(return_value=b"not-valid-json")
        engine = _make_engine(client)
        result = engine.compute_delta("x", 42.0)
        assert result.previous_value is None


# ---------------------------------------------------------------------------
# Tests — end-to-end batch → direction scenario
# ---------------------------------------------------------------------------


class TestEndToEndScenario:
    def test_batch_with_mixed_metrics(self):
        """
        Three metrics, one stable, one moderate-up, one critical-up.
        Expected: overall direction 'up', critical_count=1, moderate_count=1.
        """
        # cpu had 100.0, now 115.0 → +15 % → moderate (threshold 10/30)
        # mem had 200.0, now 270.0 → +35 % → critical (threshold 10/30)
        # disk had 50.0,  now 51.0  → +2 %  → none

        def lindex_side_effect(key, idx):
            mapping = {
                "delta:history:cpu": json.dumps(100.0).encode(),
                "delta:history:mem": json.dumps(200.0).encode(),
                "delta:history:disk": json.dumps(50.0).encode(),
            }
            return mapping.get(key)

        client = MagicMock()
        client.lindex = MagicMock(side_effect=lindex_side_effect)
        pipe = MagicMock()
        pipe.execute = MagicMock(return_value=[1, True, True])
        client.pipeline = MagicMock(return_value=pipe)

        thresholds = {
            "cpu": MetricThreshold("cpu", moderate_pct=10.0, critical_pct=30.0),
            "mem": MetricThreshold("mem", moderate_pct=10.0, critical_pct=30.0),
            "disk": MetricThreshold("disk", moderate_pct=10.0, critical_pct=30.0),
        }
        engine = DeltaEngine(thresholds=thresholds)
        engine._get_client = MagicMock(return_value=client)

        results = engine.compute_batch({"cpu": 115.0, "mem": 270.0, "disk": 51.0})
        summary = engine.get_risk_direction(results)

        severities = {r.metric_name: r.severity for r in results}
        assert severities["cpu"] == "moderate"
        assert severities["mem"] == "critical"
        assert severities["disk"] == "none"

        assert summary.direction == "up"
        assert summary.critical_count == 1
        assert summary.moderate_count == 1
        assert summary.up_count == 2
        assert summary.stable_count == 1
