#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
AutoBot Business Intelligence Dashboard
Advanced analytics, ROI tracking, and performance insights for the distributed system.

Issue #10720: Replaced fabricated usage constants and hardcoded component costs with:
- Real usage counts sourced from Prometheus (autobot_llm_requests_total,
  autobot_knowledge_search_requests_total) via query_instant(); explicit
  "unavailable" signal returned when Prometheus is unreachable.
- Config-driven component cost model (CostModelConfig in ssot_config.py) so
  operators supply deployment-specific values without editing source code.
- Redis-failure paths now return a degradation-shaped dict (available=False +
  error key) instead of an indistinguishable empty dict.
"""

import asyncio
import json
import logging
import os
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
import matplotlib
import psutil

matplotlib.use("Agg")  # Non-interactive backend
import numpy as np
from jinja2 import Template
from performance_monitor import ALERT_THRESHOLDS

from autobot_shared.monitoring.prometheus_query import query_instant
from autobot_shared.network_constants import NetworkConstants
from autobot_shared.ssot_config import get_config

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for numeric type checks
_NUMERIC_TYPES = (int, float)

# Sentinel – returned by helpers when data is not available (Redis down, etc.)
# Callers check for the ``available`` key being False before consuming data.
_UNAVAILABLE: Dict[str, Any] = {"available": False}

_cfg = get_config()
_cost = _cfg.cost_model  # CostModelConfig — operator-supplied, env-overridable

# HTML template for visual dashboard
_DASHBOARD_HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>AutoBot Business Intelligence Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .dashboard { max-width: 1200px; margin: 0 auto; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
        .metrics-grid { display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px; margin-bottom: 20px; }
        .metric-card { background: white; padding: 20px; border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .metric-title { font-size: 14px; color: #666; margin-bottom: 10px; }
        .metric-value { font-size: 24px; font-weight: bold; color: #333; }
        .health-score { font-size: 36px; font-weight: bold; color: {{ health_color }}; }
        .improvement-area { background: #fff3cd; padding: 5px 10px; margin: 5px 0;
            border-radius: 5px; border-left: 4px solid #ffc107; }
        .roi-positive { color: #28a745; }
        .roi-negative { color: #dc3545; }
        .chart-placeholder { height: 200px; background: #e9ecef; border-radius: 5px;
            display: flex; align-items: center; justify-content: center; color: #6c757d; }
        .timestamp { font-size: 12px; color: #999; }
    </style>
</head>
<body>
    <div class="dashboard">
        <div class="header">
            <h1>AutoBot Business Intelligence Dashboard</h1>
            <p>Distributed System Performance &amp; ROI Analytics</p>
            <p class="timestamp">Generated: {{ timestamp }}</p>
        </div>

        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-title">Overall System Health</div>
                {% if health_data_available %}
                <div class="health-score">{{ health_score }}/100</div>
                {% else %}
                <div class="health-score" style="font-size:16px;color:#999">
                Unavailable — backend metrics not yet collected</div>
                {% endif %}
            </div>

            <div class="metric-card">
                <div class="metric-title">Total ROI</div>
                <div class="metric-value {{ roi_class }}">{{ roi_percent }}%</div>
            </div>

            <div class="metric-card">
                <div class="metric-title">Break Even Period</div>
                <div class="metric-value">{{ break_even_months }} months</div>
            </div>

            <div class="metric-card">
                <div class="metric-title">Monthly Operational Cost</div>
                <div class="metric-value">${{ monthly_cost }}</div>
            </div>

            <div class="metric-card">
                <div class="metric-title">Optimization Potential</div>
                <div class="metric-value">${{ optimization_potential }}/month</div>
            </div>

            <div class="metric-card">
                <div class="metric-title">Hardware Investment</div>
                <div class="metric-value">${{ hardware_investment }}</div>
            </div>
        </div>

        <div class="metrics-grid">
            <div class="metric-card">
                <h3>System Health Breakdown</h3>
                {% if not health_data_available %}
                <p style="color:#999;font-style:italic">Performance, efficiency and
                satisfaction scores unavailable (Redis metrics not yet collected)</p>
                {% endif %}
                <p>Availability: {{ availability_score }}/100</p>
                <p>Performance: {{ performance_score }}/100
                {% if not health_data_available %} (unavailable){% endif %}</p>
                <p>Security: {{ security_score }}/100</p>
                <p>Efficiency: {{ efficiency_score }}/100
                {% if not health_data_available %} (unavailable){% endif %}</p>
                <p>User Satisfaction: {{ user_satisfaction_score }}/100
                {% if not health_data_available %} (unavailable){% endif %}</p>
            </div>

            <div class="metric-card">
                <h3>Cost Efficiency Analysis</h3>
                {% for cost in cost_analysis %}
                <p>{{ cost.component }}: {{ cost.efficiency_score }}% efficient
                    {% if cost.cost_is_estimate %}(estimated cost){% endif %}</p>
                {% endfor %}
            </div>

            <div class="metric-card">
                <h3>Performance Predictions</h3>
                {% for pred in predictions %}
                <p>{{ pred.metric_name }}: {{ pred.trend_direction }}</p>
                {% endfor %}
            </div>
        </div>

        {% if improvement_areas %}
        <div class="metric-card">
            <h3>Improvement Areas</h3>
            {% for area in improvement_areas %}
            <div class="improvement-area">{{ area }}</div>
            {% endfor %}
        </div>
        {% endif %}
    </div>
</body>
</html>
"""


@dataclass
class ROIMetrics:
    """Return on Investment metrics for hardware and infrastructure."""

    timestamp: str
    hardware_investment_usd: float
    operational_cost_monthly_usd: float
    performance_improvement_percent: float
    cost_per_operation: float
    productivity_gain_hours_per_month: float
    break_even_months: float
    total_roi_percent: float
    # True when monthly_operations came from a real source; False = Prometheus unavailable
    operations_data_available: bool


@dataclass
class CostAnalysis:
    """Cost analysis for different system components."""

    timestamp: str
    component: str
    monthly_cost_usd: float
    utilization_percent: float
    cost_per_hour: float
    efficiency_score: float
    optimization_potential_usd: float
    # False when cost came from config defaults (estimates); True if operator-overridden
    cost_is_estimate: bool


@dataclass
class PerformancePrediction:
    """Predictive performance insights."""

    timestamp: str
    metric_name: str
    current_value: float
    predicted_7d: float
    predicted_30d: float
    trend_direction: str  # increasing, decreasing, stable
    confidence_percent: float
    recommended_action: str


@dataclass
class SystemHealthScore:
    """Overall system health scoring."""

    timestamp: str
    overall_score: float  # 0-100
    availability_score: float
    performance_score: float
    security_score: float
    efficiency_score: float
    user_satisfaction_score: float
    improvement_areas: List[str]
    # True when both utilization and historical performance sources returned real data.
    # False when Redis was unavailable; consumers must show "unavailable" instead of
    # presenting the zeroed sub-scores as if they were measured values (#10779).
    data_available: bool


# ---------------------------------------------------------------------------
# Prometheus usage helpers
# ---------------------------------------------------------------------------

# PromQL: 30-day increase in total LLM requests (all providers/models)
_PROMQL_LLM_REQUESTS_30D = "increase(autobot_llm_requests_total[30d])"
# PromQL: 30-day increase in knowledge-base search requests (all types/collections)
_PROMQL_KB_SEARCHES_30D = "increase(autobot_knowledge_search_requests_total[30d])"
# PromQL: 30-day increase in generic HTTP API requests (Issue #10778)
_PROMQL_API_REQUESTS_30D = "increase(autobot_api_requests_total[30d])"


async def _sum_prometheus_increase(promql: str) -> Optional[float]:
    """Return the sum of all series for a 30-day increase PromQL expression.

    Returns None when Prometheus is unreachable or returns no data.
    """
    data = await query_instant(promql)
    if not data:
        return None
    results = data.get("result", [])
    if not results:
        return None
    try:
        return sum(float(r["value"][1]) for r in results if len(r.get("value", [])) == 2)
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("Could not parse Prometheus result for %r: %s", promql, exc)
        return None


# ---------------------------------------------------------------------------
# Network utilisation helpers (Issue #10778)
# ---------------------------------------------------------------------------

# Short delta interval for the two psutil samples (seconds).
# 0.25 s is short enough not to block the event loop noticeably yet long
# enough to produce stable byte counts on modern NICs.
_NET_SAMPLE_INTERVAL_S: float = 0.25


def _sample_net_bytes_per_sec() -> float:
    """Return total network throughput in bytes/s across all interfaces.

    Runs two ``psutil.net_io_counters()`` samples separated by
    ``_NET_SAMPLE_INTERVAL_S`` seconds (blocking).  Must be called via
    ``asyncio.to_thread`` from async code.
    """
    import time  # noqa: PLC0415 — stdlib, imported here to keep module-level imports clean

    before = psutil.net_io_counters()
    time.sleep(_NET_SAMPLE_INTERVAL_S)
    after = psutil.net_io_counters()
    delta_bytes = (after.bytes_sent + after.bytes_recv) - (before.bytes_sent + before.bytes_recv)
    return max(delta_bytes / _NET_SAMPLE_INTERVAL_S, 0.0)


async def _get_network_utilization_percent() -> Optional[float]:
    """Return network utilisation as a percentage of configured link capacity.

    Uses ``asyncio.to_thread`` so the blocking psutil sampling does not stall
    the event loop.

    Returns:
        A float in [0, 100] when ``AUTOBOT_COST_NETWORK_LINK_CAPACITY_MBPS``
        is configured and > 0.  Returns None when capacity is unknown — callers
        must treat None as "unavailable" and must not fabricate a number.
    """
    capacity_mbps = _cfg.cost_model.network_link_capacity_mbps
    if capacity_mbps <= 0:
        return None  # capacity unknown; refuse to fabricate a percentage

    bytes_per_sec = await asyncio.to_thread(_sample_net_bytes_per_sec)
    capacity_bytes_per_sec = capacity_mbps * 125_000  # 1 Mbit/s = 125 000 B/s
    return min(bytes_per_sec / capacity_bytes_per_sec * 100.0, 100.0)


class BusinessIntelligenceDashboard:
    """Business Intelligence and Analytics Dashboard for AutoBot."""

    def __init__(self, redis_host: str = NetworkConstants.REDIS_VM_IP, redis_port: int = 6379):
        self.logger = logging.getLogger(__name__)
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_client = None
        _base = os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot")
        self.dashboard_data_path = Path(_base) / "reports" / "performance"
        self.dashboard_data_path.mkdir(parents=True, exist_ok=True)

        # Hardware investment tracking
        self.hardware_investments = {
            "intel_ultra_9_185h": {"cost": 800, "category": "cpu"},
            "nvidia_rtx_4070": {"cost": 700, "category": "gpu"},
            "intel_ai_boost_npu": {"cost": 200, "category": "npu"},  # Estimated
            "memory_64gb": {"cost": 400, "category": "memory"},
            "nvme_storage_2tb": {"cost": 300, "category": "storage"},
            "vm_infrastructure": {"cost": 200, "category": "virtualization"},
        }

        # Operational costs (monthly)
        self.operational_costs = {
            "electricity": 150,  # Estimated for high-performance system
            "internet": 80,
            "software_licenses": 50,
            "maintenance": 100,
        }

        # Performance baselines
        self.performance_baselines = {
            "api_response_time": 2.0,  # seconds
            "knowledge_search_time": 300,  # ms
            "llm_tokens_per_second": 20.0,
            "system_uptime": 99.5,  # percent
            "npu_utilization": 60.0,  # percent
        }

    async def initialize_redis_connection(self):
        """Initialize Redis connection for BI metrics using canonical utility."""
        try:
            # Use canonical Redis utility following CLAUDE.md "REDIS CLIENT USAGE" policy
            from autobot_shared.redis_client import get_redis_client

            self.redis_client = get_redis_client(database="metrics")
            if self.redis_client is None:
                raise Exception("Redis client initialization returned None")

            self.redis_client.ping()
            self.logger.info("Redis connection established for BI Dashboard")
        except Exception as e:
            self.logger.error("Failed to connect to Redis for BI: %s", e)
            self.redis_client = None

    def _compute_savings_and_roi(
        self,
        total_hardware_cost: float,
        monthly_operational_cost: float,
        productivity_gain_hours: float,
    ) -> tuple:
        """Compute break-even months and total ROI percentage.

        Helper for calculate_roi_metrics. Ref: #1088.

        Returns:
            Tuple of (break_even_months, total_roi_percent).
        """
        monthly_savings = productivity_gain_hours * 50  # $50/hour value
        break_even_months = total_hardware_cost / monthly_savings if monthly_savings > 0 else float("inf")
        annual_savings = monthly_savings * 12
        total_roi = (
            (annual_savings - monthly_operational_cost * 12) / total_hardware_cost * 100
            if total_hardware_cost > 0
            else 0
        )
        return break_even_months, total_roi

    async def _get_monthly_operations(self) -> tuple:
        """Query real 30-day operation counts from Prometheus.

        Sources (all queried in parallel; any available source contributes):
        - autobot_llm_requests_total        — LLM inference requests
        - autobot_knowledge_search_requests_total — knowledge-base searches
        - autobot_api_requests_total        — generic HTTP API requests (#10778)

        Returns:
            Tuple of (total_monthly_operations: int, data_available: bool).
            data_available=False means all Prometheus queries were unreachable;
            the caller must NOT present the returned count as real data in that case.
        """
        llm_count, kb_count, api_count = await asyncio.gather(
            _sum_prometheus_increase(_PROMQL_LLM_REQUESTS_30D),
            _sum_prometheus_increase(_PROMQL_KB_SEARCHES_30D),
            _sum_prometheus_increase(_PROMQL_API_REQUESTS_30D),
        )

        if llm_count is None and kb_count is None and api_count is None:
            self.logger.warning(
                "Prometheus unreachable — monthly operation count unavailable (#10720). "
                "Deploy a Prometheus scrape target for autobot_llm_requests_total, "
                "autobot_knowledge_search_requests_total, and "
                "autobot_api_requests_total to get real usage data."
            )
            return 0, False

        total = int((llm_count or 0) + (kb_count or 0) + (api_count or 0))
        return total, True

    async def calculate_roi_metrics(self) -> ROIMetrics:
        """Calculate comprehensive ROI metrics."""
        try:
            total_hardware_cost = sum(hw["cost"] for hw in self.hardware_investments.values())
            monthly_operational_cost = sum(self.operational_costs.values())

            performance_data = await self._get_historical_performance_data()
            performance_improvement = await self._calculate_performance_improvement(performance_data)

            productivity_gain_hours = self._estimate_productivity_gains(performance_improvement)

            total_monthly_operations, ops_available = await self._get_monthly_operations()
            cost_per_operation = (
                monthly_operational_cost / total_monthly_operations if total_monthly_operations > 0 else 0
            )

            break_even_months, total_roi = self._compute_savings_and_roi(
                total_hardware_cost, monthly_operational_cost, productivity_gain_hours
            )

            return ROIMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                hardware_investment_usd=total_hardware_cost,
                operational_cost_monthly_usd=monthly_operational_cost,
                performance_improvement_percent=performance_improvement,
                cost_per_operation=cost_per_operation,
                productivity_gain_hours_per_month=productivity_gain_hours,
                break_even_months=break_even_months,
                total_roi_percent=total_roi,
                operations_data_available=ops_available,
            )

        except Exception as e:
            self.logger.error("Error calculating ROI metrics: %s", e)
            return ROIMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                hardware_investment_usd=0.0,
                operational_cost_monthly_usd=0.0,
                performance_improvement_percent=0.0,
                cost_per_operation=0.0,
                productivity_gain_hours_per_month=0.0,
                break_even_months=0.0,
                total_roi_percent=0.0,
                operations_data_available=False,
            )

    async def _get_historical_performance_data(self) -> Dict[str, Any]:
        """Get historical performance data for analysis."""
        if not self.redis_client:
            self.logger.warning("Redis unavailable — historical performance data cannot be read (#10720)")
            return {"available": False, "error": "redis_unavailable"}

        try:
            history = self.redis_client.lrange("autobot:performance:history", 0, 99)
        except Exception as e:
            self.logger.error("Redis error reading performance history: %s", e)
            return {"available": False, "error": str(e)}

        performance_data: Dict[str, Any] = {
            "available": True,
            "api_response_times": [],
            "cpu_utilization": [],
            "memory_utilization": [],
            "service_availability": [],
        }

        for entry in history:
            try:
                data = json.loads(entry)
                metrics = data.get("data", {})

                services = metrics.get("services", [])
                if services:
                    avg_response_time = statistics.mean(
                        [s.response_time for s in services if hasattr(s, "response_time")]
                    )
                    performance_data["api_response_times"].append(avg_response_time)

                system = metrics.get("system")
                if system:
                    if hasattr(system, "cpu_percent"):
                        performance_data["cpu_utilization"].append(system.cpu_percent)
                    if hasattr(system, "memory_percent"):
                        performance_data["memory_utilization"].append(system.memory_percent)

            except Exception:
                continue  # nosec B112

        return performance_data

    async def _calculate_performance_improvement(self, performance_data: Dict[str, Any]) -> float:
        """Calculate overall performance improvement percentage."""
        try:
            if not performance_data.get("available", True):
                return 0.0

            improvements = []

            api_times = performance_data.get("api_response_times", [])
            if len(api_times) >= 10:
                recent_avg = statistics.mean(api_times[-10:])
                baseline = self.performance_baselines["api_response_time"]
                improvement = max(0, (baseline - recent_avg) / baseline * 100)
                improvements.append(improvement)

            cpu_utils = performance_data.get("cpu_utilization", [])
            if len(cpu_utils) >= 10:
                recent_avg = statistics.mean(cpu_utils[-10:])
                improvement = max(0, (80 - recent_avg) / 80 * 100)  # 80% baseline
                improvements.append(improvement)

            return statistics.mean(improvements) if improvements else 0.0

        except Exception as e:
            self.logger.error("Error calculating performance improvement: %s", e)
            return 0.0

    def _estimate_productivity_gains(self, performance_improvement: float) -> float:
        """Estimate productivity gains in hours per month."""
        try:
            base_hours_per_month = 160  # 40 hours/week * 4 weeks
            time_saved_ratio = performance_improvement / 100
            productivity_gain = base_hours_per_month * time_saved_ratio * 0.1  # Conservative estimate
            return min(productivity_gain, 40)  # Cap at 40 hours/month
        except Exception as e:
            self.logger.error("Error estimating productivity gains: %s", e)
            return 0.0

    def _build_component_definitions(self, utilization_data: Dict[str, float]) -> Dict[str, Dict]:
        """Build per-component cost/efficiency dict from config (not hardcoded literals).

        Costs are read from CostModelConfig (env-overridable via AUTOBOT_COST_*).
        All cost values are marked as estimates unless the operator has overridden them.
        Helper for analyze_cost_efficiency. Ref: #1088, #10720.
        """
        return {
            "cpu": {
                "monthly_cost": _cost.cpu_monthly_usd,
                "utilization": utilization_data.get("cpu", 0),
                "baseline_efficiency": _cost.cpu_baseline_efficiency,
            },
            "gpu": {
                "monthly_cost": _cost.gpu_monthly_usd,
                "utilization": utilization_data.get("gpu", 0),
                "baseline_efficiency": _cost.gpu_baseline_efficiency,
            },
            "npu": {
                "monthly_cost": _cost.npu_monthly_usd,
                "utilization": utilization_data.get("npu", 0),
                "baseline_efficiency": _cost.npu_baseline_efficiency,
            },
            "memory": {
                "monthly_cost": _cost.memory_monthly_usd,
                "utilization": utilization_data.get("memory", 0),
                "baseline_efficiency": _cost.memory_baseline_efficiency,
            },
            "storage": {
                "monthly_cost": _cost.storage_monthly_usd,
                "utilization": utilization_data.get("storage", 0),
                "baseline_efficiency": _cost.storage_baseline_efficiency,
            },
            "network": {
                "monthly_cost": _cost.network_monthly_usd,
                "utilization": utilization_data.get("network", 0),
                "baseline_efficiency": _cost.network_baseline_efficiency,
            },
        }

    async def analyze_cost_efficiency(self) -> List[CostAnalysis]:
        """Analyze cost efficiency of different system components."""
        cost_analyses = []

        try:
            utilization_data_raw = await self._get_current_utilization()
            if not utilization_data_raw.get("available", True):
                self.logger.warning("Utilization data unavailable (Redis down) — cost efficiency skipped (#10720)")
                return cost_analyses

            # Strip the sentinel key before passing to component builder
            utilization_data = {k: v for k, v in utilization_data_raw.items() if k != "available"}

            components = self._build_component_definitions(utilization_data)

            for component, data in components.items():
                utilization = data["utilization"]
                efficiency_score = min(utilization / data["baseline_efficiency"] * 100, 100)

                if efficiency_score < 70:
                    optimization_potential = data["monthly_cost"] * (70 - efficiency_score) / 100
                else:
                    optimization_potential = 0

                cost_analyses.append(
                    CostAnalysis(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        component=component,
                        monthly_cost_usd=data["monthly_cost"],
                        utilization_percent=utilization,
                        cost_per_hour=data["monthly_cost"] / (30 * 24),
                        efficiency_score=efficiency_score,
                        optimization_potential_usd=optimization_potential,
                        cost_is_estimate=True,  # always an operator estimate — label it
                    )
                )

        except Exception as e:
            self.logger.error("Error analyzing cost efficiency: %s", e)

        return cost_analyses

    async def _get_current_utilization(self) -> Dict[str, Any]:
        """Get current system utilization metrics.

        Returns a dict with available=False on Redis errors so callers can
        distinguish "no data yet" from "backend error" (#10720).
        """
        if not self.redis_client:
            self.logger.warning("Redis unavailable — current utilization cannot be read (#10720)")
            return {"available": False, "error": "redis_unavailable"}

        try:
            latest_data = self.redis_client.hget("autobot:performance:latest", "data")
        except Exception as e:
            self.logger.error("Redis error reading latest utilization: %s", e)
            return {"available": False, "error": str(e)}

        if not latest_data:
            return {"available": False, "error": "no_data"}

        try:
            metrics = json.loads(latest_data)
        except (json.JSONDecodeError, TypeError) as e:
            self.logger.error("Could not decode utilization JSON: %s", e)
            return {"available": False, "error": "decode_error"}

        system = metrics.get("system", {})

        return {
            "available": True,
            "cpu": (
                system.get("cpu_percent", 0) if isinstance(system.get("cpu_percent"), _NUMERIC_TYPES) else 0
            ),  # Issue #380
            "memory": (
                system.get("memory_percent", 0) if isinstance(system.get("memory_percent"), _NUMERIC_TYPES) else 0
            ),  # Issue #380
            "storage": (
                system.get("disk_percent", 0) if isinstance(system.get("disk_percent"), _NUMERIC_TYPES) else 0
            ),  # Issue #380
            "gpu": (system.get("gpu_utilization", 0) if system.get("gpu_utilization") is not None else 0),
            "npu": (system.get("npu_utilization", 0) if system.get("npu_utilization") is not None else 0),
            # Issue #10778: real network utilisation via psutil delta sample.
            # _get_network_utilization_percent returns None when link capacity is
            # not configured; fall back to 0 so cost-efficiency scoring is honest
            # rather than fabricating a number.
            "network": (await _get_network_utilization_percent()) or 0.0,
        }

    async def generate_performance_predictions(self) -> List[PerformancePrediction]:
        """Generate predictive performance insights using historical data."""
        predictions = []

        try:
            performance_data = await self._get_historical_performance_data()

            if not performance_data.get("available", True):
                self.logger.warning("Performance predictions skipped — historical data unavailable (#10720)")
                return predictions

            cpu_data = performance_data.get("cpu_utilization", [])
            if len(cpu_data) >= 10:
                cpu_prediction = await self._predict_metric_trend(cpu_data, "cpu_utilization")
                predictions.append(cpu_prediction)

            api_data = performance_data.get("api_response_times", [])
            if len(api_data) >= 10:
                api_prediction = await self._predict_metric_trend(api_data, "api_response_time")
                predictions.append(api_prediction)

            memory_data = performance_data.get("memory_utilization", [])
            if len(memory_data) >= 10:
                memory_prediction = await self._predict_metric_trend(memory_data, "memory_utilization")
                predictions.append(memory_prediction)

        except Exception as e:
            self.logger.error("Error generating performance predictions: %s", e)

        return predictions

    def _compute_linear_trend(self, data: List[float]) -> tuple:
        """Run linear regression on data and return trend statistics.

        Helper for _predict_metric_trend. Ref: #1088.

        Returns:
            Tuple of (current_value, predicted_7d, predicted_30d,
                      trend_direction, confidence_percent).
        """
        x = np.arange(len(data))
        y = np.array(data)
        z = np.polyfit(x, y, 1)
        slope = z[0]

        current_value = data[-1]
        predicted_7d = current_value + (slope * 7)
        predicted_30d = current_value + (slope * 30)

        if abs(slope) < 0.1:
            trend_direction = "stable"
        elif slope > 0:
            trend_direction = "increasing"
        else:
            trend_direction = "decreasing"

        std_dev = np.std(data)
        confidence = max(0, 100 - (std_dev * 10))

        return current_value, predicted_7d, predicted_30d, trend_direction, confidence

    async def _predict_metric_trend(self, data: List[float], metric_name: str) -> PerformancePrediction:
        """Predict trend for a specific metric."""
        try:
            if len(data) < 5:
                return PerformancePrediction(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    metric_name=metric_name,
                    current_value=0.0,
                    predicted_7d=0.0,
                    predicted_30d=0.0,
                    trend_direction="stable",
                    confidence_percent=0.0,
                    recommended_action="Insufficient data for prediction",
                )

            (
                current_value,
                predicted_7d,
                predicted_30d,
                trend_direction,
                confidence,
            ) = self._compute_linear_trend(data)

            recommendation = self._generate_metric_recommendation(metric_name, trend_direction, predicted_30d)

            return PerformancePrediction(
                timestamp=datetime.now(timezone.utc).isoformat(),
                metric_name=metric_name,
                current_value=current_value,
                predicted_7d=predicted_7d,
                predicted_30d=predicted_30d,
                trend_direction=trend_direction,
                confidence_percent=confidence,
                recommended_action=recommendation,
            )

        except Exception as e:
            self.logger.error("Error predicting trend for %s: %s", metric_name, e)
            return PerformancePrediction(
                timestamp=datetime.now(timezone.utc).isoformat(),
                metric_name=metric_name,
                current_value=0.0,
                predicted_7d=0.0,
                predicted_30d=0.0,
                trend_direction="unknown",
                confidence_percent=0.0,
                recommended_action="Prediction failed",
            )

    def _generate_metric_recommendation(self, metric_name: str, trend: str, predicted_value: float) -> str:
        """Generate recommendations based on metric trends."""
        cpu_threshold = ALERT_THRESHOLDS.get("cpu_percent", 80.0)
        memory_threshold = ALERT_THRESHOLDS.get("memory_percent", 85.0)

        if metric_name == "cpu_utilization":
            if trend == "increasing" and predicted_value > cpu_threshold:
                return "CPU utilization trending high - consider workload optimization or scaling"
            elif trend == "decreasing":
                return "CPU utilization decreasing - good efficiency trend"
            else:
                return "CPU utilization stable - monitor for changes"

        elif metric_name == "memory_utilization":
            if trend == "increasing" and predicted_value > memory_threshold:
                return "Memory utilization trending high - consider memory optimization"
            else:
                return "Memory utilization within acceptable range"

        elif metric_name == "api_response_time":
            if trend == "increasing" and predicted_value > 3.0:
                return "API response time increasing - investigate performance bottlenecks"
            elif trend == "decreasing":
                return "API response time improving - performance optimizations working"
            else:
                return "API response time stable"

        return "Continue monitoring"

    def _calculate_availability_score(self, services_data: List) -> float:
        """Calculate availability score from services data.

        Helper for calculate_system_health_score.
        """
        healthy_services = sum(1 for s in services_data if getattr(s, "is_healthy", False))
        total_services = max(len(services_data), 1)
        return (healthy_services / total_services) * 100

    def _calculate_performance_score(self, utilization_data: Dict[str, float]) -> float:
        """Calculate performance score from utilization data.

        Helper for calculate_system_health_score.
        """
        cpu_util = utilization_data.get("cpu", 0)
        memory_util = utilization_data.get("memory", 0)
        cpu_performance = 100 - abs(cpu_util - 60)
        memory_performance = 100 - abs(memory_util - 70)
        return statistics.mean([max(0, cpu_performance), max(0, memory_performance)])

    def _calculate_efficiency_score(self, utilization_data: Dict[str, float]) -> float:
        """Calculate efficiency score from utilization data.

        Helper for calculate_system_health_score.
        """
        gpu_util = utilization_data.get("gpu", 0)
        npu_util = utilization_data.get("npu", 0)
        cpu_util = utilization_data.get("cpu", 0)
        efficiency_components = [
            min(cpu_util / 60 * 100, 100),
            min(gpu_util / 70 * 100, 100),
            min(npu_util / 50 * 100, 100),
        ]
        return statistics.mean([max(c, 0) for c in efficiency_components])

    def _calculate_user_satisfaction_score(self, performance_data: Dict[str, Any]) -> float:
        """Calculate user satisfaction score from response times.

        Helper for calculate_system_health_score.
        """
        api_times = performance_data.get("api_response_times", [])
        if api_times:
            avg_response_time = statistics.mean(api_times[-10:]) if len(api_times) >= 10 else statistics.mean(api_times)
            return max(0, 100 - (avg_response_time - 1.0) * 20)
        return 80.0

    def _identify_improvement_areas(
        self,
        availability_score: float,
        performance_score: float,
        efficiency_score: float,
        security_score: float,
        user_satisfaction: float,
    ) -> List[str]:
        """Identify areas needing improvement.

        Helper for calculate_system_health_score.
        """
        improvement_areas = []
        if availability_score < 90:
            improvement_areas.append("Service Availability")
        if performance_score < 70:
            improvement_areas.append("System Performance")
        if efficiency_score < 60:
            improvement_areas.append("Resource Efficiency")
        if security_score < 80:
            improvement_areas.append("Security Posture")
        if user_satisfaction < 75:
            improvement_areas.append("User Experience")
        return improvement_areas

    async def calculate_system_health_score(self) -> SystemHealthScore:
        """Calculate comprehensive system health score."""
        try:
            utilization_raw = await self._get_current_utilization()
            utilization_available = utilization_raw.get("available", True)
            utilization_data = (
                {k: v for k, v in utilization_raw.items() if k != "available"} if utilization_available else {}
            )

            performance_data = await self._get_historical_performance_data()
            performance_available = performance_data.get("available", True)

            # data_available is False when ANY required source is degraded (#10779).
            data_available = utilization_available and performance_available

            services_data = []
            if self.redis_client:
                try:
                    latest_data = self.redis_client.hget("autobot:performance:latest", "data")
                    if latest_data:
                        metrics = json.loads(latest_data)
                        services_data = metrics.get("services", [])
                except Exception as e:
                    self.logger.error("Redis error reading services data for health score: %s", e)

            availability_score = self._calculate_availability_score(services_data)
            # Guard: avoid fabricated 35.0/80.0 defaults when source data is missing (#10779).
            performance_score = self._calculate_performance_score(utilization_data) if utilization_available else 0.0
            efficiency_score = self._calculate_efficiency_score(utilization_data) if utilization_available else 0.0
            security_score = 85.0
            user_satisfaction = (
                self._calculate_user_satisfaction_score(performance_data) if performance_available else 0.0
            )

            scores = [
                availability_score,
                performance_score,
                security_score,
                efficiency_score,
                user_satisfaction,
            ]
            overall_score = statistics.mean(scores)

            improvement_areas = self._identify_improvement_areas(
                availability_score,
                performance_score,
                efficiency_score,
                security_score,
                user_satisfaction,
            )

            return SystemHealthScore(
                timestamp=datetime.now(timezone.utc).isoformat(),
                overall_score=overall_score,
                availability_score=availability_score,
                performance_score=performance_score,
                security_score=security_score,
                efficiency_score=efficiency_score,
                user_satisfaction_score=user_satisfaction,
                improvement_areas=improvement_areas,
                data_available=data_available,
            )

        except Exception as e:
            self.logger.error("Error calculating system health score: %s", e)
            return SystemHealthScore(
                timestamp=datetime.now(timezone.utc).isoformat(),
                overall_score=0.0,
                availability_score=0.0,
                performance_score=0.0,
                security_score=0.0,
                efficiency_score=0.0,
                user_satisfaction_score=0.0,
                improvement_areas=["System Health Calculation Failed"],
                data_available=False,
            )

    async def generate_comprehensive_dashboard_report(self) -> Dict[str, Any]:
        """Generate comprehensive business intelligence dashboard report."""
        try:
            roi_metrics = await self.calculate_roi_metrics()
            cost_analysis = await self.analyze_cost_efficiency()
            predictions = await self.generate_performance_predictions()
            health_score = await self.calculate_system_health_score()

            dashboard_report = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": {
                    "overall_health_score": health_score.overall_score,
                    "total_roi_percent": roi_metrics.total_roi_percent,
                    "monthly_operational_cost": roi_metrics.operational_cost_monthly_usd,
                    "break_even_months": roi_metrics.break_even_months,
                    "total_optimization_potential": sum(ca.optimization_potential_usd for ca in cost_analysis),
                    # Surfaced explicitly so consumers can show "unavailable" rather than fake numbers
                    "operations_data_available": roi_metrics.operations_data_available,
                    # False when Redis/utilization data was unavailable during health calculation (#10779)
                    "system_health_data_available": health_score.data_available,
                },
                "roi_analysis": asdict(roi_metrics),
                "cost_efficiency": [asdict(ca) for ca in cost_analysis],
                "performance_predictions": [asdict(p) for p in predictions],
                "system_health": asdict(health_score),
                "hardware_investments": self.hardware_investments,
                "operational_costs": self.operational_costs,
            }

            await self._store_dashboard_report(dashboard_report)
            await self._generate_visual_dashboard(dashboard_report)

            return dashboard_report

        except Exception as e:
            self.logger.error("Error generating dashboard report: %s", e)
            return {
                "error": "Failed to generate dashboard report",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    async def _store_dashboard_report(self, report: Dict[str, Any]):
        """Store dashboard report in Redis and files."""
        timestamp = datetime.now(timezone.utc).isoformat()

        if self.redis_client:
            try:
                self.redis_client.hset(
                    "autobot:bi_dashboard:latest",
                    mapping={
                        "timestamp": timestamp,
                        "data": json.dumps(report, default=str),
                    },
                )
                self.redis_client.lpush(
                    "autobot:bi_dashboard:history",
                    json.dumps({"timestamp": timestamp, "data": report}, default=str),
                )
                self.redis_client.ltrim("autobot:bi_dashboard:history", 0, 99)
            except Exception as e:
                self.logger.error("Error storing dashboard report in Redis: %s", e)

        try:
            report_file = self.dashboard_data_path / f"bi_dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            async with aiofiles.open(report_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(report, indent=2, default=str))
        except OSError as e:
            self.logger.error("Failed to write dashboard report to %s: %s", report_file, e)
        except Exception as e:
            self.logger.error("Error storing dashboard report to file: %s", e)

    def _prepare_dashboard_template_vars(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare template variables for dashboard rendering.

        Helper for _generate_visual_dashboard.
        """
        summary = report.get("summary", {})
        health = report.get("system_health", {})

        # data_available=False means scores are zeroed placeholders, not real measurements (#10779)
        health_data_available = health.get("data_available", True)
        health_score_raw = round(health.get("overall_score", 0), 1)
        health_color = "#28a745" if health_score_raw >= 80 else "#ffc107" if health_score_raw >= 60 else "#dc3545"

        roi_percent = round(summary.get("total_roi_percent", 0), 1)
        roi_class = "roi-positive" if roi_percent > 0 else "roi-negative"

        return {
            "timestamp": report.get("timestamp", ""),
            "health_score": health_score_raw,
            "health_color": health_color,
            "health_data_available": health_data_available,
            "roi_percent": roi_percent,
            "roi_class": roi_class,
            "break_even_months": round(summary.get("break_even_months", 0), 1),
            "monthly_cost": round(summary.get("monthly_operational_cost", 0)),
            "optimization_potential": round(summary.get("total_optimization_potential", 0)),
            "hardware_investment": round(report.get("roi_analysis", {}).get("hardware_investment_usd", 0)),
            "availability_score": round(health.get("availability_score", 0), 1),
            "performance_score": round(health.get("performance_score", 0), 1),
            "security_score": round(health.get("security_score", 0), 1),
            "efficiency_score": round(health.get("efficiency_score", 0), 1),
            "user_satisfaction_score": round(health.get("user_satisfaction_score", 0), 1),
            "cost_analysis": report.get("cost_efficiency", []),
            "predictions": report.get("performance_predictions", []),
            "improvement_areas": health.get("improvement_areas", []),
        }

    async def _save_dashboard_html(self, dashboard_html: str, dashboard_file: Path):
        """Save dashboard HTML to file.

        Helper for _generate_visual_dashboard.
        """
        try:
            async with aiofiles.open(dashboard_file, "w", encoding="utf-8") as f:
                await f.write(dashboard_html)
            self.logger.info("Dashboard saved to: %s", dashboard_file)
        except OSError as e:
            self.logger.error("Failed to save dashboard HTML to %s: %s", dashboard_file, e)

    async def _generate_visual_dashboard(self, report: Dict[str, Any]):
        """Generate HTML visual dashboard."""
        try:
            dashboard_template = Template(_DASHBOARD_HTML_TEMPLATE)
            template_vars = self._prepare_dashboard_template_vars(report)
            dashboard_html = dashboard_template.render(**template_vars)

            dashboard_file = self.dashboard_data_path / f"dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            await self._save_dashboard_html(dashboard_html, dashboard_file)

        except Exception as e:
            self.logger.error("Error generating visual dashboard: %s", e)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    import argparse

    async def main():
        parser = argparse.ArgumentParser(description="AutoBot Business Intelligence Dashboard")
        parser.add_argument(
            "--generate",
            action="store_true",
            help="Generate comprehensive dashboard report",
        )
        parser.add_argument("--roi", action="store_true", help="Calculate ROI metrics only")
        parser.add_argument("--health", action="store_true", help="Calculate system health score only")

        args = parser.parse_args()

        bi_dashboard = BusinessIntelligenceDashboard()
        await bi_dashboard.initialize_redis_connection()

        if args.roi:
            roi_metrics = await bi_dashboard.calculate_roi_metrics()
            logger.info("ROI Analysis:")
            logger.info("Total Hardware Investment: $%s", f"{roi_metrics.hardware_investment_usd:,.2f}")
            logger.info("Monthly Operational Cost: $%s", f"{roi_metrics.operational_cost_monthly_usd:,.2f}")
            logger.info("Total ROI: %s%%", f"{roi_metrics.total_roi_percent:.1f}")
            logger.info("Break Even: %s months", f"{roi_metrics.break_even_months:.1f}")
            if not roi_metrics.operations_data_available:
                logger.warning("Monthly operation count: unavailable (Prometheus unreachable)")

        elif args.health:
            health_score = await bi_dashboard.calculate_system_health_score()
            logger.info("System Health Score:")
            logger.info("Overall: %s/100", f"{health_score.overall_score:.1f}")
            logger.info("Availability: %s/100", f"{health_score.availability_score:.1f}")
            logger.info("Performance: %s/100", f"{health_score.performance_score:.1f}")
            logger.info("Security: %s/100", f"{health_score.security_score:.1f}")
            logger.info("Efficiency: %s/100", f"{health_score.efficiency_score:.1f}")
            if not health_score.data_available:
                logger.warning(
                    "System health score: unavailable (Redis/utilization data not collected"
                    " — scores are zeroed, not real measurements)"
                )

        elif args.generate:
            logger.info("Generating comprehensive BI dashboard...")
            report = await bi_dashboard.generate_comprehensive_dashboard_report()
            logger.info("Dashboard generated successfully!")
            logger.info("Report summary:")
            summary = report.get("summary", {})
            logger.info("  Overall Health: %s/100", f"{summary.get('overall_health_score', 0):.1f}")
            logger.info("  Total ROI: %s%%", f"{summary.get('total_roi_percent', 0):.1f}")
            logger.info("  Monthly Cost: $%s", f"{summary.get('monthly_operational_cost', 0):.2f}")
            optimization_potential = summary.get("total_optimization_potential", 0)
            logger.info("  Optimization Potential: $%s/month", f"{optimization_potential:.2f}")
            if not summary.get("operations_data_available", True):
                logger.warning("  Monthly operations count: unavailable (Prometheus unreachable)")
            if not summary.get("system_health_data_available", True):
                logger.warning("  System health scores: unavailable (Redis/utilization data not collected)")

    asyncio.run(main())
