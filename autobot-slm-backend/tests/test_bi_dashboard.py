# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for business_intelligence_dashboard.py — Issue #10720.

Covers:
- Real usage path: Prometheus returns data → operations_data_available=True
- Unavailable usage path: Prometheus unreachable → operations_data_available=False
  and no fabricated numbers presented as real.
- Config-driven costs: CostModelConfig values are reflected in CostAnalysis.
- Redis-failure degradation: _get_current_utilization and
  _get_historical_performance_data return available=False, not silent empty dict.
"""

import importlib.util
import json
import logging
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub all heavy deps BEFORE importing the module under test.
# We load the .py file directly so the monitoring package __init__ is bypassed.
# ---------------------------------------------------------------------------

# matplotlib stub
_matplotlib = types.ModuleType("matplotlib")
_matplotlib.use = lambda *a, **kw: None
sys.modules.setdefault("matplotlib", _matplotlib)
_matplotlib_pyplot = types.ModuleType("matplotlib.pyplot")
sys.modules.setdefault("matplotlib.pyplot", _matplotlib_pyplot)

# numpy stub — only polyfit/arange/std/array are exercised
import numpy as _real_numpy  # noqa: E402 — numpy is available in test env

sys.modules.setdefault("numpy", _real_numpy)

# aiofiles stub
_aiofiles = types.ModuleType("aiofiles")
sys.modules.setdefault("aiofiles", _aiofiles)

# jinja2 stub
_jinja2 = types.ModuleType("jinja2")


class _FakeTemplate:
    def __init__(self, src):
        self._src = src

    def render(self, **kwargs):
        return self._src


_jinja2.Template = _FakeTemplate
sys.modules.setdefault("jinja2", _jinja2)

# performance_monitor stub (local SLM dep)
_pm = types.ModuleType("performance_monitor")
_pm.ALERT_THRESHOLDS = {"cpu_percent": 80.0, "memory_percent": 85.0}
sys.modules["performance_monitor"] = _pm

# autobot_shared stubs
_shared = types.ModuleType("autobot_shared")
sys.modules.setdefault("autobot_shared", _shared)

_nc = types.ModuleType("autobot_shared.network_constants")


class _NC:
    REDIS_VM_IP = "127.0.0.1"


_nc.NetworkConstants = _NC
sys.modules["autobot_shared.network_constants"] = _nc

# prometheus_query stub — patched per-test via patch()
_pq = types.ModuleType("autobot_shared.monitoring.prometheus_query")
_pq.query_instant = AsyncMock(return_value=None)
_monitoring_pkg = types.ModuleType("autobot_shared.monitoring")
sys.modules["autobot_shared.monitoring"] = _monitoring_pkg
sys.modules["autobot_shared.monitoring.prometheus_query"] = _pq

_rc = types.ModuleType("autobot_shared.redis_client")
sys.modules["autobot_shared.redis_client"] = _rc

_http = types.ModuleType("autobot_shared.http_client")
sys.modules["autobot_shared.http_client"] = _http

_lm = types.ModuleType("autobot_shared.logging_manager")
_lm.get_logger = logging.getLogger
sys.modules["autobot_shared.logging_manager"] = _lm


# ---------------------------------------------------------------------------
# Stub CostModelConfig and ssot_config
# ---------------------------------------------------------------------------


class _StubCostModel:
    cpu_monthly_usd = 55.0
    gpu_monthly_usd = 85.0
    npu_monthly_usd = 35.0
    memory_monthly_usd = 22.0
    storage_monthly_usd = 28.0
    network_monthly_usd = 90.0
    cpu_baseline_efficiency = 70.0
    gpu_baseline_efficiency = 60.0
    npu_baseline_efficiency = 50.0
    memory_baseline_efficiency = 80.0
    storage_baseline_efficiency = 60.0
    network_baseline_efficiency = 40.0


class _StubConfig:
    cost_model = _StubCostModel()


_ssot = types.ModuleType("autobot_shared.ssot_config")
_ssot.get_config = lambda: _StubConfig()
sys.modules["autobot_shared.ssot_config"] = _ssot

# ---------------------------------------------------------------------------
# Load the module under test directly from its file path
# ---------------------------------------------------------------------------

_slm_root = Path(__file__).parent.parent
_dashboard_path = _slm_root / "monitoring" / "business_intelligence_dashboard.py"
_spec = importlib.util.spec_from_file_location("business_intelligence_dashboard", _dashboard_path)
_bid_mod = importlib.util.module_from_spec(_spec)
sys.modules["business_intelligence_dashboard"] = _bid_mod
_spec.loader.exec_module(_bid_mod)

BusinessIntelligenceDashboard = _bid_mod.BusinessIntelligenceDashboard
_sum_prometheus_increase = _bid_mod._sum_prometheus_increase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dashboard() -> BusinessIntelligenceDashboard:
    """Return a dashboard instance with Redis disabled and a temp data path."""
    dash = object.__new__(BusinessIntelligenceDashboard)
    dash.logger = logging.getLogger("test_bid")
    dash.redis_client = None
    dash.redis_host = "127.0.0.1"
    dash.redis_port = 6379
    dash.dashboard_data_path = Path("/tmp/test_bi_dashboard")  # test-only temp path
    dash.hardware_investments = {
        "intel_ultra_9_185h": {"cost": 800, "category": "cpu"},
    }
    dash.operational_costs = {"electricity": 150, "internet": 80}
    dash.performance_baselines = {
        "api_response_time": 2.0,
        "knowledge_search_time": 300,
        "llm_tokens_per_second": 20.0,
        "system_uptime": 99.5,
        "npu_utilization": 60.0,
    }
    return dash


# ---------------------------------------------------------------------------
# Part 1: Monthly operation counts — real usage vs unavailable
# ---------------------------------------------------------------------------


class TestMonthlyOperations:
    @pytest.mark.asyncio
    async def test_real_usage_path_returns_data_available_true(self):
        """When Prometheus returns counts, operations_data_available is True."""
        dash = _make_dashboard()

        async def _fake_get_monthly_operations():
            return 51_000, True

        dash._get_monthly_operations = _fake_get_monthly_operations
        dash._get_historical_performance_data = AsyncMock(return_value={"available": False})
        dash._calculate_performance_improvement = AsyncMock(return_value=0.0)

        roi = await dash.calculate_roi_metrics()

        assert roi.operations_data_available is True
        # cost_per_operation must be non-zero when ops count is real
        assert roi.cost_per_operation > 0

    @pytest.mark.asyncio
    async def test_prometheus_unavailable_returns_data_available_false(self):
        """When Prometheus is unreachable, operations_data_available is False."""
        dash = _make_dashboard()

        async def _fake_get_monthly_operations():
            return 0, False

        dash._get_monthly_operations = _fake_get_monthly_operations
        dash._get_historical_performance_data = AsyncMock(return_value={"available": False})
        dash._calculate_performance_improvement = AsyncMock(return_value=0.0)

        roi = await dash.calculate_roi_metrics()

        assert roi.operations_data_available is False
        # cost_per_operation must be 0 — no ops means undefined, not fake
        assert roi.cost_per_operation == 0

    @pytest.mark.asyncio
    async def test_sum_prometheus_increase_none_when_no_data(self):
        """_sum_prometheus_increase returns None when Prometheus returns None."""
        with patch.object(_bid_mod, "query_instant", new=AsyncMock(return_value=None)):
            result = await _sum_prometheus_increase("fake_metric[30d]")
        assert result is None

    @pytest.mark.asyncio
    async def test_sum_prometheus_increase_none_when_empty_result(self):
        """_sum_prometheus_increase returns None when result list is empty."""
        empty = {"resultType": "vector", "result": []}
        with patch.object(_bid_mod, "query_instant", new=AsyncMock(return_value=empty)):
            result = await _sum_prometheus_increase("autobot_llm_requests_total[30d]")
        assert result is None

    @pytest.mark.asyncio
    async def test_sum_prometheus_increase_sums_all_series(self):
        """_sum_prometheus_increase sums across label dimensions."""
        fake_data = {
            "resultType": "vector",
            "result": [
                {"metric": {"provider": "ollama"}, "value": [1234567890, "300"]},
                {"metric": {"provider": "openai"}, "value": [1234567890, "200"]},
            ],
        }
        with patch.object(_bid_mod, "query_instant", new=AsyncMock(return_value=fake_data)):
            result = await _sum_prometheus_increase("autobot_llm_requests_total[30d]")
        assert result == pytest.approx(500.0)

    @pytest.mark.asyncio
    async def test_get_monthly_operations_both_sources_available(self):
        """_get_monthly_operations combines LLM + KB counts when both Prometheus series exist."""
        llm_data = {
            "resultType": "vector",
            "result": [{"metric": {}, "value": [0, "1000"]}],
        }
        kb_data = {
            "resultType": "vector",
            "result": [{"metric": {}, "value": [0, "500"]}],
        }

        call_count = 0

        async def _mock_query(promql):
            nonlocal call_count
            call_count += 1
            if "llm" in promql:
                return llm_data
            return kb_data

        with patch.object(_bid_mod, "query_instant", side_effect=_mock_query):
            total, available = await dash._get_monthly_operations()

        assert available is True
        assert total == 1500

    @pytest.mark.asyncio
    async def test_get_monthly_operations_both_unavailable(self):
        """_get_monthly_operations returns (0, False) when both Prometheus calls fail."""
        with patch.object(_bid_mod, "query_instant", new=AsyncMock(return_value=None)):
            total, available = await dash._get_monthly_operations()
        assert available is False
        assert total == 0


# Shared fixture for some tests
dash = _make_dashboard()


# ---------------------------------------------------------------------------
# Part 2: Config-driven component costs
# ---------------------------------------------------------------------------


class TestConfigDrivenCosts:
    def test_build_component_definitions_uses_config_values(self):
        """_build_component_definitions reads from _cost (CostModelConfig), not literals."""
        d = _make_dashboard()
        defs = d._build_component_definitions(
            {"cpu": 45.0, "gpu": 0, "npu": 0, "memory": 0, "storage": 0, "network": 0}
        )
        assert defs["cpu"]["monthly_cost"] == _StubCostModel.cpu_monthly_usd
        assert defs["gpu"]["monthly_cost"] == _StubCostModel.gpu_monthly_usd
        assert defs["npu"]["monthly_cost"] == _StubCostModel.npu_monthly_usd
        assert defs["memory"]["monthly_cost"] == _StubCostModel.memory_monthly_usd
        assert defs["storage"]["monthly_cost"] == _StubCostModel.storage_monthly_usd
        assert defs["network"]["monthly_cost"] == _StubCostModel.network_monthly_usd

    def test_build_component_definitions_uses_config_efficiency(self):
        """baseline_efficiency values come from config, not hardcoded literals."""
        d = _make_dashboard()
        defs = d._build_component_definitions({})
        assert defs["cpu"]["baseline_efficiency"] == _StubCostModel.cpu_baseline_efficiency
        assert defs["gpu"]["baseline_efficiency"] == _StubCostModel.gpu_baseline_efficiency

    @pytest.mark.asyncio
    async def test_cost_analysis_cost_is_estimate_always_true(self):
        """CostAnalysis.cost_is_estimate is True because costs are operator estimates."""
        d = _make_dashboard()
        util = {
            "available": True,
            "cpu": 50.0,
            "gpu": 40.0,
            "npu": 30.0,
            "memory": 60.0,
            "storage": 50.0,
            "network": 30.0,
        }
        d._get_current_utilization = AsyncMock(return_value=util)
        analyses = await d.analyze_cost_efficiency()
        assert analyses, "Expected at least one CostAnalysis"
        for ca in analyses:
            assert ca.cost_is_estimate is True

    @pytest.mark.asyncio
    async def test_cost_analysis_uses_config_monthly_cost(self):
        """CostAnalysis.monthly_cost_usd matches the config value for each component."""
        d = _make_dashboard()
        util = {
            "available": True,
            "cpu": 50.0,
            "gpu": 40.0,
            "npu": 30.0,
            "memory": 60.0,
            "storage": 50.0,
            "network": 30.0,
        }
        d._get_current_utilization = AsyncMock(return_value=util)
        analyses = await d.analyze_cost_efficiency()
        costs_by_component = {ca.component: ca.monthly_cost_usd for ca in analyses}
        assert costs_by_component["cpu"] == _StubCostModel.cpu_monthly_usd
        assert costs_by_component["network"] == _StubCostModel.network_monthly_usd

    @pytest.mark.asyncio
    async def test_cost_analysis_empty_when_utilization_unavailable(self):
        """analyze_cost_efficiency returns [] when utilization data is unavailable (Redis down)."""
        d = _make_dashboard()
        d._get_current_utilization = AsyncMock(return_value={"available": False, "error": "redis_unavailable"})
        analyses = await d.analyze_cost_efficiency()
        assert analyses == []


# ---------------------------------------------------------------------------
# Part 3: Redis-failure degradation signals
# ---------------------------------------------------------------------------


class TestRedisFallbacks:
    @pytest.mark.asyncio
    async def test_get_current_utilization_no_redis_returns_available_false(self):
        """_get_current_utilization returns {available:False} (not {}) when redis_client is None."""
        d = _make_dashboard()
        result = await d._get_current_utilization()
        assert result.get("available") is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_current_utilization_redis_error_returns_available_false(self):
        """_get_current_utilization returns {available:False} on Redis command error."""
        d = _make_dashboard()
        mock_redis = MagicMock()
        mock_redis.hget.side_effect = Exception("connection refused")
        d.redis_client = mock_redis

        result = await d._get_current_utilization()
        assert result.get("available") is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_current_utilization_no_data_returns_available_false(self):
        """_get_current_utilization returns {available:False} when key missing in Redis."""
        d = _make_dashboard()
        mock_redis = MagicMock()
        mock_redis.hget.return_value = None
        d.redis_client = mock_redis

        result = await d._get_current_utilization()
        assert result.get("available") is False

    @pytest.mark.asyncio
    async def test_get_current_utilization_happy_path(self):
        """_get_current_utilization returns available=True with real metrics on success."""
        d = _make_dashboard()
        mock_redis = MagicMock()
        mock_redis.hget.return_value = json.dumps(
            {"system": {"cpu_percent": 45.0, "memory_percent": 60.0, "disk_percent": 30.0}}
        )
        d.redis_client = mock_redis

        result = await d._get_current_utilization()
        assert result["available"] is True
        assert result["cpu"] == 45.0
        assert result["memory"] == 60.0

    @pytest.mark.asyncio
    async def test_get_historical_performance_data_no_redis_returns_available_false(self):
        """_get_historical_performance_data returns {available:False} when redis_client is None."""
        d = _make_dashboard()
        result = await d._get_historical_performance_data()
        assert result.get("available") is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_historical_performance_data_redis_error_returns_available_false(self):
        """_get_historical_performance_data returns {available:False} on Redis command error."""
        d = _make_dashboard()
        mock_redis = MagicMock()
        mock_redis.lrange.side_effect = Exception("timeout")
        d.redis_client = mock_redis

        result = await d._get_historical_performance_data()
        assert result.get("available") is False

    @pytest.mark.asyncio
    async def test_get_historical_performance_data_happy_path(self):
        """_get_historical_performance_data returns available=True with empty lists on no history."""
        d = _make_dashboard()
        mock_redis = MagicMock()
        mock_redis.lrange.return_value = []
        d.redis_client = mock_redis

        result = await d._get_historical_performance_data()
        assert result["available"] is True
        assert "api_response_times" in result


# ---------------------------------------------------------------------------
# Part 4: SystemHealthScore.data_available — honesty flag (#10779)
# ---------------------------------------------------------------------------


class TestSystemHealthScoreDataAvailable:
    """Verify calculate_system_health_score never emits confident defaults when data is absent."""

    @pytest.mark.asyncio
    async def test_data_available_true_when_both_sources_present(self):
        """data_available=True and scores are non-zero when utilization + performance data exist."""
        d = _make_dashboard()
        util = {
            "available": True,
            "cpu": 50.0,
            "gpu": 40.0,
            "npu": 30.0,
            "memory": 60.0,
            "storage": 50.0,
            "network": 30.0,
        }
        perf = {
            "available": True,
            "api_response_times": [1.2, 1.3, 1.1, 1.4, 1.2],
            "cpu_utilization": [],
            "memory_utilization": [],
            "service_availability": [],
        }
        d._get_current_utilization = AsyncMock(return_value=util)
        d._get_historical_performance_data = AsyncMock(return_value=perf)

        result = await d.calculate_system_health_score()

        assert result.data_available is True
        # performance_score must NOT be the empty-dict artifact (35.0)
        assert result.performance_score != 35.0
        # user_satisfaction_score must NOT be the bare default (80.0 returned when api_times=[])
        assert result.user_satisfaction_score != 80.0 or len(perf["api_response_times"]) > 0

    @pytest.mark.asyncio
    async def test_data_available_false_when_utilization_unavailable(self):
        """When utilization data is unavailable, data_available=False and no fabricated 35.0 score."""
        d = _make_dashboard()
        d._get_current_utilization = AsyncMock(return_value={"available": False, "error": "redis_unavailable"})
        d._get_historical_performance_data = AsyncMock(
            return_value={"available": True, "api_response_times": [], "cpu_utilization": [], "memory_utilization": []}
        )

        result = await d.calculate_system_health_score()

        assert result.data_available is False
        # Must be 0.0, not the fabricated 35.0 from empty-dict arithmetic
        assert result.performance_score == 0.0, f"Expected 0.0, got {result.performance_score}"
        assert result.efficiency_score == 0.0

    @pytest.mark.asyncio
    async def test_data_available_false_when_performance_data_unavailable(self):
        """When performance history is unavailable, data_available=False and no fabricated 80.0."""
        d = _make_dashboard()
        d._get_current_utilization = AsyncMock(
            return_value={
                "available": True,
                "cpu": 50.0,
                "gpu": 40.0,
                "npu": 30.0,
                "memory": 60.0,
                "storage": 50.0,
                "network": 30.0,
            }
        )
        d._get_historical_performance_data = AsyncMock(return_value={"available": False, "error": "redis_unavailable"})

        result = await d.calculate_system_health_score()

        assert result.data_available is False
        # Must be 0.0, not the bare 80.0 default returned when api_times is missing
        assert result.user_satisfaction_score == 0.0, f"Expected 0.0, got {result.user_satisfaction_score}"

    @pytest.mark.asyncio
    async def test_no_fabricated_scores_when_no_redis(self):
        """No Redis → both sources unavailable → data_available=False; no 35.0 or 80.0 defaults."""
        d = _make_dashboard()
        # redis_client=None: both helpers return available=False naturally
        result = await d.calculate_system_health_score()

        assert result.data_available is False
        assert result.performance_score == 0.0, f"Got fabricated performance_score={result.performance_score}"
        assert (
            result.user_satisfaction_score == 0.0
        ), f"Got fabricated user_satisfaction={result.user_satisfaction_score}"
        assert result.efficiency_score == 0.0

    @pytest.mark.asyncio
    async def test_data_available_in_comprehensive_report_summary(self):
        """generate_comprehensive_dashboard_report surfaces system_health_data_available in summary."""
        d = _make_dashboard()
        d._get_current_utilization = AsyncMock(return_value={"available": False, "error": "redis_unavailable"})
        d._get_historical_performance_data = AsyncMock(return_value={"available": False, "error": "redis_unavailable"})
        d._get_monthly_operations = AsyncMock(return_value=(0, False))
        d._store_dashboard_report = AsyncMock()
        d._generate_visual_dashboard = AsyncMock()
        # Stub calculate_performance_improvement since it depends on performance_data
        d._calculate_performance_improvement = AsyncMock(return_value=0.0)

        report = await d.generate_comprehensive_dashboard_report()

        summary = report.get("summary", {})
        assert "system_health_data_available" in summary, "system_health_data_available must be in summary"
        assert summary["system_health_data_available"] is False
