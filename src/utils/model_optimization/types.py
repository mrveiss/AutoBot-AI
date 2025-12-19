# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Model Optimization Types Module

Issue #381: Extracted from model_optimizer.py god class refactoring.
Contains enums, dataclasses, and type definitions for model optimization.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskComplexity(Enum):
    """Task complexity levels for model selection."""

    SIMPLE = "simple"  # Basic responses, factual questions
    MODERATE = "moderate"  # Analysis, reasoning, explanations
    COMPLEX = "complex"  # Advanced reasoning, code generation, long-form content
    SPECIALIZED = "specialized"  # Domain-specific tasks requiring maximum capability


class ModelPerformanceLevel(Enum):
    """Model performance classification."""

    LIGHTWEIGHT = "lightweight"  # < 2B parameters
    STANDARD = "standard"  # 2-8B parameters
    ADVANCED = "advanced"  # 8B+ parameters
    SPECIALIZED = "specialized"  # Domain-specific models


# Issue #380: Module-level frozensets to avoid repeated list creation
CODE_TASK_TYPES = frozenset({"code", "programming", "development"})
CODE_COMPLEXITY_KEYWORDS = frozenset({"complex", "algorithm", "optimize", "architecture"})


@dataclass
class SystemResources:
    """System resource measurements with behavior methods (Tell Don't Ask)."""

    cpu_percent: float
    memory_percent: float
    available_memory_gb: float

    def allows_large_models(self) -> bool:
        """Tell if system can handle large models."""
        return self.memory_percent < 70 and self.cpu_percent < 60

    def get_max_model_size_gb(self) -> float:
        """Tell what max model size system can handle."""
        if self.cpu_percent > 80 or self.available_memory_gb < 4:
            return 4.0
        elif self.available_memory_gb < 8:
            return 8.0
        return float("inf")

    def to_dict(self) -> Dict[str, float]:
        """Convert to dict for backward compatibility."""
        return {
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "available_memory_gb": self.available_memory_gb,
        }


@dataclass
class TaskRequest:
    """A request for model optimization."""

    query: str
    task_type: str  # 'chat', 'code', 'analysis', etc.
    max_response_time: Optional[float] = None
    min_quality: Optional[float] = None
    context_length: int = 0
    user_preference: Optional[str] = None

    def analyze_complexity(
        self, complexity_keywords: Dict[TaskComplexity, List[str]]
    ) -> TaskComplexity:
        """Tell what complexity this task has (Tell Don't Ask)."""
        query_lower = self.query.lower()
        task_type = self.task_type.lower()

        # Check for specialized task types - Issue #380: Use module-level frozensets
        if task_type in CODE_TASK_TYPES:
            if any(word in query_lower for word in CODE_COMPLEXITY_KEYWORDS):
                return TaskComplexity.SPECIALIZED
            else:
                return TaskComplexity.COMPLEX

        # Analyze query content
        complexity_scores = {complexity: 0 for complexity in TaskComplexity}

        for complexity, keywords in complexity_keywords.items():
            for keyword in keywords:
                if keyword in query_lower:
                    complexity_scores[complexity] += 1

        # Consider query length as a factor
        query_length = len(self.query.split())
        if query_length > 50:
            complexity_scores[TaskComplexity.COMPLEX] += 1

        # Consider context length
        if self.context_length > 1000:
            complexity_scores[TaskComplexity.COMPLEX] += 1

        # Return highest scoring complexity
        if max(complexity_scores.values()) == 0:
            return TaskComplexity.MODERATE  # Default

        return max(complexity_scores.keys(), key=lambda k: complexity_scores[k])


@dataclass
class ModelInfo:
    """Information about an available model with performance tracking."""

    name: str
    size_gb: float
    parameter_size: str
    quantization: str
    family: str
    performance_level: ModelPerformanceLevel
    avg_tokens_per_second: float = 0.0
    avg_response_time: float = 0.0
    success_rate: float = 1.0
    last_used: float = 0.0
    use_count: int = 0

    async def load_performance_from_redis(self, redis_client, logger):
        """Load historical performance data from Redis (backward compatibility)."""
        from .performance_tracking import ModelPerformanceTracker

        tracker = ModelPerformanceTracker(redis_client, 3600, logger)
        await tracker.load_performance(self)

    async def save_performance_to_redis(self, redis_client, cache_ttl: int, logger):
        """Save performance metrics to Redis (backward compatibility)."""
        from .performance_tracking import ModelPerformanceTracker

        tracker = ModelPerformanceTracker(redis_client, cache_ttl, logger)
        await tracker.save_performance(self)

    def update_performance(
        self, response_time: float, tokens_per_second: float, success: bool
    ):
        """Update running performance averages."""
        if self.use_count > 0:
            total_count = self.use_count + 1
            self.avg_response_time = (
                self.avg_response_time * self.use_count + response_time
            ) / total_count
            self.avg_tokens_per_second = (
                self.avg_tokens_per_second * self.use_count + tokens_per_second
            ) / total_count
            self.success_rate = (
                self.success_rate * self.use_count + (1.0 if success else 0.0)
            ) / total_count
        else:
            self.avg_response_time = response_time
            self.avg_tokens_per_second = tokens_per_second
            self.success_rate = 1.0 if success else 0.0

        self.use_count += 1
        self.last_used = time.time()

    def calculate_score(
        self, task_request: TaskRequest, min_samples: int
    ) -> float:
        """Calculate performance score for this model given a task request."""
        score = 0.0

        # Performance history scoring
        if self.use_count >= min_samples:
            # Favor models with good historical performance
            score += self.success_rate * 30  # Success rate weight

            # Favor faster models if response time is important
            if task_request.max_response_time and self.avg_response_time > 0:
                if self.avg_response_time <= task_request.max_response_time:
                    score += 20
                else:
                    score -= 10  # Penalty for slow models

            # Favor models with higher token throughput
            score += min(self.avg_tokens_per_second / 10, 20)  # Cap at 20 points
        else:
            # New models get moderate score
            score += 15

        # Model capability scoring
        if self.performance_level == ModelPerformanceLevel.ADVANCED:
            score += 25
        elif self.performance_level == ModelPerformanceLevel.STANDARD:
            score += 15
        elif self.performance_level == ModelPerformanceLevel.LIGHTWEIGHT:
            score += 5

        # Recency bonus (favor recently used models)
        if self.last_used > 0:
            recency_hours = (time.time() - self.last_used) / 3600
            if recency_hours < 24:
                score += max(5 - recency_hours / 5, 0)  # Bonus decreases over time

        # User preference bonus
        if task_request.user_preference and task_request.user_preference in self.name:
            score += 10

        return score

    def meets_complexity_requirement(self, complexity: TaskComplexity) -> bool:
        """Check if this model meets the complexity requirements."""
        if complexity == TaskComplexity.SIMPLE:
            # Simple tasks can use any model
            return True
        elif complexity == TaskComplexity.MODERATE:
            # Moderate tasks need at least standard models
            return self.performance_level in [
                ModelPerformanceLevel.STANDARD,
                ModelPerformanceLevel.ADVANCED,
                ModelPerformanceLevel.SPECIALIZED,
            ]
        elif complexity == TaskComplexity.COMPLEX:
            # Complex tasks need advanced models
            return self.performance_level in [
                ModelPerformanceLevel.ADVANCED,
                ModelPerformanceLevel.SPECIALIZED,
            ]
        else:  # SPECIALIZED
            # Specialized tasks prefer advanced models
            return self.performance_level == ModelPerformanceLevel.ADVANCED

    def fits_resource_constraints(
        self, resources: "SystemResources | Dict[str, float]"
    ) -> bool:
        """Check if this model fits within available system resources."""
        # Support both SystemResources and dict for backward compatibility
        if isinstance(resources, SystemResources):
            max_size = resources.get_max_model_size_gb()
            return self.size_gb <= max_size
        else:
            # Dict format (backward compatibility)
            available_memory_gb = resources.get("available_memory_gb", 8.0)
            cpu_percent = resources.get("cpu_percent", 50.0)

            if cpu_percent > 80 or available_memory_gb < 4:
                return self.size_gb < 4.0
            elif available_memory_gb < 8:
                return self.size_gb < 8.0
            else:
                return True  # No resource constraints

    def is_underperforming(self, avg_success_rate: float) -> bool:
        """Check if this model is underperforming compared to average."""
        return self.use_count > 0 and self.success_rate < avg_success_rate * 0.8

    def is_slow(self, avg_response_time: float) -> bool:
        """Check if this model is slow compared to average."""
        return self.use_count > 0 and self.avg_response_time > avg_response_time * 1.5

    def is_overused_lightweight(self) -> bool:
        """Check if this lightweight model is being overused."""
        return (
            self.performance_level == ModelPerformanceLevel.LIGHTWEIGHT
            and self.use_count > 50
        )

    def to_info_dict(self) -> Dict[str, Any]:
        """Convert to info dictionary for API response."""
        return {
            "name": self.name,
            "size_gb": self.size_gb,
            "parameter_size": self.parameter_size,
            "quantization": self.quantization,
            "family": self.family,
            "performance_level": self.performance_level.value,
            "avg_tokens_per_second": self.avg_tokens_per_second,
            "avg_response_time": self.avg_response_time,
            "success_rate": self.success_rate,
            "use_count": self.use_count,
            "last_used": self.last_used,
        }

    def to_select_dict(self) -> Dict[str, Any]:
        """Convert to selection summary for model selection API."""
        return {
            "name": self.name,
            "size_gb": self.size_gb,
            "parameter_size": self.parameter_size,
            "performance_level": self.performance_level.value,
            "avg_response_time": self.avg_response_time,
            "avg_tokens_per_second": self.avg_tokens_per_second,
            "success_rate": self.success_rate,
        }

    def to_performance_history_dict(self) -> Dict[str, Any]:
        """Convert to performance history response."""
        # Calculate efficiency metrics
        tokens_per_gb = self.avg_tokens_per_second / max(self.size_gb, 0.1)
        response_efficiency = (
            1.0 / max(self.avg_response_time, 0.1)
            if self.avg_response_time > 0
            else 0
        )
        overall_score = (
            (
                self.success_rate * 40
                + min(self.avg_tokens_per_second / 10, 30)
                + min(10 / max(self.avg_response_time, 0.1), 30)
            )
            if self.avg_response_time > 0
            else self.success_rate * 40
        )

        return {
            "model_name": self.name,
            "current_metrics": {
                "avg_response_time": self.avg_response_time,
                "avg_tokens_per_second": self.avg_tokens_per_second,
                "success_rate": self.success_rate,
                "use_count": self.use_count,
                "last_used": self.last_used,
            },
            "model_info": {
                "size_gb": self.size_gb,
                "parameter_size": self.parameter_size,
                "quantization": self.quantization,
                "family": self.family,
                "performance_level": self.performance_level.value,
            },
            "efficiency_metrics": {
                "tokens_per_gb": tokens_per_gb,
                "response_efficiency": response_efficiency,
                "overall_score": overall_score,
            },
        }

    def to_comparison_dict(self) -> Dict[str, Any]:
        """Convert to comparison dict for model comparison API."""
        efficiency_score = (
            (self.avg_tokens_per_second / max(self.size_gb, 0.1))
            if self.size_gb > 0
            else 0
        )
        performance_score = (
            (
                self.success_rate * 50
                + min(self.avg_tokens_per_second / 5, 25)
                + min(25 / max(self.avg_response_time, 0.1), 25)
            )
            if self.avg_response_time > 0
            else self.success_rate * 50
        )

        return {
            "name": self.name,
            "size_gb": self.size_gb,
            "parameter_size": self.parameter_size,
            "avg_response_time": self.avg_response_time,
            "avg_tokens_per_second": self.avg_tokens_per_second,
            "success_rate": self.success_rate,
            "use_count": self.use_count,
            "efficiency_score": efficiency_score,
            "performance_score": performance_score,
        }
