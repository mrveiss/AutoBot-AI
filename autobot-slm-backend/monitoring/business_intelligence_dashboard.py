#!/usr/bin/env python3
"""
AutoBot Business Intelligence Dashboard
Advanced analytics, ROI tracking, and performance insights for the distributed system.
"""

import asyncio
import json
import logging
import os
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import aiofiles
import matplotlib

matplotlib.use("Agg")  # Non-interactive backend
import numpy as np
from jinja2 import Template
from performance_monitor import ALERT_THRESHOLDS

from autobot_shared.network_constants import NetworkConstants

# Issue #380: Module-level tuple for numeric type checks
_NUMERIC_TYPES = (int, float)

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
            <h1>🤖 AutoBot Business Intelligence Dashboard</h1>
            <p>Distributed System Performance & ROI Analytics</p>
            <p class="timestamp">Generated: {{ timestamp }}</p>
        </div>

        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-title">Overall System Health</div>
                <div class="health-score">{{ health_score }}/100</div>
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
                <p>Availability: {{ availability_score }}/100</p>
                <p>Performance: {{ performance_score }}/100</p>
                <p>Security: {{ security_score }}/100</p>
                <p>Efficiency: {{ efficiency_score }}/100</p>
                <p>User Satisfaction: {{ user_satisfaction_score }}/100</p>
            </div>

            <div class="metric-card">
                <h3>Cost Efficiency Analysis</h3>
                {% for cost in cost_analysis %}
                <p>{{ cost.component }}: {{ cost.efficiency_score }}% efficient</p>
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


class BusinessIntelligenceDashboard:
    """Business Intelligence and Analytics Dashboard for AutoBot."""

    def __init__(
        self, redis_host: str = NetworkConstants.REDIS_VM_IP, redis_port: int = 6379
    ):
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
            # Use canonical Redis utility following CLAUDE.md "🔴 REDIS CLIENT USAGE" policy
            from autobot_shared.redis_client import get_redis_client

            self.redis_client = get_redis_client(database="metrics")
            if self.redis_client is None:
                raise Exception("Redis client initialization returned None")

            self.redis_client.ping()
            self.logger.info("✅ Redis connection established for BI Dashboard")
        except Exception as e:
            self.logger.error(f"❌ Failed to connect to Redis for BI: {e}")
            self.redis_client = None

    async def calculate_roi_metrics(self) -> ROIMetrics:
        """Calculate comprehensive ROI metrics."""
        try:
            # Calculate total hardware investment
            total_hardware_cost = sum(
                hw["cost"] for hw in self.hardware_investments.values()
            )
            monthly_operational_cost = sum(self.operational_costs.values())

            # Get performance improvement metrics
            performance_data = await self._get_historical_performance_data()
            performance_improvement = await self._calculate_performance_improvement(
                performance_data
            )

            # Calculate productivity gains (estimated)
            productivity_gain_hours = self._estimate_productivity_gains(
                performance_improvement
            )

            # Estimate cost per operation
            total_monthly_operations = await self._estimate_monthly_operations()
            cost_per_operation = (
                monthly_operational_cost / total_monthly_operations
                if total_monthly_operations > 0
                else 0
            )

            # Calculate break-even point
            monthly_savings = productivity_gain_hours * 50  # $50/hour value
            break_even_months = (
                total_hardware_cost / monthly_savings
                if monthly_savings > 0
                else float("inf")
            )

            # Calculate total ROI
            annual_savings = monthly_savings * 12
            total_roi = (
                (
                    (annual_savings - monthly_operational_cost * 12)
                    / total_hardware_cost
                    * 100
                )
                if total_hardware_cost > 0
                else 0
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
            )

        except Exception as e:
            self.logger.error(f"Error calculating ROI metrics: {e}")
            return ROIMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                hardware_investment_usd=0.0,
                operational_cost_monthly_usd=0.0,
                performance_improvement_percent=0.0,
                cost_per_operation=0.0,
                productivity_gain_hours_per_month=0.0,
                break_even_months=0.0,
                total_roi_percent=0.0,
            )

    async def _get_historical_performance_data(self) -> Dict[str, List[float]]:
        """Get historical performance data for analysis."""
        try:
            if not self.redis_client:
                return {}

            # Get performance history from Redis
            history = self.redis_client.lrange("autobot:performance:history", 0, 99)

            performance_data = {
                "api_response_times": [],
                "cpu_utilization": [],
                "memory_utilization": [],
                "service_availability": [],
            }

            for entry in history:
                try:
                    data = json.loads(entry)
                    metrics = data.get("data", {})

                    # Extract relevant metrics
                    services = metrics.get("services", [])
                    if services:
                        avg_response_time = statistics.mean(
                            [
                                s.response_time
                                for s in services
                                if hasattr(s, "response_time")
                            ]
                        )
                        performance_data["api_response_times"].append(avg_response_time)

                    system = metrics.get("system")
                    if system:
                        if hasattr(system, "cpu_percent"):
                            performance_data["cpu_utilization"].append(
                                system.cpu_percent
                            )
                        if hasattr(system, "memory_percent"):
                            performance_data["memory_utilization"].append(
                                system.memory_percent
                            )

                except Exception:
                    continue  # nosec B112

            return performance_data

        except Exception as e:
            self.logger.error(f"Error getting historical performance data: {e}")
            return {}

    async def _calculate_performance_improvement(
        self, performance_data: Dict[str, List[float]]
    ) -> float:
        """Calculate overall performance improvement percentage."""
        try:
            improvements = []

            # API response time improvement
            api_times = performance_data.get("api_response_times", [])
            if len(api_times) >= 10:
                recent_avg = statistics.mean(api_times[-10:])
                baseline = self.performance_baselines["api_response_time"]
                improvement = max(0, (baseline - recent_avg) / baseline * 100)
                improvements.append(improvement)

            # CPU efficiency improvement
            cpu_utils = performance_data.get("cpu_utilization", [])
            if len(cpu_utils) >= 10:
                recent_avg = statistics.mean(cpu_utils[-10:])
                # Lower CPU utilization for same workload is better
                improvement = max(0, (80 - recent_avg) / 80 * 100)  # 80% baseline
                improvements.append(improvement)

            return statistics.mean(improvements) if improvements else 0.0

        except Exception as e:
            self.logger.error(f"Error calculating performance improvement: {e}")
            return 0.0

    def _estimate_productivity_gains(self, performance_improvement: float) -> float:
        """Estimate productivity gains in hours per month."""
        try:
            # Base calculation: performance improvement translates to time saved
            base_hours_per_month = 160  # 40 hours/week * 4 weeks
            time_saved_ratio = performance_improvement / 100
            productivity_gain = (
                base_hours_per_month * time_saved_ratio * 0.1
            )  # Conservative estimate

            return min(productivity_gain, 40)  # Cap at 40 hours/month

        except Exception as e:
            self.logger.error(f"Error estimating productivity gains: {e}")
            return 0.0

    async def _estimate_monthly_operations(self) -> int:
        """Estimate total monthly operations."""
        try:
            # Estimate based on typical usage patterns
            daily_api_calls = 1000  # Conservative estimate
            daily_knowledge_searches = 500
            daily_llm_requests = 200

            total_daily_operations = (
                daily_api_calls + daily_knowledge_searches + daily_llm_requests
            )
            return total_daily_operations * 30  # Monthly

        except Exception as e:
            self.logger.error(f"Error estimating monthly operations: {e}")
            return 0

    async def analyze_cost_efficiency(self) -> List[CostAnalysis]:
        """Analyze cost efficiency of different system components."""
        cost_analyses = []

        try:
            # Get current utilization data
            utilization_data = await self._get_current_utilization()

            # Analyze each major component
            components = {
                "cpu": {
                    "monthly_cost": 50,  # Portion of total operational cost
                    "utilization": utilization_data.get("cpu", 0),
                    "baseline_efficiency": 70,
                },
                "gpu": {
                    "monthly_cost": 80,  # Higher due to power consumption
                    "utilization": utilization_data.get("gpu", 0),
                    "baseline_efficiency": 60,
                },
                "npu": {
                    "monthly_cost": 30,
                    "utilization": utilization_data.get("npu", 0),
                    "baseline_efficiency": 50,
                },
                "memory": {
                    "monthly_cost": 20,
                    "utilization": utilization_data.get("memory", 0),
                    "baseline_efficiency": 80,
                },
                "storage": {
                    "monthly_cost": 25,
                    "utilization": utilization_data.get("storage", 0),
                    "baseline_efficiency": 60,
                },
                "network": {
                    "monthly_cost": 80,  # Internet costs
                    "utilization": utilization_data.get("network", 0),
                    "baseline_efficiency": 40,
                },
            }

            for component, data in components.items():
                utilization = data["utilization"]
                efficiency_score = min(
                    utilization / data["baseline_efficiency"] * 100, 100
                )

                # Calculate optimization potential
                if efficiency_score < 70:
                    optimization_potential = (
                        data["monthly_cost"] * (70 - efficiency_score) / 100
                    )
                else:
                    optimization_potential = 0

                cost_analyses.append(
                    CostAnalysis(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        component=component,
                        monthly_cost_usd=data["monthly_cost"],
                        utilization_percent=utilization,
                        cost_per_hour=data["monthly_cost"] / (30 * 24),  # $/hour
                        efficiency_score=efficiency_score,
                        optimization_potential_usd=optimization_potential,
                    )
                )

        except Exception as e:
            self.logger.error(f"Error analyzing cost efficiency: {e}")

        return cost_analyses

    async def _get_current_utilization(self) -> Dict[str, float]:
        """Get current system utilization metrics."""
        try:
            if not self.redis_client:
                return {}

            # Get latest performance metrics
            latest_data = self.redis_client.hget("autobot:performance:latest", "data")
            if not latest_data:
                return {}

            metrics = json.loads(latest_data)
            system = metrics.get("system", {})

            utilization = {
                "cpu": system.get("cpu_percent", 0)
                if isinstance(system.get("cpu_percent"), _NUMERIC_TYPES)
                else 0,  # Issue #380
                "memory": system.get("memory_percent", 0)
                if isinstance(system.get("memory_percent"), _NUMERIC_TYPES)
                else 0,  # Issue #380
                "storage": system.get("disk_percent", 0)
                if isinstance(system.get("disk_percent"), _NUMERIC_TYPES)
                else 0,  # Issue #380
                "gpu": system.get("gpu_utilization", 0)
                if system.get("gpu_utilization") is not None
                else 0,
                "npu": system.get("npu_utilization", 0)
                if system.get("npu_utilization") is not None
                else 0,
                "network": 30.0,  # Estimated network utilization
            }

            return utilization

        except Exception as e:
            self.logger.error(f"Error getting current utilization: {e}")
            return {}

    async def generate_performance_predictions(self) -> List[PerformancePrediction]:
        """Generate predictive performance insights using historical data."""
        predictions = []

        try:
            # Get historical data for trend analysis
            performance_data = await self._get_historical_performance_data()

            # Predict CPU utilization
            cpu_data = performance_data.get("cpu_utilization", [])
            if len(cpu_data) >= 10:
                cpu_prediction = await self._predict_metric_trend(
                    cpu_data, "cpu_utilization"
                )
                predictions.append(cpu_prediction)

            # Predict API response times
            api_data = performance_data.get("api_response_times", [])
            if len(api_data) >= 10:
                api_prediction = await self._predict_metric_trend(
                    api_data, "api_response_time"
                )
                predictions.append(api_prediction)

            # Predict memory utilization
            memory_data = performance_data.get("memory_utilization", [])
            if len(memory_data) >= 10:
                memory_prediction = await self._predict_metric_trend(
                    memory_data, "memory_utilization"
                )
                predictions.append(memory_prediction)

        except Exception as e:
            self.logger.error(f"Error generating performance predictions: {e}")

        return predictions

    async def _predict_metric_trend(
        self, data: List[float], metric_name: str
    ) -> PerformancePrediction:
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

            # Simple linear regression for trend prediction
            x = np.arange(len(data))
            y = np.array(data)

            # Calculate linear trend
            z = np.polyfit(x, y, 1)
            slope = z[0]

            current_value = data[-1]
            predicted_7d = current_value + (slope * 7)
            predicted_30d = current_value + (slope * 30)

            # Determine trend direction
            if abs(slope) < 0.1:
                trend_direction = "stable"
            elif slope > 0:
                trend_direction = "increasing"
            else:
                trend_direction = "decreasing"

            # Calculate confidence (based on data consistency)
            std_dev = np.std(data)
            confidence = max(0, 100 - (std_dev * 10))  # Simple confidence calculation

            # Generate recommendation
            recommendation = self._generate_metric_recommendation(
                metric_name, trend_direction, predicted_30d
            )

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
            self.logger.error(f"Error predicting trend for {metric_name}: {e}")
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

    def _generate_metric_recommendation(
        self, metric_name: str, trend: str, predicted_value: float
    ) -> str:
        """Generate recommendations based on metric trends."""
        # Get thresholds from centralized config
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
                return (
                    "API response time increasing - investigate performance bottlenecks"
                )
            elif trend == "decreasing":
                return "API response time improving - performance optimizations working"
            else:
                return "API response time stable"

        return "Continue monitoring"

    def _calculate_availability_score(self, services_data: List) -> float:
        """Calculate availability score from services data.

        Helper for calculate_system_health_score.
        """
        healthy_services = sum(
            1 for s in services_data if getattr(s, "is_healthy", False)
        )
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

    def _calculate_user_satisfaction_score(
        self, performance_data: Dict[str, List[float]]
    ) -> float:
        """Calculate user satisfaction score from response times.

        Helper for calculate_system_health_score.
        """
        api_times = performance_data.get("api_response_times", [])
        if api_times:
            avg_response_time = (
                statistics.mean(api_times[-10:])
                if len(api_times) >= 10
                else statistics.mean(api_times)
            )
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
            utilization_data = await self._get_current_utilization()
            performance_data = await self._get_historical_performance_data()

            services_data = []
            if self.redis_client:
                latest_data = self.redis_client.hget(
                    "autobot:performance:latest", "data"
                )
                if latest_data:
                    metrics = json.loads(latest_data)
                    services_data = metrics.get("services", [])

            availability_score = self._calculate_availability_score(services_data)
            performance_score = self._calculate_performance_score(utilization_data)
            efficiency_score = self._calculate_efficiency_score(utilization_data)
            security_score = 85.0
            user_satisfaction = self._calculate_user_satisfaction_score(
                performance_data
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
            )

        except Exception as e:
            self.logger.error(f"Error calculating system health score: {e}")
            return SystemHealthScore(
                timestamp=datetime.now(timezone.utc).isoformat(),
                overall_score=0.0,
                availability_score=0.0,
                performance_score=0.0,
                security_score=0.0,
                efficiency_score=0.0,
                user_satisfaction_score=0.0,
                improvement_areas=["System Health Calculation Failed"],
            )

    async def generate_comprehensive_dashboard_report(self) -> Dict[str, Any]:
        """Generate comprehensive business intelligence dashboard report."""
        try:
            # Collect all BI metrics
            roi_metrics = await self.calculate_roi_metrics()
            cost_analysis = await self.analyze_cost_efficiency()
            predictions = await self.generate_performance_predictions()
            health_score = await self.calculate_system_health_score()

            # Compile comprehensive report
            dashboard_report = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": {
                    "overall_health_score": health_score.overall_score,
                    "total_roi_percent": roi_metrics.total_roi_percent,
                    "monthly_operational_cost": roi_metrics.operational_cost_monthly_usd,
                    "break_even_months": roi_metrics.break_even_months,
                    "total_optimization_potential": sum(
                        ca.optimization_potential_usd for ca in cost_analysis
                    ),
                },
                "roi_analysis": asdict(roi_metrics),
                "cost_efficiency": [asdict(ca) for ca in cost_analysis],
                "performance_predictions": [asdict(p) for p in predictions],
                "system_health": asdict(health_score),
                "hardware_investments": self.hardware_investments,
                "operational_costs": self.operational_costs,
            }

            # Store the dashboard report
            await self._store_dashboard_report(dashboard_report)

            # Generate visual dashboard (HTML)
            await self._generate_visual_dashboard(dashboard_report)

            return dashboard_report

        except Exception as e:
            self.logger.error(f"Error generating dashboard report: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    async def _store_dashboard_report(self, report: Dict[str, Any]):
        """Store dashboard report in Redis and files."""
        timestamp = datetime.now(timezone.utc).isoformat()

        # Store in Redis
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
                self.logger.error(f"Error storing dashboard report in Redis: {e}")

        # Store in local file
        try:
            report_file = (
                self.dashboard_data_path
                / f"bi_dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            async with aiofiles.open(report_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(report, indent=2, default=str))
        except OSError as e:
            self.logger.error(f"Failed to write dashboard report to {report_file}: {e}")
        except Exception as e:
            self.logger.error(f"Error storing dashboard report to file: {e}")

    def _prepare_dashboard_template_vars(
        self, report: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Prepare template variables for dashboard rendering.

        Helper for _generate_visual_dashboard.
        """
        summary = report.get("summary", {})
        health = report.get("system_health", {})

        health_score = round(health.get("overall_score", 0), 1)
        health_color = (
            "#28a745"
            if health_score >= 80
            else "#ffc107"
            if health_score >= 60
            else "#dc3545"
        )

        roi_percent = round(summary.get("total_roi_percent", 0), 1)
        roi_class = "roi-positive" if roi_percent > 0 else "roi-negative"

        return {
            "timestamp": report.get("timestamp", ""),
            "health_score": health_score,
            "health_color": health_color,
            "roi_percent": roi_percent,
            "roi_class": roi_class,
            "break_even_months": round(summary.get("break_even_months", 0), 1),
            "monthly_cost": round(summary.get("monthly_operational_cost", 0)),
            "optimization_potential": round(
                summary.get("total_optimization_potential", 0)
            ),
            "hardware_investment": round(
                report.get("roi_analysis", {}).get("hardware_investment_usd", 0)
            ),
            "availability_score": round(health.get("availability_score", 0), 1),
            "performance_score": round(health.get("performance_score", 0), 1),
            "security_score": round(health.get("security_score", 0), 1),
            "efficiency_score": round(health.get("efficiency_score", 0), 1),
            "user_satisfaction_score": round(
                health.get("user_satisfaction_score", 0), 1
            ),
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
            self.logger.info(f"📊 Dashboard saved to: {dashboard_file}")
        except OSError as e:
            self.logger.error(f"Failed to save dashboard HTML to {dashboard_file}: {e}")

    async def _generate_visual_dashboard(self, report: Dict[str, Any]):
        """Generate HTML visual dashboard."""
        try:
            dashboard_template = Template(_DASHBOARD_HTML_TEMPLATE)
            template_vars = self._prepare_dashboard_template_vars(report)
            dashboard_html = dashboard_template.render(**template_vars)

            dashboard_file = (
                self.dashboard_data_path
                / f"dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            )
            await self._save_dashboard_html(dashboard_html, dashboard_file)

        except Exception as e:
            self.logger.error(f"Error generating visual dashboard: {e}")


if __name__ == "__main__":
    import argparse

    async def main():
        parser = argparse.ArgumentParser(
            description="AutoBot Business Intelligence Dashboard"
        )
        parser.add_argument(
            "--generate",
            action="store_true",
            help="Generate comprehensive dashboard report",
        )
        parser.add_argument(
            "--roi", action="store_true", help="Calculate ROI metrics only"
        )
        parser.add_argument(
            "--health", action="store_true", help="Calculate system health score only"
        )

        args = parser.parse_args()

        bi_dashboard = BusinessIntelligenceDashboard()
        await bi_dashboard.initialize_redis_connection()

        if args.roi:
            roi_metrics = await bi_dashboard.calculate_roi_metrics()
            print("📈 ROI Analysis:")
            print(
                f"Total Hardware Investment: ${roi_metrics.hardware_investment_usd:,.2f}"
            )
            print(
                f"Monthly Operational Cost: ${roi_metrics.operational_cost_monthly_usd:,.2f}"
            )
            print(f"Total ROI: {roi_metrics.total_roi_percent:.1f}%")
            print(f"Break Even: {roi_metrics.break_even_months:.1f} months")

        elif args.health:
            health_score = await bi_dashboard.calculate_system_health_score()
            print("🏥 System Health Score:")
            print(f"Overall: {health_score.overall_score:.1f}/100")
            print(f"Availability: {health_score.availability_score:.1f}/100")
            print(f"Performance: {health_score.performance_score:.1f}/100")
            print(f"Security: {health_score.security_score:.1f}/100")
            print(f"Efficiency: {health_score.efficiency_score:.1f}/100")

        elif args.generate:
            print("🚀 Generating comprehensive BI dashboard...")
            report = await bi_dashboard.generate_comprehensive_dashboard_report()
            print("✅ Dashboard generated successfully!")
            print("📊 Report summary:")
            summary = report.get("summary", {})
            print(f"  Overall Health: {summary.get('overall_health_score', 0):.1f}/100")
            print(f"  Total ROI: {summary.get('total_roi_percent', 0):.1f}%")
            print(f"  Monthly Cost: ${summary.get('monthly_operational_cost', 0):.2f}")
            optimization_potential = summary.get("total_optimization_potential", 0)
            print(f"  Optimization Potential: ${optimization_potential:.2f}/month")

    asyncio.run(main())
