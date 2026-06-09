# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Confounder Control Analyzer for Agent Stratified Comparison.

Implements stratified analysis to control for confounders in agent performance
evaluation. Enables fair comparison of agents by partitioning execution history
by confounder values and detecting confounding effects.

Features:
- Stratification by confounder values (e.g., query_complexity, system_load)
- Within-stratum comparison for fairness
- Confounding detection (metric variance across strata)
- True effect estimation after controlling for confounders
- Confidence scoring based on sample size

Related Issues: #59 (Advanced Analytics & Business Intelligence)
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import RedisDatabase
from autobot_shared.redis_mixin import AsyncRedisClientMixin
from autobot_shared.singleton_factory import lazy_singleton

logger = get_logger(__name__)


@dataclass
class StratumMetrics:
    """Metrics for a single stratum (confounder value group)"""

    stratum_value: str
    task_count: int
    success_count: int
    failed_count: int
    metric_value: float  # The actual metric (success_rate, avg_duration, etc.)
    confidence: float  # Confidence based on sample size (0.0-1.0)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StratifiedComparison:
    """Result of stratified comparison between two agents"""

    agent_a: str
    agent_b: str
    metric: str  # The metric being compared (success_rate, avg_duration, etc.)
    confounders: List[str]  # List of confounders analyzed
    overall_advantage: float  # Agent A's advantage in the metric (-1.0 to 1.0)
    strata: Dict[str, Tuple[StratumMetrics, StratumMetrics]]  # agent_a, agent_b metrics per stratum
    confounded_effect: bool  # True if confounding detected (metric varies by stratum)
    confounding_strength: float  # Strength of confounding effect (0.0-1.0)
    true_effect: float  # Agent A's advantage after controlling for confounders
    true_effect_confidence: float  # Confidence in true effect estimate
    interpretation: str  # Human-readable summary of findings
    sample_coverage: float  # Fraction of tasks used in analysis (0.0-1.0)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "agent_a": self.agent_a,
            "agent_b": self.agent_b,
            "metric": self.metric,
            "confounders": self.confounders,
            "overall_advantage": round(self.overall_advantage, 3),
            "confounded_effect": self.confounded_effect,
            "confounding_strength": round(self.confounding_strength, 3),
            "true_effect": round(self.true_effect, 3),
            "true_effect_confidence": round(self.true_effect_confidence, 3),
            "interpretation": self.interpretation,
            "sample_coverage": round(self.sample_coverage, 3),
            "strata": {
                k: {
                    "agent_a": {
                        "stratum_value": v[0].stratum_value,
                        "task_count": v[0].task_count,
                        "success_count": v[0].success_count,
                        "metric_value": round(v[0].metric_value, 3),
                        "confidence": round(v[0].confidence, 3),
                    },
                    "agent_b": {
                        "stratum_value": v[1].stratum_value,
                        "task_count": v[1].task_count,
                        "success_count": v[1].success_count,
                        "metric_value": round(v[1].metric_value, 3),
                        "confidence": round(v[1].confidence, 3),
                    },
                }
                for k, v in self.strata.items()
            },
        }


class ConfounderControlAnalyzer(AsyncRedisClientMixin):
    """Analyzes agent performance with confounder control via stratification."""

    _redis_database = RedisDatabase.ANALYTICS

    REDIS_KEY_PREFIX = "agent_analytics:"
    AGENT_HISTORY_KEY = f"{REDIS_KEY_PREFIX}history"

    # Confounder thresholds and bins
    CONFOUNDER_BINS = {
        "query_complexity": {"low": 0, "medium": 1, "high": 2},
        "knowledge_base_size": {"small": 0, "medium": 1, "large": 2},
        "network_latency_ms": {"low": 100, "medium": 500, "high": float("inf")},
        "system_load": {"low": 0.3, "medium": 0.7, "high": float("inf")},
        "task_priority": {"low": 1, "medium": 2, "high": 3},
    }

    async def get_redis(self):
        """Get async Redis client"""
        return await self._get_redis()

    async def compare_agents_stratified(
        self,
        agent_a: str,
        agent_b: str,
        metric: str = "success_rate",
        confounders: List[str] | None = None,
        limit: int = 1000,
    ) -> StratifiedComparison | None:
        """
        Compare two agents with confounder control via stratification.

        Args:
            agent_a: First agent ID
            agent_b: Second agent ID
            metric: Metric to compare (success_rate, avg_duration_ms, error_rate)
            confounders: List of confounders to control for
            limit: Max tasks to retrieve per agent

        Returns:
            StratifiedComparison with fairness-controlled metrics, or None if insufficient data
        """
        if confounders is None:
            confounders = ["query_complexity"]

        # Get task histories for both agents
        tasks_a = await self._get_agent_history(agent_a, limit)
        tasks_b = await self._get_agent_history(agent_b, limit)

        if not tasks_a or not tasks_b:
            logger.warning(
                "Insufficient data for comparison: agent_a=%s (%d tasks), agent_b=%s (%d tasks)",
                agent_a,
                len(tasks_a),
                agent_b,
                len(tasks_b),
            )
            return None

        # Stratify by each confounder and compute metrics
        strata_results = {}

        for confounder in confounders:
            strata_a = await self.stratify_by_confounder(tasks_a, confounder)
            strata_b = await self.stratify_by_confounder(tasks_b, confounder)

            # Compute metrics for each stratum
            for stratum_value in set(strata_a.keys()) & set(strata_b.keys()):
                metrics_a = self._compute_stratum_metrics(strata_a[stratum_value], metric, stratum_value)
                metrics_b = self._compute_stratum_metrics(strata_b[stratum_value], metric, stratum_value)

                if metrics_a and metrics_b:
                    strata_results[f"{confounder}:{stratum_value}"] = (
                        metrics_a,
                        metrics_b,
                    )

        if not strata_results:
            logger.warning(
                "No overlapping strata for comparison: agent_a=%s, agent_b=%s, confounders=%s",
                agent_a,
                agent_b,
                confounders,
            )
            return None

        # Compute overall and true effects
        overall_advantage = self._compute_overall_advantage(metric, strata_results)
        true_effect, true_effect_confidence = self._estimate_true_effect(metric, strata_results)
        confounded, confounding_strength = self._detect_confounding(metric, strata_results)

        sample_coverage = len(strata_results) / (len(confounders) * 3)  # Assume max 3 strata per confounder

        interpretation = self._generate_interpretation(
            agent_a,
            agent_b,
            metric,
            overall_advantage,
            true_effect,
            confounded,
            confounding_strength,
        )

        return StratifiedComparison(
            agent_a=agent_a,
            agent_b=agent_b,
            metric=metric,
            confounders=confounders,
            overall_advantage=overall_advantage,
            strata=strata_results,
            confounded_effect=confounded,
            confounding_strength=confounding_strength,
            true_effect=true_effect,
            true_effect_confidence=true_effect_confidence,
            interpretation=interpretation,
            sample_coverage=sample_coverage,
        )

    async def stratify_by_confounder(
        self, tasks: List[Dict[str, Any]], confounder: str
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Partition tasks by confounder value.

        Args:
            tasks: List of task records
            confounder: Confounder name (e.g., 'query_complexity')

        Returns:
            Dict mapping stratum values to task lists
        """
        strata = {}

        for task in tasks:
            stratum_value = self._extract_confounder_value(task, confounder)
            if stratum_value:
                if stratum_value not in strata:
                    strata[stratum_value] = []
                strata[stratum_value].append(task)

        return strata

    def _extract_confounder_value(self, task: Dict[str, Any], confounder: str) -> str | None:
        """Extract and bin confounder value from task record."""
        metadata = task.get("metadata", {})

        # Handle each confounder type
        if confounder == "query_complexity":
            complexity = metadata.get("query_complexity", 1)
            if complexity <= 1:
                return "low"
            elif complexity <= 2:
                return "medium"
            else:
                return "high"

        elif confounder == "knowledge_base_size":
            kb_size = metadata.get("knowledge_base_size", 1000)
            if kb_size < 5000:
                return "small"
            elif kb_size < 50000:
                return "medium"
            else:
                return "large"

        elif confounder == "network_latency_ms":
            latency = metadata.get("network_latency_ms", 100)
            if latency < 100:
                return "low"
            elif latency < 500:
                return "medium"
            else:
                return "high"

        elif confounder == "system_load":
            load = metadata.get("system_load", 0.5)
            if load < 0.3:
                return "low"
            elif load < 0.7:
                return "medium"
            else:
                return "high"

        elif confounder == "task_priority":
            priority = metadata.get("task_priority", 2)
            if priority <= 1:
                return "low"
            elif priority <= 2:
                return "medium"
            else:
                return "high"

        return None

    def _compute_stratum_metrics(
        self,
        tasks: List[Dict[str, Any]],
        metric: str,
        stratum_value: str,
    ) -> StratumMetrics | None:
        """Compute metrics for a stratum."""
        if not tasks:
            return None

        completed = sum(1 for t in tasks if t.get("status") == "completed")
        failed = sum(1 for t in tasks if t.get("status") == "failed")
        total = len(tasks)

        # Compute requested metric
        if metric == "success_rate":
            metric_value = (completed / total) * 100 if total > 0 else 0
        elif metric == "error_rate":
            metric_value = (failed / total) * 100 if total > 0 else 0
        elif metric == "avg_duration_ms":
            durations = [t.get("duration_ms", 0) for t in tasks if t.get("duration_ms")]
            metric_value = sum(durations) / len(durations) if durations else 0
        else:
            metric_value = 0

        # Confidence based on sample size (sqrt(n) scaled to 0-1)
        # Min confidence 0.3 for n=10, max confidence 1.0 for n=100+
        confidence = min(1.0, 0.3 + (total**0.5) / 20)

        return StratumMetrics(
            stratum_value=stratum_value,
            task_count=total,
            success_count=completed,
            failed_count=failed,
            metric_value=metric_value,
            confidence=confidence,
        )

    def _compute_overall_advantage(
        self,
        metric: str,
        strata_results: Dict[str, Tuple[StratumMetrics, StratumMetrics]],
    ) -> float:
        """
        Compute agent A's overall advantage (ignoring confounders).

        For higher-is-better metrics (success_rate): advantage = A - B
        For lower-is-better metrics (error_rate, avg_duration_ms): advantage = B - A
        """
        if not strata_results:
            return 0.0

        # Aggregate metrics across all strata
        total_a = 0.0
        total_b = 0.0
        count = 0

        for metrics_a, metrics_b in strata_results.values():
            # Weight by confidence
            total_a += metrics_a.metric_value * metrics_a.confidence
            total_b += metrics_b.metric_value * metrics_b.confidence
            count += metrics_a.confidence + metrics_b.confidence

        if count == 0:
            return 0.0

        avg_a = total_a / count
        avg_b = total_b / count

        # Direction depends on metric type
        if metric in ["success_rate"]:
            return (avg_a - avg_b) / 100 if avg_b > 0 else 0
        else:  # error_rate, avg_duration_ms
            return (avg_b - avg_a) / (avg_b + 1) if (avg_b + avg_a) > 0 else 0

    def _estimate_true_effect(
        self,
        metric: str,
        strata_results: Dict[str, Tuple[StratumMetrics, StratumMetrics]],
    ) -> Tuple[float, float]:
        """
        Estimate true effect using Mantel-Haenszel-like stratified analysis.

        Returns:
            (true_effect, confidence) tuple
        """
        if not strata_results:
            return 0.0, 0.0

        # Within-stratum differences
        differences = []
        weights = []

        for metrics_a, metrics_b in strata_results.values():
            if metrics_a.task_count >= 2 and metrics_b.task_count >= 2:
                diff = metrics_a.metric_value - metrics_b.metric_value
                # Weight by sample size and confidence
                weight = (metrics_a.task_count + metrics_b.task_count) * metrics_a.confidence * metrics_b.confidence
                differences.append(diff)
                weights.append(weight)

        if not differences:
            return 0.0, 0.0

        # Weighted average of within-stratum effects
        total_weight = sum(weights)
        true_effect = sum(d * w for d, w in zip(differences, weights)) / total_weight if total_weight > 0 else 0.0

        # Confidence based on consistency of within-stratum effects
        # If all strata show same direction → high confidence
        same_direction = all((d > 0) == (differences[0] > 0) for d in differences)
        consistency = 1.0 if same_direction else 0.5
        stratum_factor = min(1.0, len(differences) / 3)  # More strata = higher confidence
        confidence = min(1.0, consistency * stratum_factor)

        return true_effect / 100 if true_effect > 0 else true_effect, confidence

    def _detect_confounding(
        self,
        metric: str,
        strata_results: Dict[str, Tuple[StratumMetrics, StratumMetrics]],
    ) -> Tuple[bool, float]:
        """
        Detect if a confounder is active (metric varies across strata).

        Returns:
            (confounding_detected, confounding_strength) tuple
        """
        if len(strata_results) < 2:
            return False, 0.0

        metric_values = []
        for metrics_a, metrics_b in strata_results.values():
            metric_values.append(metrics_a.metric_value)
            metric_values.append(metrics_b.metric_value)

        if not metric_values:
            return False, 0.0

        # Compute coefficient of variation (std / mean)
        mean = sum(metric_values) / len(metric_values)
        if mean == 0:
            return False, 0.0

        variance = sum((v - mean) ** 2 for v in metric_values) / len(metric_values)
        std_dev = variance**0.5
        cv = std_dev / abs(mean)

        # Confounding strength: CV > 0.15 → confounding detected
        confounded = cv > 0.15
        strength = min(1.0, cv)  # Cap at 1.0

        return confounded, strength

    def _generate_interpretation(
        self,
        agent_a: str,
        agent_b: str,
        metric: str,
        overall_advantage: float,
        true_effect: float,
        confounded: bool,
        confounding_strength: float,
    ) -> str:
        """Generate human-readable interpretation of results."""
        parts = []

        # Overall effect
        if abs(overall_advantage) < 0.01:
            parts.append(f"{agent_a} and {agent_b} perform similarly on {metric}.")
        elif overall_advantage > 0:
            pct = abs(overall_advantage) * 100
            parts.append(f"{agent_a} shows {pct:.1f}% advantage over {agent_b} on {metric}.")
        else:
            pct = abs(overall_advantage) * 100
            parts.append(f"{agent_b} shows {pct:.1f}% advantage over {agent_a} on {metric}.")

        # Confounding detection
        if confounded:
            parts.append(
                f"Confounding detected (strength: {confounding_strength:.2f}). "
                f"Agent performance varies significantly across task conditions."
            )

            # True effect after control
            if abs(true_effect - overall_advantage) > 0.01:
                parts.append(f"After controlling for confounders, the true effect is {true_effect:.3f}.")
        else:
            parts.append("No significant confounding detected. Observed advantage is likely genuine.")

        return " ".join(parts)

    async def _get_agent_history(self, agent_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get task history for an agent from Redis."""
        try:
            redis = await self.get_redis()
            agent_key = f"{self.AGENT_HISTORY_KEY}:{agent_id}"
            records = await redis.lrange(agent_key, 0, limit - 1)

            results = []
            for r in records:
                if isinstance(r, bytes):
                    results.append(json.loads(r.decode("utf-8")))
                else:
                    results.append(json.loads(r))
            return results

        except Exception as e:
            logger.error("Failed to get agent history for %s: %s", agent_id, e)
            return []


get_confounder_control_analyzer = lazy_singleton(ConfounderControlAnalyzer)
