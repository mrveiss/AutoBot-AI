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
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Bytes-per-parameter for common quantization levels (Issue #1966).
_QUANT_BPP: Dict[str, float] = {
    "F32": 4.0,
    "F16": 2.0,
    "BF16": 2.0,
    "Q8_0": 1.0,
    "Q8": 1.0,
    "Q6_K": 0.75,
    "Q5_K_M": 0.625,
    "Q5_K_S": 0.625,
    "Q5_1": 0.625,
    "Q5_0": 0.625,
    "Q4_K_M": 0.5,
    "Q4_K_S": 0.5,
    "Q4_1": 0.5,
    "Q4_0": 0.5,
    "Q3_K_M": 0.375,
    "Q3_K_S": 0.375,
    "Q3_K_L": 0.375,
    "Q2_K": 0.25,
    "IQ4_XS": 0.5,
    "IQ3_XXS": 0.375,
    "IQ2_XXS": 0.25,
}
_DEFAULT_BPP = 0.5


def _parse_parameter_billions(parameter_size: str) -> float:
    """Parse parameter size string to billions (Issue #1966).

    Supports "7B", "13B", "500M", "1.5B". Returns 7.0 on failure.
    """
    s = parameter_size.strip().upper()
    try:
        if s.endswith("M"):
            return float(s[:-1]) / 1000.0
        if s.endswith("B"):
            return float(s[:-1])
    except ValueError:
        pass
    logger.debug(
        "Could not parse parameter_size %r, using 7B default",
        parameter_size,
    )
    return 7.0


def estimate_model_memory_gb(
    parameter_size: str,
    quantization: str,
    context_tokens: int = 2048,
) -> float:
    """Estimate LLM memory requirement in GB (Issue #1966).

    Formula: memory = (params_B * bpp) + (0.000008 * params_B * ctx) + 0.5
    Components: weight storage + KV cache + CUDA/runtime overhead.
    """
    params_b = _parse_parameter_billions(parameter_size)
    bpp = _QUANT_BPP.get(quantization.strip().upper(), _DEFAULT_BPP)
    weight_gb = params_b * bpp
    kv_cache_gb = 0.000008 * params_b * context_tokens
    return weight_gb + kv_cache_gb + 0.5


class ModelCapabilityTier(Enum):
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
    gpu_vram_gb: float = 0.0  # Total free VRAM across all GPUs in GB (#1966, #2032)
    per_gpu_vram_gb: List[float] = field(default_factory=list)  # Per-GPU free VRAM (#2032)

    def allows_large_models(self) -> bool:
        """Tell if system can handle large models."""
        return self.memory_percent < 70 and self.cpu_percent < 60

    def get_max_model_size_gb(self) -> float:
        """Tell max model memory the system can handle (Issue #1966).

        Uses 80% of available memory as safety margin to prevent OOM.
        """
        if self.cpu_percent > 90 or self.available_memory_gb < 2:
            return 1.0
        return self.available_memory_gb * 0.8

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for backward compatibility."""
        return {
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "available_memory_gb": self.available_memory_gb,
            "gpu_vram_gb": self.gpu_vram_gb,
            "per_gpu_vram_gb": list(self.per_gpu_vram_gb),
        }


@dataclass
class TaskRequest:
    """A request for model optimization."""

    query: str
    task_type: str  # 'chat', 'code', 'analysis', etc.
    max_response_time: float | None = None
    min_quality: float | None = None
    context_length: int = 0
    user_preference: str | None = None

    def analyze_complexity(self, complexity_keywords: Dict[ModelCapabilityTier, List[str]]) -> ModelCapabilityTier:
        """Tell what complexity this task has (Tell Don't Ask)."""
        query_lower = self.query.lower()
        task_type = self.task_type.lower()

        # Check for specialized task types - Issue #380: Use module-level frozensets
        if task_type in CODE_TASK_TYPES:
            if any(word in query_lower for word in CODE_COMPLEXITY_KEYWORDS):
                return ModelCapabilityTier.SPECIALIZED
            else:
                return ModelCapabilityTier.COMPLEX

        # Analyze query content
        complexity_scores = {complexity: 0 for complexity in ModelCapabilityTier}

        for complexity, keywords in complexity_keywords.items():
            for keyword in keywords:
                if keyword in query_lower:
                    complexity_scores[complexity] += 1

        # Consider query length as a factor
        query_length = len(self.query.split())
        if query_length > 50:
            complexity_scores[ModelCapabilityTier.COMPLEX] += 1

        # Consider context length
        if self.context_length > 1000:
            complexity_scores[ModelCapabilityTier.COMPLEX] += 1

        # Return highest scoring complexity
        if max(complexity_scores.values()) == 0:
            return ModelCapabilityTier.MODERATE  # Default

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

    def update_performance(self, response_time: float, tokens_per_second: float, success: bool):
        """Update running performance averages."""
        if self.use_count > 0:
            total_count = self.use_count + 1
            self.avg_response_time = (self.avg_response_time * self.use_count + response_time) / total_count
            self.avg_tokens_per_second = (self.avg_tokens_per_second * self.use_count + tokens_per_second) / total_count
            self.success_rate = (self.success_rate * self.use_count + (1.0 if success else 0.0)) / total_count
        else:
            self.avg_response_time = response_time
            self.avg_tokens_per_second = tokens_per_second
            self.success_rate = 1.0 if success else 0.0

        self.use_count += 1
        self.last_used = time.time()

    def calculate_score(self, task_request: TaskRequest, min_samples: int) -> float:
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

    def meets_complexity_requirement(self, complexity: ModelCapabilityTier) -> bool:
        """Check if this model meets the complexity requirements."""
        if complexity == ModelCapabilityTier.SIMPLE:
            # Simple tasks can use any model
            return True
        elif complexity == ModelCapabilityTier.MODERATE:
            # Moderate tasks need at least standard models
            return self.performance_level in [
                ModelPerformanceLevel.STANDARD,
                ModelPerformanceLevel.ADVANCED,
                ModelPerformanceLevel.SPECIALIZED,
            ]
        elif complexity == ModelCapabilityTier.COMPLEX:
            # Complex tasks need advanced models
            return self.performance_level in [
                ModelPerformanceLevel.ADVANCED,
                ModelPerformanceLevel.SPECIALIZED,
            ]
        else:  # SPECIALIZED
            # Specialized tasks prefer advanced models
            return self.performance_level == ModelPerformanceLevel.ADVANCED

    def estimate_memory_gb(self, context_tokens: int = 2048) -> float:
        """Estimate memory this model needs in GB (Issue #1966)."""
        return estimate_model_memory_gb(self.parameter_size, self.quantization, context_tokens)

    def fits_resource_constraints(self, resources: "SystemResources | Dict[str, float]") -> bool:
        """Check if this model fits within available resources (#1966, #2015).

        When a GPU is present, LLM weights load into VRAM — not system RAM.
        GPU path: compare estimated memory against gpu_vram_gb and return
        immediately; system RAM is irrelevant for GPU inference.
        CPU-only path (gpu_vram_gb == 0): compare against available_memory_gb.
        """
        estimated = self.estimate_memory_gb()
        if isinstance(resources, SystemResources):
            if resources.gpu_vram_gb > 0:
                return estimated <= resources.gpu_vram_gb
            max_mem = resources.get_max_model_size_gb()
            return estimated <= max_mem
        else:
            gpu_vram = resources.get("gpu_vram_gb", 0.0)
            if gpu_vram > 0:
                return estimated <= gpu_vram
            available = resources.get("available_memory_gb", 8.0)
            cpu = resources.get("cpu_percent", 50.0)
            if cpu > 90 or available < 2:
                return estimated <= 1.0
            return estimated <= available * 0.8

    def is_underperforming(self, avg_success_rate: float) -> bool:
        """Check if this model is underperforming compared to average."""
        return self.use_count > 0 and self.success_rate < avg_success_rate * 0.8

    def is_slow(self, avg_response_time: float) -> bool:
        """Check if this model is slow compared to average."""
        return self.use_count > 0 and self.avg_response_time > avg_response_time * 1.5

    def is_overused_lightweight(self) -> bool:
        """Check if this lightweight model is being overused."""
        return self.performance_level == ModelPerformanceLevel.LIGHTWEIGHT and self.use_count > 50

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
        response_efficiency = 1.0 / max(self.avg_response_time, 0.1) if self.avg_response_time > 0 else 0
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
        efficiency_score = (self.avg_tokens_per_second / max(self.size_gb, 0.1)) if self.size_gb > 0 else 0
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
