# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Analytics Service - Centralized facade for all analytics capabilities.

This module provides a unified interface for:
- User behavior analytics
- Agent performance analytics
- Cost analytics
- Predictive maintenance
- Resource optimization recommendations
- System health insights

Related Issues: #59 (Advanced Analytics & Business Intelligence)
"""

import asyncio
import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from backend.services.agent_analytics import AgentAnalytics, get_agent_analytics
from backend.services.llm_cost_tracker import LLMCostTracker, get_cost_tracker
from backend.services.user_behavior_analytics import (
    UserBehaviorAnalytics,
    get_behavior_analytics,
)
from autobot_shared.redis_client import RedisDatabase, get_redis_client

logger = logging.getLogger(__name__)


class MaintenancePriority(str, Enum):
    """Priority levels for maintenance recommendations."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ResourceType(str, Enum):
    """Types of resources to optimize."""

    LLM_TOKENS = "llm_tokens"
    AGENT_TASKS = "agent_tasks"
    MEMORY = "memory"
    CACHE = "cache"
    DATABASE = "database"


@dataclass
class MaintenanceRecommendation:
    """A predictive maintenance recommendation."""

    id: str
    title: str
    description: str
    priority: MaintenancePriority
    category: str
    affected_component: str
    predicted_issue: str
    confidence: float  # 0.0 to 1.0
    recommended_action: str
    estimated_impact: str
    detected_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "category": self.category,
            "affected_component": self.affected_component,
            "predicted_issue": self.predicted_issue,
            "confidence": round(self.confidence, 2),
            "recommended_action": self.recommended_action,
            "estimated_impact": self.estimated_impact,
            "detected_at": self.detected_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class ResourceOptimization:
    """A resource optimization recommendation."""

    id: str
    resource_type: ResourceType
    title: str
    current_usage: Dict[str, Any]
    recommended_change: str
    expected_savings: Dict[str, Any]
    implementation_effort: str  # low, medium, high
    priority: MaintenancePriority
    details: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "resource_type": self.resource_type.value,
            "title": self.title,
            "current_usage": self.current_usage,
            "recommended_change": self.recommended_change,
            "expected_savings": self.expected_savings,
            "implementation_effort": self.implementation_effort,
            "priority": self.priority.value,
            "details": self.details,
        }


class AnalyticsService:
    """
    Centralized analytics service providing a unified interface.

    Aggregates data from:
    - UserBehaviorAnalytics
    - AgentAnalytics
    - LLMCostTracker
    - System metrics

    Provides:
    - Unified dashboards
    - Cross-system insights
    - Predictive maintenance
    - Resource optimization
    """

    REDIS_PREFIX = "analytics_service:"
    MAINTENANCE_KEY = f"{REDIS_PREFIX}maintenance"
    OPTIMIZATION_KEY = f"{REDIS_PREFIX}optimization"

    def __init__(self):
        """Initialize analytics service with lazy-loaded dependencies."""
        self._behavior: Optional[UserBehaviorAnalytics] = None
        self._agents: Optional[AgentAnalytics] = None
        self._cost: Optional[LLMCostTracker] = None
        self._redis = None

    @property
    def behavior(self) -> UserBehaviorAnalytics:
        """Get user behavior analytics service."""
        if self._behavior is None:
            self._behavior = get_behavior_analytics()
        return self._behavior

    @property
    def agents(self) -> AgentAnalytics:
        """Get agent analytics service."""
        if self._agents is None:
            self._agents = get_agent_analytics()
        return self._agents

    @property
    def cost(self) -> LLMCostTracker:
        """Get cost tracker service."""
        if self._cost is None:
            self._cost = get_cost_tracker()
        return self._cost

    async def get_redis(self):
        """Get Redis client for analytics database."""
        if self._redis is None:
            self._redis = await get_redis_client(
                async_client=True, database=RedisDatabase.ANALYTICS
            )
        return self._redis

    # =========================================================================
    # UNIFIED DASHBOARD
    # =========================================================================

    def _build_agents_section(self, agent_metrics: List[Any]) -> Dict[str, Any]:
        """Build agents section for unified dashboard (Issue #665: extracted helper)."""
        return {
            "total_agents": len(agent_metrics),
            "total_tasks": sum(m.total_tasks for m in agent_metrics),
            "avg_success_rate": (
                sum(m.success_rate for m in agent_metrics) / len(agent_metrics)
                if agent_metrics
                else 0
            ),
            "top_performers": [
                m.agent_id
                for m in sorted(
                    agent_metrics, key=lambda x: x.success_rate, reverse=True
                )[:3]
            ],
        }

    def _build_maintenance_section(self, maintenance_recs: List[Any]) -> Dict[str, Any]:
        """Build maintenance section for unified dashboard (Issue #665: extracted helper)."""
        return {
            "total_recommendations": len(maintenance_recs),
            "critical_count": sum(
                1
                for r in maintenance_recs
                if r.priority == MaintenancePriority.CRITICAL
            ),
            "high_priority": [
                r.to_dict()
                for r in maintenance_recs
                if r.priority
                in [MaintenancePriority.CRITICAL, MaintenancePriority.HIGH]
            ][:5],
        }

    async def get_unified_dashboard(self, days: int = 30) -> Dict[str, Any]:
        """
        Get unified dashboard data aggregating all analytics sources.

        Args:
            days: Number of days to include in analysis

        Returns:
            Comprehensive dashboard data
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        # Fetch all data concurrently
        (
            cost_summary,
            cost_trends,
            agent_metrics,
            engagement,
            maintenance_recs,
            optimization_recs,
        ) = await asyncio.gather(
            self.cost.get_cost_summary(start_date, end_date),
            self.cost.get_cost_trends(days),
            self.agents.get_all_agents_metrics(),
            self.behavior.get_engagement_metrics(),
            self.get_predictive_maintenance(),
            self.get_resource_optimizations(),
        )

        # Calculate health score
        health_score = await self._calculate_system_health(
            cost_trends, agent_metrics, engagement
        )

        return {
            "generated_at": datetime.utcnow().isoformat(),
            "period_days": days,
            "health": {
                "score": health_score,
                "grade": self._get_grade(health_score),
                "status": self._get_health_status(health_score),
            },
            "cost": {
                "total_usd": cost_summary.get("total_cost_usd", 0),
                "daily_avg_usd": cost_summary.get("avg_daily_cost", 0),
                "trend": cost_trends.get("trend", "stable"),
                "growth_rate": cost_trends.get("growth_rate_percent", 0),
            },
            "agents": self._build_agents_section(agent_metrics),
            "engagement": {
                "total_sessions": engagement.get("metrics", {}).get(
                    "total_sessions", 0
                ),
                "page_views": engagement.get("metrics", {}).get("total_page_views", 0),
                "most_popular": engagement.get("most_popular_feature"),
            },
            "maintenance": self._build_maintenance_section(maintenance_recs),
            "optimization": {
                "total_recommendations": len(optimization_recs),
                "estimated_savings": self._sum_savings(optimization_recs),
                "top_recommendations": [r.to_dict() for r in optimization_recs[:3]],
            },
        }

    async def _calculate_system_health(
        self,
        cost_trends: Dict[str, Any],
        agent_metrics: List[Any],
        engagement: Dict[str, Any],
    ) -> float:
        """Calculate overall system health score (0-100)."""
        scores = []

        # Cost health (lower growth is better)
        growth_rate = cost_trends.get("growth_rate_percent", 0)
        cost_score = max(0, 100 - abs(growth_rate) * 2)
        scores.append(cost_score)

        # Agent health (success rate)
        if agent_metrics:
            agent_score = sum(m.success_rate for m in agent_metrics) / len(
                agent_metrics
            )
            scores.append(agent_score)

        # Engagement health (based on session activity)
        metrics = engagement.get("metrics", {})
        if metrics.get("total_sessions", 0) > 0:
            pages_per_session = metrics.get("pages_per_session", 0)
            engagement_score = min(100, pages_per_session * 20)
            scores.append(engagement_score)

        return round(statistics.mean(scores) if scores else 50, 1)

    def _get_grade(self, score: float) -> str:
        """Convert score to letter grade."""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        return "F"

    def _get_health_status(self, score: float) -> str:
        """Get health status from score."""
        if score >= 80:
            return "healthy"
        elif score >= 60:
            return "warning"
        return "critical"

    def _sum_savings(
        self, recommendations: List[ResourceOptimization]
    ) -> Dict[str, float]:
        """Sum up expected savings from optimization recommendations."""
        savings = {"cost_usd": 0, "performance_percent": 0}
        for rec in recommendations:
            expected = rec.expected_savings
            savings["cost_usd"] += expected.get("cost_usd", 0)
            savings["performance_percent"] += expected.get("performance_percent", 0)
        return savings

    # =========================================================================
    # PREDICTIVE MAINTENANCE
    # =========================================================================

    async def get_predictive_maintenance(self) -> List[MaintenanceRecommendation]:
        """
        Analyze system metrics and predict maintenance needs.

        Returns:
            List of maintenance recommendations sorted by priority
        """
        # Issue #619: Parallelize independent maintenance analyses
        agent_recs, cost_recs, resource_recs = await asyncio.gather(
            self._analyze_agent_maintenance(),
            self._analyze_cost_maintenance(),
            self._analyze_resource_maintenance(),
        )
        recommendations = []
        recommendations.extend(agent_recs)
        recommendations.extend(cost_recs)
        recommendations.extend(resource_recs)

        # Sort by priority
        priority_order = {
            MaintenancePriority.CRITICAL: 0,
            MaintenancePriority.HIGH: 1,
            MaintenancePriority.MEDIUM: 2,
            MaintenancePriority.LOW: 3,
        }
        recommendations.sort(key=lambda r: (priority_order[r.priority], -r.confidence))

        return recommendations

    async def _analyze_agent_maintenance(self) -> List[MaintenanceRecommendation]:
        """Analyze agent performance for maintenance recommendations."""
        recommendations = []
        agent_metrics = await self.agents.get_all_agents_metrics()

        for agent in agent_metrics:
            # High error rate detection
            if agent.error_rate > 20:
                recommendations.append(
                    MaintenanceRecommendation(
                        id=f"agent-error-{agent.agent_id}",
                        title=f"High Error Rate: {agent.agent_id}",
                        description=f"Agent {agent.agent_id} has an error rate of {agent.error_rate:.1f}%",
                        priority=MaintenancePriority.HIGH
                        if agent.error_rate > 30
                        else MaintenancePriority.MEDIUM,
                        category="agent_performance",
                        affected_component=f"agent:{agent.agent_id}",
                        predicted_issue="Continued degradation may lead to task failures",
                        confidence=min(0.9, agent.error_rate / 100 + 0.3),
                        recommended_action="Review agent logs, check for pattern issues, consider retraining",
                        estimated_impact=f"Affects {agent.total_tasks} tasks",
                        metadata={
                            "error_rate": agent.error_rate,
                            "agent_type": agent.agent_type,
                        },
                    )
                )

            # Slow performance detection
            if agent.avg_duration_ms > 10000:  # > 10 seconds
                recommendations.append(
                    MaintenanceRecommendation(
                        id=f"agent-slow-{agent.agent_id}",
                        title=f"Slow Performance: {agent.agent_id}",
                        description=f"Agent {agent.agent_id} average duration is {agent.avg_duration_ms/1000:.1f}s",
                        priority=MaintenancePriority.MEDIUM,
                        category="agent_performance",
                        affected_component=f"agent:{agent.agent_id}",
                        predicted_issue="Performance degradation affecting user experience",
                        confidence=0.7,
                        recommended_action="Profile agent execution, optimize prompts, consider caching",
                        estimated_impact="Increased latency for end users",
                        metadata={"avg_duration_ms": agent.avg_duration_ms},
                    )
                )

            # Timeout issues
            if agent.timeout_tasks > 5 and agent.total_tasks > 0:
                timeout_rate = (agent.timeout_tasks / agent.total_tasks) * 100
                if timeout_rate > 5:
                    recommendations.append(
                        MaintenanceRecommendation(
                            id=f"agent-timeout-{agent.agent_id}",
                            title=f"Frequent Timeouts: {agent.agent_id}",
                            description=f"Agent {agent.agent_id} has {timeout_rate:.1f}% timeout rate",
                            priority=MaintenancePriority.HIGH,
                            category="reliability",
                            affected_component=f"agent:{agent.agent_id}",
                            predicted_issue="Tasks timing out may indicate resource constraints",
                            confidence=0.85,
                            recommended_action="Increase timeout limits, optimize task complexity, check resources",
                            estimated_impact=f"{agent.timeout_tasks} tasks affected",
                            metadata={
                                "timeout_tasks": agent.timeout_tasks,
                                "timeout_rate": timeout_rate,
                            },
                        )
                    )

        return recommendations

    async def _analyze_cost_maintenance(self) -> List[MaintenanceRecommendation]:
        """Analyze cost patterns for maintenance recommendations."""
        recommendations = []
        trends = await self.cost.get_cost_trends(30)

        # Rapidly increasing costs
        growth_rate = trends.get("growth_rate_percent", 0)
        if growth_rate > 20:
            recommendations.append(
                MaintenanceRecommendation(
                    id="cost-growth-alert",
                    title="Rapid Cost Increase Detected",
                    description=f"LLM costs are increasing at {growth_rate:.1f}% rate",
                    priority=MaintenancePriority.HIGH
                    if growth_rate > 50
                    else MaintenancePriority.MEDIUM,
                    category="cost_management",
                    affected_component="llm_provider",
                    predicted_issue="Budget may be exceeded if trend continues",
                    confidence=0.85,
                    recommended_action="Review usage patterns, implement cost controls, optimize prompts",
                    estimated_impact=(
                        f"Projected cost increase of "
                        f"${trends.get('total_cost_usd', 0) * growth_rate / 100:.2f}"
                    ),
                    metadata={"growth_rate": growth_rate, "trend": trends.get("trend")},
                )
            )

        return recommendations

    async def _analyze_resource_maintenance(self) -> List[MaintenanceRecommendation]:
        """Analyze system resources for maintenance recommendations."""
        recommendations = []

        try:
            redis = await self.get_redis()
            info = await redis.info("memory")

            # Check Redis memory usage
            used_memory = info.get("used_memory", 0)
            max_memory = info.get("maxmemory", 0)

            if max_memory > 0:
                memory_pct = (used_memory / max_memory) * 100
                if memory_pct > 80:
                    recommendations.append(
                        MaintenanceRecommendation(
                            id="redis-memory-high",
                            title="High Redis Memory Usage",
                            description=f"Redis is using {memory_pct:.1f}% of allocated memory",
                            priority=MaintenancePriority.HIGH
                            if memory_pct > 90
                            else MaintenancePriority.MEDIUM,
                            category="infrastructure",
                            affected_component="redis",
                            predicted_issue="Memory exhaustion may cause cache evictions or failures",
                            confidence=0.9,
                            recommended_action=(
                                "Clean up old data, increase memory allocation, "
                                "review retention policies"
                            ),
                            estimated_impact="May affect caching and real-time features",
                            metadata={
                                "used_memory_mb": used_memory / 1024 / 1024,
                                "memory_percent": memory_pct,
                            },
                        )
                    )
        except Exception as e:
            logger.warning("Failed to check Redis memory: %s", e)

        return recommendations

    # =========================================================================
    # RESOURCE OPTIMIZATION
    # =========================================================================

    async def get_resource_optimizations(self) -> List[ResourceOptimization]:
        """
        Analyze resource usage and provide optimization recommendations.

        Returns:
            List of optimization recommendations sorted by impact
        """
        # Issue #619: Parallelize independent optimization analyses
        token_opts, agent_opts, cache_opts = await asyncio.gather(
            self._analyze_token_optimization(),
            self._analyze_agent_optimization(),
            self._analyze_cache_optimization(),
        )
        recommendations = []
        recommendations.extend(token_opts)
        recommendations.extend(agent_opts)
        recommendations.extend(cache_opts)

        # Sort by priority then expected savings
        priority_order = {
            MaintenancePriority.CRITICAL: 0,
            MaintenancePriority.HIGH: 1,
            MaintenancePriority.MEDIUM: 2,
            MaintenancePriority.LOW: 3,
        }
        recommendations.sort(
            key=lambda r: (
                priority_order[r.priority],
                -r.expected_savings.get("cost_usd", 0),
            )
        )

        return recommendations

    async def _analyze_token_optimization(self) -> List[ResourceOptimization]:
        """Analyze token usage for optimization opportunities."""
        recommendations = []
        summary = await self.cost.get_cost_summary()

        by_model = summary.get("by_model", {})

        # Find expensive models that could be replaced
        for model, data in by_model.items():
            cost = data.get("cost_usd", 0)
            input_tokens = data.get("input_tokens", 0)
            output_tokens = data.get("output_tokens", 0)
            call_count = data.get("call_count", 0)

            if cost > 10:  # Models costing more than $10
                # Check for potential model substitution
                model_lower = model.lower()
                if "opus" in model_lower or "gpt-4" in model_lower:
                    recommendations.append(
                        ResourceOptimization(
                            id=f"model-substitute-{model[:20]}",
                            resource_type=ResourceType.LLM_TOKENS,
                            title=f"Consider cheaper model for {model}",
                            current_usage={
                                "model": model,
                                "cost_usd": cost,
                                "calls": call_count,
                                "input_tokens": input_tokens,
                                "output_tokens": output_tokens,
                            },
                            recommended_change="Use Claude Sonnet or GPT-4o for simpler tasks",
                            expected_savings={
                                "cost_usd": cost * 0.4,  # Estimate 40% savings
                                "performance_percent": -5,  # Slight quality tradeoff
                            },
                            implementation_effort="medium",
                            priority=MaintenancePriority.MEDIUM,
                            details="Analyze task complexity and route simpler tasks to cheaper models",
                        )
                    )

            # High token usage without caching
            if input_tokens > 1000000 and call_count > 100:
                avg_input = input_tokens / call_count
                if avg_input > 5000:  # Large prompts
                    recommendations.append(
                        ResourceOptimization(
                            id=f"prompt-caching-{model[:20]}",
                            resource_type=ResourceType.LLM_TOKENS,
                            title=f"Enable prompt caching for {model}",
                            current_usage={
                                "model": model,
                                "avg_input_tokens": avg_input,
                                "total_input_tokens": input_tokens,
                            },
                            recommended_change="Implement prompt caching for repeated system prompts",
                            expected_savings={
                                "cost_usd": cost * 0.25,
                                "performance_percent": 15,
                            },
                            implementation_effort="low",
                            priority=MaintenancePriority.HIGH,
                            details="Anthropic and OpenAI support prompt caching for repeated content",
                        )
                    )

        return recommendations

    async def _analyze_agent_optimization(self) -> List[ResourceOptimization]:
        """Analyze agent usage for optimization opportunities."""
        recommendations = []
        agent_metrics = await self.agents.get_all_agents_metrics()

        for agent in agent_metrics:
            # Agents with many retries (high task count but low success)
            if agent.total_tasks > 50 and agent.success_rate < 80:
                wasted_tasks = agent.failed_tasks + agent.timeout_tasks
                if wasted_tasks > 10:
                    recommendations.append(
                        ResourceOptimization(
                            id=f"agent-retry-{agent.agent_id}",
                            resource_type=ResourceType.AGENT_TASKS,
                            title=f"Reduce failed tasks for {agent.agent_id}",
                            current_usage={
                                "agent_id": agent.agent_id,
                                "total_tasks": agent.total_tasks,
                                "failed_tasks": agent.failed_tasks,
                                "timeout_tasks": agent.timeout_tasks,
                                "success_rate": agent.success_rate,
                            },
                            recommended_change="Improve error handling and task validation",
                            expected_savings={
                                "cost_usd": wasted_tasks
                                * 0.01,  # Estimate $0.01 per task
                                "performance_percent": 10,
                            },
                            implementation_effort="medium",
                            priority=MaintenancePriority.MEDIUM,
                            details=f"Agent has {wasted_tasks} wasted task executions",
                        )
                    )

            # Slow agents that could benefit from optimization
            if agent.avg_duration_ms > 5000 and agent.total_tasks > 20:
                recommendations.append(
                    ResourceOptimization(
                        id=f"agent-speed-{agent.agent_id}",
                        resource_type=ResourceType.AGENT_TASKS,
                        title=f"Optimize {agent.agent_id} execution time",
                        current_usage={
                            "agent_id": agent.agent_id,
                            "avg_duration_ms": agent.avg_duration_ms,
                            "total_tasks": agent.total_tasks,
                        },
                        recommended_change="Profile and optimize agent prompts and logic",
                        expected_savings={
                            "cost_usd": 0,
                            "performance_percent": 30,
                        },
                        implementation_effort="high",
                        priority=MaintenancePriority.LOW,
                        details=(
                            f"Reducing {agent.avg_duration_ms}ms to 2000ms would save "
                            f"{(agent.avg_duration_ms - 2000) * agent.total_tasks / 1000}s"
                        ),
                    )
                )

        return recommendations

    async def _analyze_cache_optimization(self) -> List[ResourceOptimization]:
        """Analyze cache usage for optimization opportunities."""
        recommendations = []

        try:
            redis = await self.get_redis()
            info = await redis.info()

            # Check hit rate
            hits = info.get("keyspace_hits", 0)
            misses = info.get("keyspace_misses", 0)
            total = hits + misses

            if total > 1000:
                hit_rate = (hits / total) * 100
                if hit_rate < 70:
                    recommendations.append(
                        ResourceOptimization(
                            id="cache-hit-rate",
                            resource_type=ResourceType.CACHE,
                            title="Improve cache hit rate",
                            current_usage={
                                "hit_rate": hit_rate,
                                "hits": hits,
                                "misses": misses,
                            },
                            recommended_change="Review cache key strategies and TTL settings",
                            expected_savings={
                                "cost_usd": misses * 0.0001,
                                "performance_percent": 20,
                            },
                            implementation_effort="medium",
                            priority=MaintenancePriority.MEDIUM,
                            details=f"Current hit rate is {hit_rate:.1f}%, target is 80%+",
                        )
                    )

        except Exception as e:
            logger.warning("Failed to analyze cache: %s", e)

        return recommendations

    # =========================================================================
    # CUSTOM REPORTS
    # =========================================================================

    async def generate_custom_report(
        self,
        report_type: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        include_sections: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a custom analytics report.

        Args:
            report_type: Type of report (executive, technical, cost, performance)
            start_date: Report period start
            end_date: Report period end
            include_sections: Specific sections to include

        Returns:
            Custom report data
        """
        end_date = end_date or datetime.utcnow()
        start_date = start_date or (end_date - timedelta(days=30))
        days = (end_date - start_date).days

        report = {
            "report_type": report_type,
            "generated_at": datetime.utcnow().isoformat(),
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": days,
            },
            "sections": {},
        }

        sections = include_sections or ["cost", "agents", "behavior", "maintenance"]

        # Fetch data for requested sections concurrently
        tasks = {}
        if "cost" in sections:
            tasks["cost"] = self.cost.get_cost_summary(start_date, end_date)
        if "agents" in sections:
            tasks["agents"] = self.agents.compare_agents()
        if "behavior" in sections:
            tasks["behavior"] = self.behavior.get_engagement_metrics()
        if "maintenance" in sections:
            tasks["maintenance"] = self.get_predictive_maintenance()
        if "optimization" in sections:
            tasks["optimization"] = self.get_resource_optimizations()

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        for (section, _), result in zip(tasks.items(), results):
            if isinstance(result, Exception):
                report["sections"][section] = {"error": str(result)}
            elif section == "maintenance":
                report["sections"][section] = [r.to_dict() for r in result]
            elif section == "optimization":
                report["sections"][section] = [r.to_dict() for r in result]
            else:
                report["sections"][section] = result

        # Add executive summary for executive reports
        if report_type == "executive":
            report["executive_summary"] = await self._generate_executive_summary(
                report["sections"]
            )

        return report

    async def _generate_executive_summary(
        self, sections: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate executive summary from report sections."""
        summary = {
            "highlights": [],
            "concerns": [],
            "recommendations": [],
        }

        # Cost highlights
        cost_data = sections.get("cost", {})
        total_cost = cost_data.get("total_cost_usd", 0)
        if total_cost > 0:
            summary["highlights"].append(f"Total LLM spend: ${total_cost:.2f}")

        # Agent performance
        agent_data = sections.get("agents", {})
        if agent_data.get("summary"):
            avg_success = agent_data["summary"].get("avg_success_rate", 0)
            summary["highlights"].append(
                f"Average agent success rate: {avg_success:.1f}%"
            )
            if avg_success < 80:
                summary["concerns"].append("Agent success rate below 80% target")

        # Maintenance concerns
        maintenance = sections.get("maintenance", [])
        critical_count = sum(1 for m in maintenance if m.get("priority") == "critical")
        if critical_count > 0:
            summary["concerns"].append(
                f"{critical_count} critical maintenance items require attention"
            )

        # Optimization opportunities
        optimization = sections.get("optimization", [])
        if optimization:
            total_savings = sum(
                o.get("expected_savings", {}).get("cost_usd", 0) for o in optimization
            )
            if total_savings > 0:
                summary["recommendations"].append(
                    f"Potential cost savings of ${total_savings:.2f} identified"
                )

        return summary


# Singleton instance (thread-safe)
import threading

_analytics_service: Optional[AnalyticsService] = None
_analytics_service_lock = threading.Lock()


def get_analytics_service() -> AnalyticsService:
    """Get the singleton AnalyticsService instance (thread-safe)."""
    global _analytics_service
    if _analytics_service is None:
        with _analytics_service_lock:
            # Double-check after acquiring lock
            if _analytics_service is None:
                _analytics_service = AnalyticsService()
    return _analytics_service
