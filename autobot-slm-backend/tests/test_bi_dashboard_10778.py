# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for Issue #10778 additions to business_intelligence_dashboard.py.

Covers:
- _get_monthly_operations now sums LLM + KB + API request counts.
- All three Prometheus queries unavailable → (0, False).
- Only one source available → data_available=True.
- _get_network_utilization_percent returns real % when capacity is configured.
- _get_network_utilization_percent returns None when capacity is 0 (unknown).
- _get_current_utilization network field uses real value, not hardcoded 30.0.
"""

import importlib.util
import logging
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub heavy deps BEFORE importing the module under test.
# Mirrors the approach in test_bi_dashboard.py.
# ---------------------------------------------------------------------------

_matplotlib = types.ModuleType("matplotlib")
_matplotlib.use = lambda *a, **kw: None
sys.modules.setdefault("matplotlib", _matplotlib)
_matplotlib_pyplot = types.ModuleType("matplotlib.pyplot")
sys.modules.setdefault("matplotlib.pyplot", _matplotlib_pyplot)

import numpy as _real_numpy  # noqa: E402

sys.modules.setdefault("numpy", _real_numpy)

_aiofiles = types.ModuleType("aiofiles")
sys.modules.setdefault("aiofiles", _aiofiles)

_jinja2 = types.ModuleType("jinja2")


class _FakeTemplate:
    def __init__(self, src):
        self._src = src

    def render(self, **kwargs):
        return self._src


_jinja2.Template = _FakeTemplate
sys.modules.setdefault("jinja2", _jinja2)

_pm = types.ModuleType("performance_monitor")
_pm.ALERT_THRESHOLDS = {"cpu_percent": 80.0, "memory_percent": 85.0}
sys.modules["performance_monitor"] = _pm

# psutil stub — net_io_counters used in _sample_net_bytes_per_sec
_psutil = types.ModuleType("psutil")


class _FakeNetIO:
    def __init__(self, bytes_sent=0, bytes_recv=0):
        self.bytes_sent = bytes_sent
        self.bytes_recv = bytes_recv


_psutil.net_io_counters = lambda: _FakeNetIO(bytes_sent=5_000_000, bytes_recv=3_000_000)
sys.modules.setdefault("psutil", _psutil)

# autobot_shared stubs
_shared = types.ModuleType("autobot_shared")
sys.modules.setdefault("autobot_shared", _shared)

_nc = types.ModuleType("autobot_shared.network_constants")


class _NC:
    REDIS_VM_IP = "127.0.0.1"


_nc.NetworkConstants = _NC
sys.modules["autobot_shared.network_constants"] = _nc

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
# Stub CostModelConfig with both old and new (#10778) fields.
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
    # Issue #10778: link capacity for real utilisation %
    network_link_capacity_mbps = 0.0  # default = unknown


class _StubConfig:
    cost_model = _StubCostModel()


_ssot = types.ModuleType("autobot_shared.ssot_config")
_ssot.get_config = lambda: _StubConfig()
sys.modules["autobot_shared.ssot_config"] = _ssot

# ---------------------------------------------------------------------------
# Load the module under test
# ---------------------------------------------------------------------------

_slm_root = Path(__file__).parent.parent
_dashboard_path = _slm_root / "monitoring" / "business_intelligence_dashboard.py"
_spec = importlib.util.spec_from_file_location("business_intelligence_dashboard", _dashboard_path)
_bid_mod = importlib.util.module_from_spec(_spec)
sys.modules["business_intelligence_dashboard"] = _bid_mod
_spec.loader.exec_module(_bid_mod)

BusinessIntelligenceDashboard = _bid_mod.BusinessIntelligenceDashboard
_sum_prometheus_increase = _bid_mod._sum_prometheus_increase
_get_network_utilization_percent = _bid_mod._get_network_utilization_percent
_sample_net_bytes_per_sec = _bid_mod._sample_net_bytes_per_sec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dashboard() -> BusinessIntelligenceDashboard:
    dash = object.__new__(BusinessIntelligenceDashboard)
    dash.logger = logging.getLogger("test_bid_10778")
    dash.redis_client = None
    dash.redis_host = "127.0.0.1"
    dash.redis_port = 6379
    dash.dashboard_data_path = Path("/tmp/test_bi_dashboard_10778")
    dash.hardware_investments = {"intel_ultra_9_185h": {"cost": 800, "category": "cpu"}}
    dash.operational_costs = {"electricity": 150, "internet": 80}
    dash.performance_baselines = {
        "api_response_time": 2.0,
        "knowledge_search_time": 300,
        "llm_tokens_per_second": 20.0,
        "system_uptime": 99.5,
        "npu_utilization": 60.0,
    }
    return dash


def _promql_vector(value: str):
    return {"resultType": "vector", "result": [{"metric": {}, "value": [0, value]}]}


# ---------------------------------------------------------------------------
# Part A: _get_monthly_operations includes API requests (#10778)
# ---------------------------------------------------------------------------


class TestMonthlyOperationsApiRequests:
    @pytest.mark.asyncio
    async def test_all_three_sources_summed(self):
        """LLM + KB + API request counts are all added together."""
        dash = _make_dashboard()
        llm_data = _promql_vector("1000")
        kb_data = _promql_vector("500")
        api_data = _promql_vector("2500")

        call_order = []

        async def _mock_query(promql):
            call_order.append(promql)
            if "llm" in promql:
                return llm_data
            if "knowledge" in promql:
                return kb_data
            if "api_requests" in promql:
                return api_data
            return None

        with patch.object(_bid_mod, "query_instant", side_effect=_mock_query):
            total, available = await dash._get_monthly_operations()

        assert available is True
        assert total == 4000  # 1000 + 500 + 2500

    @pytest.mark.asyncio
    async def test_only_api_requests_available(self):
        """data_available=True and correct total when only api_requests returns data."""
        dash = _make_dashboard()
        api_data = _promql_vector("3000")

        async def _mock_query(promql):
            if "api_requests" in promql:
                return api_data
            return None

        with patch.object(_bid_mod, "query_instant", side_effect=_mock_query):
            total, available = await dash._get_monthly_operations()

        assert available is True
        assert total == 3000

    @pytest.mark.asyncio
    async def test_all_three_unavailable_returns_false(self):
        """(0, False) returned when all three Prometheus queries fail."""
        dash = _make_dashboard()

        with patch.object(_bid_mod, "query_instant", AsyncMock(return_value=None)):
            total, available = await dash._get_monthly_operations()

        assert available is False
        assert total == 0

    @pytest.mark.asyncio
    async def test_llm_and_kb_available_api_missing(self):
        """LLM + KB count correctly when api_requests is unavailable."""
        dash = _make_dashboard()

        async def _mock_query(promql):
            if "llm" in promql:
                return _promql_vector("700")
            if "knowledge" in promql:
                return _promql_vector("300")
            return None  # api_requests fails

        with patch.object(_bid_mod, "query_instant", side_effect=_mock_query):
            total, available = await dash._get_monthly_operations()

        assert available is True
        assert total == 1000


# ---------------------------------------------------------------------------
# Part B: network utilisation — _get_network_utilization_percent
# ---------------------------------------------------------------------------


class TestNetworkUtilizationPercent:
    @pytest.mark.asyncio
    async def test_returns_none_when_capacity_is_zero(self):
        """Returns None when network_link_capacity_mbps == 0 (default, unknown)."""
        _bid_mod._cfg.cost_model.network_link_capacity_mbps = 0.0
        result = await _get_network_utilization_percent()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_percent_when_capacity_configured(self):
        """Returns a float in [0, 100] when capacity is configured."""
        # psutil stub returns 5MB + 3MB = 8MB bytes total; split across 0.25s window
        # _sample_net_bytes_per_sec will return 8 000 000 / 0.25 = 32 000 000 B/s
        # With 1000 Mbit/s capacity = 125 000 000 B/s → ~25.6%
        _bid_mod._cfg.cost_model.network_link_capacity_mbps = 1000.0

        with patch.object(_bid_mod, "_sample_net_bytes_per_sec", return_value=32_000_000.0):
            result = await _get_network_utilization_percent()

        assert result is not None
        assert 0.0 <= result <= 100.0
        assert abs(result - 25.6) < 1.0

    @pytest.mark.asyncio
    async def test_caps_at_100_percent(self):
        """Utilisation is capped at 100% even when throughput exceeds capacity."""
        _bid_mod._cfg.cost_model.network_link_capacity_mbps = 10.0  # 10 Mbit/s

        # 200 MB/s far exceeds 10 Mbit/s capacity
        with patch.object(_bid_mod, "_sample_net_bytes_per_sec", return_value=200_000_000.0):
            result = await _get_network_utilization_percent()

        assert result == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_get_current_utilization_network_not_hardcoded(self):
        """_get_current_utilization.network is derived from psutil, not the old 30.0."""
        import json

        dash = _make_dashboard()
        mock_redis = MagicMock()
        mock_redis.hget.return_value = json.dumps(
            {"system": {"cpu_percent": 40.0, "memory_percent": 55.0, "disk_percent": 20.0}}
        )
        dash.redis_client = mock_redis

        _bid_mod._cfg.cost_model.network_link_capacity_mbps = 1000.0

        with patch.object(_bid_mod, "_sample_net_bytes_per_sec", return_value=12_500_000.0):
            result = await dash._get_current_utilization()

        assert result["available"] is True
        # 12.5 MB/s / 125 MB/s (1 Gbit) = 10%
        assert abs(result["network"] - 10.0) < 1.0
        # Critically, must not be the old hardcoded 30.0
        assert result["network"] != 30.0

    @pytest.mark.asyncio
    async def test_get_current_utilization_network_zero_when_capacity_unknown(self):
        """network field is 0.0 (not 30.0) when link capacity is not configured."""
        import json

        dash = _make_dashboard()
        mock_redis = MagicMock()
        mock_redis.hget.return_value = json.dumps({"system": {"cpu_percent": 40.0}})
        dash.redis_client = mock_redis

        _bid_mod._cfg.cost_model.network_link_capacity_mbps = 0.0

        result = await dash._get_current_utilization()

        assert result["available"] is True
        assert result["network"] == 0.0  # honest: capacity unknown
        assert result["network"] != 30.0  # not the old fabricated value


# ---------------------------------------------------------------------------
# Part B: _sample_net_bytes_per_sec is synchronous (runs in to_thread)
# ---------------------------------------------------------------------------


class TestSampleNetBytesPerSec:
    def test_returns_positive_float(self):
        """_sample_net_bytes_per_sec returns a non-negative float.

        Uses the psutil stub that simulates stable counters (same value before
        and after), so the result is 0 bytes/s — still a valid non-negative float.
        """

        class _StaticNetIO:
            def __init__(self):
                self.bytes_sent = 10_000_000
                self.bytes_recv = 5_000_000

        with patch.object(_bid_mod.psutil, "net_io_counters", return_value=_StaticNetIO()):
            result = _sample_net_bytes_per_sec()

        assert isinstance(result, float)
        assert result >= 0.0

    def test_returns_rate_for_increasing_counters(self):
        """_sample_net_bytes_per_sec computes delta correctly for growing counters."""
        calls = [0]

        class _GrowingNetIO:
            _samples = [
                type("IO", (), {"bytes_sent": 0, "bytes_recv": 0})(),
                type(
                    "IO",
                    (),
                    {
                        "bytes_sent": int(32_000_000 * _bid_mod._NET_SAMPLE_INTERVAL_S),
                        "bytes_recv": 0,
                    },
                )(),
            ]

            def __init__(self):
                self._val = _GrowingNetIO._samples[calls[0] % 2]
                calls[0] += 1
                self.bytes_sent = self._val.bytes_sent
                self.bytes_recv = self._val.bytes_recv

        side_effects = iter(
            [
                type("IO", (), {"bytes_sent": 0, "bytes_recv": 0})(),
                type(
                    "IO",
                    (),
                    {
                        "bytes_sent": int(32_000_000 * _bid_mod._NET_SAMPLE_INTERVAL_S),
                        "bytes_recv": 0,
                    },
                )(),
            ]
        )

        with patch.object(_bid_mod.psutil, "net_io_counters", side_effect=side_effects):
            result = _sample_net_bytes_per_sec()

        assert abs(result - 32_000_000.0) < 1.0
