# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for claude_api_monitor.py — Issue #10721

Verifies:
- calculate_usage_rate returns a real rate from a mocked Prometheus source
- calculate_usage_rate returns 0.0 honestly when Prometheus is unavailable
- get_recent_calls and get_tool_usage_stats no longer exist (dead stubs removed)
- AlertManager.check_usage_alerts fires correctly from Prometheus data
- PromQL shape is correct (increase, correct metric name, window embedded)
"""

import sys
import warnings
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub heavy package-level imports so that importing monitoring.claude_api_monitor
# does not trigger the full prometheus_metrics → autobot_shared init chain,
# which requires live config and log directories not present in test environments.
# Our target module (claude_api_monitor) does NOT import these at module level;
# the stubs only prevent monitoring/__init__.py from failing during pytest
# collection when it tries ``from monitoring.prometheus_metrics import ...``.
# ---------------------------------------------------------------------------
if "monitoring.prometheus_metrics" not in sys.modules:
    sys.modules["monitoring.prometheus_metrics"] = MagicMock()
    # monitoring/__init__.py re-exports two names; provide them on the stub
    sys.modules["monitoring.prometheus_metrics"].PrometheusMetricsManager = MagicMock()
    sys.modules["monitoring.prometheus_metrics"].get_metrics_manager = MagicMock(return_value=MagicMock())

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tracker():
    """Create a UsageTracker suppressing the expected DeprecationWarning."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from monitoring.claude_api_monitor import UsageTracker

        return UsageTracker()


def _make_alert_manager():
    """Create an AlertManager suppressing the expected DeprecationWarning."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from monitoring.claude_api_monitor import AlertManager

        return AlertManager()


def _prometheus_data(total_calls: float):
    """Return a minimal Prometheus instant-query data payload."""
    return {"resultType": "vector", "result": [{"metric": {}, "value": [1700000000.0, str(total_calls)]}]}


def _patch_query_instant(monkeypatch, async_fn):
    """Patch the module-level _prometheus_query_instant reference used by calculate_usage_rate."""
    import monitoring.claude_api_monitor as cam

    monkeypatch.setattr(cam, "_prometheus_query_instant", async_fn)


# ---------------------------------------------------------------------------
# calculate_usage_rate — Prometheus-backed path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calculate_usage_rate_divides_by_window(monkeypatch):
    """120 calls in 60 minutes → 2.0 calls/min."""
    tracker = _make_tracker()

    async def mock_query(promql: str):
        return _prometheus_data(120.0)

    _patch_query_instant(monkeypatch, mock_query)

    rate = await tracker.calculate_usage_rate(60)
    assert rate == pytest.approx(2.0), f"Expected 2.0 calls/min, got {rate}"


@pytest.mark.asyncio
async def test_calculate_usage_rate_one_minute_window(monkeypatch):
    """30 calls in a 1-minute window → 30.0 calls/min."""
    tracker = _make_tracker()

    async def mock_query(promql: str):
        assert "[1m]" in promql, "Should use 1-minute Prometheus window"
        return _prometheus_data(30.0)

    _patch_query_instant(monkeypatch, mock_query)

    rate = await tracker.calculate_usage_rate(1)
    assert rate == pytest.approx(30.0), f"Expected 30.0 calls/min for 30 calls in 1 min, got {rate}"


@pytest.mark.asyncio
async def test_calculate_usage_rate_prometheus_unavailable_returns_zero(monkeypatch):
    """Returns 0.0 honestly when Prometheus is unreachable (returns None)."""
    tracker = _make_tracker()

    async def mock_query(promql: str):
        return None

    _patch_query_instant(monkeypatch, mock_query)

    rate = await tracker.calculate_usage_rate(60)
    assert rate == 0.0, "Must return 0.0 (honest) when Prometheus returns None"


@pytest.mark.asyncio
async def test_calculate_usage_rate_no_query_instant_returns_zero(monkeypatch):
    """Returns 0.0 when _prometheus_query_instant is None (module not importable)."""
    tracker = _make_tracker()
    _patch_query_instant(monkeypatch, None)  # simulate import failure

    rate = await tracker.calculate_usage_rate(60)
    assert rate == 0.0, "Must return 0.0 when query_instant is not available"


@pytest.mark.asyncio
async def test_calculate_usage_rate_empty_result_returns_zero(monkeypatch):
    """Returns 0.0 when Prometheus returns an empty result set."""
    tracker = _make_tracker()

    async def mock_query(promql: str):
        return {"resultType": "vector", "result": []}

    _patch_query_instant(monkeypatch, mock_query)

    rate = await tracker.calculate_usage_rate(60)
    assert rate == 0.0, "Must return 0.0 on empty Prometheus result"


@pytest.mark.asyncio
async def test_calculate_usage_rate_window_zero_returns_total(monkeypatch):
    """window_minutes=0 clamps to 1m PromQL window and returns total count."""
    tracker = _make_tracker()

    async def mock_query(promql: str):
        assert "[1m]" in promql, "window=0 should clamp to [1m]"
        return _prometheus_data(15.0)

    _patch_query_instant(monkeypatch, mock_query)

    result = await tracker.calculate_usage_rate(0)
    # window_minutes == 0 → return total_calls (15.0), not rate
    assert result == pytest.approx(15.0)


# ---------------------------------------------------------------------------
# Dead stubs removed (#10721)
# ---------------------------------------------------------------------------


def test_get_recent_calls_removed():
    """get_recent_calls must not exist — it was a silent-empty dead stub."""
    tracker = _make_tracker()
    assert not hasattr(
        tracker, "get_recent_calls"
    ), "get_recent_calls() was a silent-empty deprecated stub and must be removed (#10721)"


def test_get_tool_usage_stats_removed():
    """get_tool_usage_stats must not exist — it was a silent-empty dead stub."""
    tracker = _make_tracker()
    assert not hasattr(
        tracker, "get_tool_usage_stats"
    ), "get_tool_usage_stats() was a silent-empty deprecated stub and must be removed (#10721)"


def test_calculate_payload_trend_removed():
    """calculate_payload_trend must not exist — depended on the removed deque."""
    tracker = _make_tracker()
    assert not hasattr(
        tracker, "calculate_payload_trend"
    ), "calculate_payload_trend() depended on get_recent_calls() and must be removed (#10721)"


# ---------------------------------------------------------------------------
# AlertManager — honest rate alerts via Prometheus
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alert_manager_fires_critical_on_high_rate(monkeypatch):
    """AlertManager issues a critical alert when Prometheus rate > 50 rpm."""
    tracker = _make_tracker()
    alert_mgr = _make_alert_manager()

    async def mock_query(promql: str):
        return _prometheus_data(55.0)

    _patch_query_instant(monkeypatch, mock_query)

    alerts = await alert_mgr.check_usage_alerts(tracker)
    assert len(alerts) >= 1, "Should fire at least one alert at 55 rpm"
    levels = [a.level for a in alerts]
    assert "critical" in levels, f"Expected critical alert, got levels: {levels}"


@pytest.mark.asyncio
async def test_alert_manager_fires_warning_on_elevated_rate(monkeypatch):
    """AlertManager issues a warning alert when Prometheus rate is 31-50 rpm."""
    tracker = _make_tracker()
    alert_mgr = _make_alert_manager()

    async def mock_query(promql: str):
        return _prometheus_data(35.0)

    _patch_query_instant(monkeypatch, mock_query)

    alerts = await alert_mgr.check_usage_alerts(tracker)
    assert len(alerts) >= 1, "Should fire at least one alert at 35 rpm"
    levels = [a.level for a in alerts]
    assert "warning" in levels, f"Expected warning alert, got levels: {levels}"


@pytest.mark.asyncio
async def test_alert_manager_no_alert_on_low_rate(monkeypatch):
    """AlertManager does not fire when Prometheus shows a low rate."""
    tracker = _make_tracker()
    alert_mgr = _make_alert_manager()

    async def mock_query(promql: str):
        return _prometheus_data(5.0)

    _patch_query_instant(monkeypatch, mock_query)

    alerts = await alert_mgr.check_usage_alerts(tracker)
    assert alerts == [], f"Expected no alerts at 5 rpm, got: {alerts}"


@pytest.mark.asyncio
async def test_alert_manager_no_alert_when_prometheus_down(monkeypatch):
    """AlertManager does not fabricate alerts when Prometheus is unavailable."""
    tracker = _make_tracker()
    alert_mgr = _make_alert_manager()

    _patch_query_instant(monkeypatch, None)  # simulate unreachable

    alerts = await alert_mgr.check_usage_alerts(tracker)
    assert alerts == [], "Must not fire alerts when Prometheus is unreachable"


# ---------------------------------------------------------------------------
# PromQL shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calculate_usage_rate_promql_shape(monkeypatch):
    """calculate_usage_rate must use increase(autobot_claude_api_requests_total[Nm])."""
    tracker = _make_tracker()
    captured = []

    async def mock_query(promql: str):
        captured.append(promql)
        return _prometheus_data(0.0)

    _patch_query_instant(monkeypatch, mock_query)

    await tracker.calculate_usage_rate(30)
    assert captured, "query_instant must be called"
    promql = captured[0]
    assert "increase" in promql, f"Must use increase(), got: {promql}"
    assert "autobot_claude_api_requests_total" in promql, f"Wrong metric name: {promql}"
    assert "[30m]" in promql, f"Window not embedded in query: {promql}"
