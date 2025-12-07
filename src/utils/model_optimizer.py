# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Ollama Model Performance Optimizer
Intelligently manages and optimizes LLM model usage based on task complexity,
performance requirements, and system resources.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import psutil
import yaml

from src.constants.model_constants import ModelConstants
from src.unified_config_manager import UnifiedConfigManager

# Create singleton config instance
config = UnifiedConfigManager()
from src.utils.http_client import get_http_client
from src.utils.redis_client import get_redis_client


class TaskComplexity(Enum):
    """Task complexity levels for model selection"""

    SIMPLE = "simple"  # Basic responses, factual questions
    MODERATE = "moderate"  # Analysis, reasoning, explanations
    COMPLEX = "complex"  # Advanced reasoning, code generation, long-form content
    SPECIALIZED = "specialized"  # Domain-specific tasks requiring maximum capability


class ModelPerformanceLevel(Enum):
    """Model performance classification"""

    LIGHTWEIGHT = "lightweight"  # < 2B parameters
    STANDARD = "standard"  # 2-8B parameters
    ADVANCED = "advanced"  # 8B+ parameters
    SPECIALIZED = "specialized"  # Domain-specific models


@dataclass
class SystemResources:
    """System resource measurements with behavior methods (Tell Don't Ask)"""

    cpu_percent: float
    memory_percent: float
    available_memory_gb: float

    def allows_large_models(self) -> bool:
        """Tell if system can handle large models"""
        return self.memory_percent < 70 and self.cpu_percent < 60

    def get_max_model_size_gb(self) -> float:
        """Tell what max model size system can handle"""
        if self.cpu_percent > 80 or self.available_memory_gb < 4:
            return 4.0
        elif self.available_memory_gb < 8:
            return 8.0
        return float("inf")

    def to_dict(self) -> Dict[str, float]:
        """Convert to dict for backward compatibility"""
        return {
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "available_memory_gb": self.available_memory_gb,
        }


class SystemResourceAnalyzer:
    """Analyzes system resources for model selection (Tell Don't Ask)"""

    def __init__(self, logger):
        """Initialize analyzer with logger for error reporting."""
        self._logger = logger

    def get_current_resources(self) -> SystemResources:
        """Get current system resource state"""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()

            return SystemResources(
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                available_memory_gb=memory.available / (1024**3),
            )
        except Exception as e:
            self._logger.error(f"Error getting system resources: {e}")
            # Conservative defaults
            return SystemResources(
                cpu_percent=50.0, memory_percent=50.0, available_memory_gb=8.0
            )


class ModelPerformanceTracker:
    """Manages performance tracking and persistence to Redis (Tell Don't Ask)"""

    def __init__(self, redis_client, cache_ttl: int, logger):
        """Initialize tracker with Redis client, TTL, and logger."""
        self._redis_client = redis_client
        self._cache_ttl = cache_ttl
        self._logger = logger

    async def load_performance(self, model_info: "ModelInfo") -> None:
        """Load performance history from Redis into ModelInfo"""
        try:
            if not self._redis_client:
                return

            key = f"model_perf:{model_info.name}"
            perf_data = await self._redis_client.hgetall(key)

            if perf_data:
                model_info.avg_tokens_per_second = float(
                    perf_data.get(b"avg_tokens_per_second")
                    or perf_data.get("avg_tokens_per_second", 0)
                )
                model_info.avg_response_time = float(
                    perf_data.get(b"avg_response_time")
                    or perf_data.get("avg_response_time", 0)
                )
                model_info.success_rate = float(
                    perf_data.get(b"success_rate")
                    or perf_data.get("success_rate", 1.0)
                )
                model_info.last_used = float(
                    perf_data.get(b"last_used") or perf_data.get("last_used", 0)
                )
                model_info.use_count = int(
                    perf_data.get(b"use_count") or perf_data.get("use_count", 0)
                )

        except Exception as e:
            self._logger.error(
                f"Error loading performance history for {model_info.name}: {e}"
            )

    async def save_performance(self, model_info: "ModelInfo") -> None:
        """Save performance metrics from ModelInfo to Redis"""
        try:
            if not self._redis_client:
                return

            key = f"model_perf:{model_info.name}"

            await self._redis_client.hset(
                key,
                mapping={
                    "avg_response_time": str(model_info.avg_response_time),
                    "avg_tokens_per_second": str(model_info.avg_tokens_per_second),
                    "success_rate": str(model_info.success_rate),
                    "last_used": str(model_info.last_used),
                    "use_count": str(model_info.use_count),
                },
            )

            await self._redis_client.expire(key, self._cache_ttl)

        except Exception as e:
            self._logger.error(f"Error saving performance for {model_info.name}: {e}")

    async def update_and_save(
        self,
        model_name: str,
        response_time: float,
        tokens_per_second: float,
        success: bool,
        model_cache: Dict[str, "ModelInfo"],
    ) -> None:
        """Update model performance and persist - one method does both"""
        # Update in-memory model if available
        if model_name in model_cache:
            model = model_cache[model_name]
            model.update_performance(response_time, tokens_per_second, success)
            await self.save_performance(model)
        else:
            # Model not in cache - update Redis directly
            self._logger.warning(
                f"Model {model_name} not in cache, updating Redis only"
            )
            await self._update_redis_directly(
                model_name, response_time, tokens_per_second, success
            )

    async def _update_redis_directly(
        self,
        model_name: str,
        response_time: float,
        tokens_per_second: float,
        success: bool,
    ) -> None:
        """Update Redis when model not in cache (fallback path)"""
        if not self._redis_client:
            return

        try:
            key = f"model_perf:{model_name}"
            existing = await self._redis_client.hgetall(key)

            if existing:
                prev_avg_response = float(
                    existing.get(b"avg_response_time")
                    or existing.get("avg_response_time", 0)
                )
                prev_avg_tokens = float(
                    existing.get(b"avg_tokens_per_second")
                    or existing.get("avg_tokens_per_second", 0)
                )
                prev_success_rate = float(
                    existing.get(b"success_rate") or existing.get("success_rate", 1.0)
                )
                use_count = int(
                    existing.get(b"use_count") or existing.get("use_count", 0)
                )

                new_count = use_count + 1
                new_avg_response = (
                    prev_avg_response * use_count + response_time
                ) / new_count
                new_avg_tokens = (
                    prev_avg_tokens * use_count + tokens_per_second
                ) / new_count
                new_success_rate = (
                    prev_success_rate * use_count + (1.0 if success else 0.0)
                ) / new_count
            else:
                new_count = 1
                new_avg_response = response_time
                new_avg_tokens = tokens_per_second
                new_success_rate = 1.0 if success else 0.0

            await self._redis_client.hset(
                key,
                mapping={
                    "avg_response_time": str(new_avg_response),
                    "avg_tokens_per_second": str(new_avg_tokens),
                    "success_rate": str(new_success_rate),
                    "last_used": str(time.time()),
                    "use_count": str(new_count),
                },
            )
            await self._redis_client.expire(key, self._cache_ttl)
        except Exception as e:
            self._logger.error(f"Error saving performance for {model_name}: {e}")


@dataclass
class ModelInfo:
    """Information about an available model with performance tracking"""

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
        """Load historical performance data from Redis (backward compatibility)"""
        tracker = ModelPerformanceTracker(redis_client, 3600, logger)
        await tracker.load_performance(self)

    async def save_performance_to_redis(self, redis_client, cache_ttl: int, logger):
        """Save performance metrics to Redis (backward compatibility)"""
        tracker = ModelPerformanceTracker(redis_client, cache_ttl, logger)
        await tracker.save_performance(self)

    def update_performance(
        self, response_time: float, tokens_per_second: float, success: bool
    ):
        """Update running performance averages"""
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
        """Calculate performance score for this model given a task request"""
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
        """Check if this model meets the complexity requirements"""
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
        """Check if this model fits within available system resources"""
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
        """Check if this model is underperforming compared to average"""
        return self.use_count > 0 and self.success_rate < avg_success_rate * 0.8

    def is_slow(self, avg_response_time: float) -> bool:
        """Check if this model is slow compared to average"""
        return self.use_count > 0 and self.avg_response_time > avg_response_time * 1.5

    def is_overused_lightweight(self) -> bool:
        """Check if this lightweight model is being overused"""
        return (
            self.performance_level == ModelPerformanceLevel.LIGHTWEIGHT
            and self.use_count > 50
        )


@dataclass
class TaskRequest:
    """A request for model optimization"""

    query: str
    task_type: str  # 'chat', 'code', 'analysis', etc.
    max_response_time: Optional[float] = None
    min_quality: Optional[float] = None
    context_length: int = 0
    user_preference: Optional[str] = None

    def analyze_complexity(
        self, complexity_keywords: Dict[TaskComplexity, List[str]]
    ) -> TaskComplexity:
        """Tell what complexity this task has (Tell Don't Ask)"""
        query_lower = self.query.lower()
        task_type = self.task_type.lower()

        # Check for specialized task types
        if task_type in ["code", "programming", "development"]:
            if any(
                word in query_lower
                for word in ["complex", "algorithm", "optimize", "architecture"]
            ):
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


class ModelSelector:
    """Handles model filtering and selection logic (Tell Don't Ask)"""

    def __init__(self, min_samples: int):
        """Initialize selector with minimum sample threshold."""
        self._min_samples = min_samples

    def filter_by_complexity(
        self, models: List[ModelInfo], complexity: TaskComplexity
    ) -> List[ModelInfo]:
        """Filter models based on task complexity requirements"""
        filtered = [m for m in models if m.meets_complexity_requirement(complexity)]

        # For SPECIALIZED complexity, prefer advanced models but fall back to all if none available
        if complexity == TaskComplexity.SPECIALIZED and not filtered:
            return models

        return filtered if filtered else models

    def filter_by_resources(
        self, models: List[ModelInfo], resources: SystemResources
    ) -> List[ModelInfo]:
        """Filter models based on available system resources"""
        return [m for m in models if m.fits_resource_constraints(resources)]

    def rank_by_performance(
        self, models: List[ModelInfo], task_request: TaskRequest
    ) -> List[ModelInfo]:
        """Rank models by expected performance for the task"""
        # Let each model calculate its own score
        scored_models = [
            (model, model.calculate_score(task_request, self._min_samples))
            for model in models
        ]

        # Sort by score (descending)
        scored_models.sort(key=lambda x: x[1], reverse=True)

        return [model for model, score in scored_models]


class ModelOptimizer:
    """Intelligent model selection and performance optimization"""

    @staticmethod
    def _load_model_classifications() -> Dict[ModelPerformanceLevel, List[str]]:
        """
        Load model classifications from config file.
        Implements zero hardcode policy by reading from config/llm_models.yaml.

        Returns:
            Dict mapping ModelPerformanceLevel to list of model names

        Fallback behavior:
            If config file not found or invalid, returns minimal defaults
        """
        try:
            # Get config file path (project root / config / llm_models.yaml)
            config_path = (
                Path(__file__).parent.parent.parent / "config" / "llm_models.yaml"
            )

            if config_path.exists():
                with open(config_path, "r") as f:
                    config_data = yaml.safe_load(f)

                performance_data = config_data.get("performance_classification", {})

                return {
                    ModelPerformanceLevel.LIGHTWEIGHT: performance_data.get(
                        "lightweight", []
                    ),
                    ModelPerformanceLevel.STANDARD: performance_data.get(
                        "standard", []
                    ),
                    ModelPerformanceLevel.ADVANCED: performance_data.get(
                        "advanced", []
                    ),
                }

            # Fallback to environment variable if config not found
            default_model = os.getenv(
                "AUTOBOT_DEFAULT_LLM_MODEL", ModelConstants.DEFAULT_OLLAMA_MODEL
            )
            logging.warning(
                f"Model classifications config not found, using default model: {default_model}"
            )
            return {
                ModelPerformanceLevel.LIGHTWEIGHT: [default_model],
                ModelPerformanceLevel.STANDARD: [default_model],
                ModelPerformanceLevel.ADVANCED: [default_model],
            }

        except Exception as e:
            # Final fallback
            default_model = os.getenv(
                "AUTOBOT_DEFAULT_LLM_MODEL", ModelConstants.DEFAULT_OLLAMA_MODEL
            )
            logging.error(
                f"Error loading model classifications: {e}, using default: {default_model}"
            )
            return {
                ModelPerformanceLevel.LIGHTWEIGHT: [default_model],
                ModelPerformanceLevel.STANDARD: [default_model],
                ModelPerformanceLevel.ADVANCED: [default_model],
            }

    def __init__(self):
        """Initialize model optimizer with caching and performance tracking."""
        self.logger = logging.getLogger(__name__)
        self._redis_client = None
        self._models_cache = {}
        self._performance_history = {}
        self._ollama_base_url = (
            f"http://{config.get_host('ollama')}:{config.get_port('ollama')}"
        )

        # Configuration
        self._performance_threshold = config.get(
            "llm.optimization.performance_threshold", 0.8
        )
        self._cache_ttl = config.get("llm.optimization.cache_ttl", 3600)  # 1 hour
        self._min_samples = config.get("llm.optimization.min_samples", 5)

        # Model classification rules - loaded from config (zero hardcode policy)
        self.model_classifications = self._load_model_classifications()

        # Task complexity mapping
        self.complexity_keywords = {
            TaskComplexity.SIMPLE: [
                "what",
                "when",
                "where",
                "who",
                "define",
                "explain briefly",
                "yes/no",
                "true/false",
                "list",
            ],
            TaskComplexity.MODERATE: [
                "analyze",
                "compare",
                "explain",
                "summarize",
                "describe",
                "how",
                "why",
                "discuss",
            ],
            TaskComplexity.COMPLEX: [
                "design",
                "create",
                "develop",
                "implement",
                "solve",
                "optimize",
                "generate code",
                "write program",
                "complex analysis",
            ],
            TaskComplexity.SPECIALIZED: [
                "research paper",
                "scientific",
                "mathematical proof",
                "legal analysis",
                "medical",
                "financial modeling",
                "advanced algorithms",
            ],
        }

        # Initialize new components (Tell Don't Ask pattern)
        self._resource_analyzer = SystemResourceAnalyzer(self.logger)
        self._model_selector = ModelSelector(self._min_samples)
        self._performance_tracker = None  # Initialized when Redis client is ready

    async def _get_redis_client(self):
        """Get Redis client for caching performance data"""
        if self._redis_client is None:
            try:
                self._redis_client = get_redis_client(
                    async_client=True, db=config.get("redis.databases.llm_cache.db", 5)
                )
                if asyncio.iscoroutine(self._redis_client):
                    self._redis_client = await self._redis_client

                # Initialize performance tracker once Redis is ready
                if self._redis_client and self._performance_tracker is None:
                    self._performance_tracker = ModelPerformanceTracker(
                        self._redis_client, self._cache_ttl, self.logger
                    )

            except Exception as e:
                self.logger.error(
                    f"Failed to initialize Redis client for model optimization: {e}"
                )
                self._redis_client = None
        return self._redis_client

    async def refresh_available_models(self) -> List[ModelInfo]:
        """Refresh the list of available models from Ollama"""
        try:
            http_client = get_http_client()
            async with await http_client.get(
                f"{self._ollama_base_url}/api/tags"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    models = []

                    for model_data in data.get("models", []):
                        name = model_data.get("name", "")
                        size_bytes = model_data.get("size", 0)
                        size_gb = round(size_bytes / (1024**3), 2)

                        details = model_data.get("details", {})
                        parameter_size = details.get("parameter_size", "Unknown")
                        quantization = details.get("quantization_level", "Unknown")
                        family = details.get("family", "Unknown")

                        # Classify model performance level
                        performance_level = self._classify_model_performance(
                            name, parameter_size
                        )

                        model_info = ModelInfo(
                            name=name,
                            size_gb=size_gb,
                            parameter_size=parameter_size,
                            quantization=quantization,
                            family=family,
                            performance_level=performance_level,
                        )

                        # Load performance history if available
                        await self._load_model_performance_history(model_info)
                        models.append(model_info)

                    self._models_cache = {model.name: model for model in models}
                    self.logger.info(f"Refreshed {len(models)} available models")
                    return models

                else:
                    self.logger.error(
                        f"Failed to fetch models: HTTP {response.status}"
                    )
                    return []

        except Exception as e:
            self.logger.error(f"Error refreshing models: {e}")
            return []

    def _classify_model_performance(
        self, name: str, parameter_size: str
    ) -> ModelPerformanceLevel:
        """Classify model performance level based on name and parameters"""
        # Check explicit classifications first
        for level, models in self.model_classifications.items():
            if any(model_name in name for model_name in models):
                return level

        # Fallback to parameter size analysis
        try:
            if "M" in parameter_size:  # Million parameters
                param_num = float(parameter_size.replace("M", ""))
                if param_num < 2000:  # < 2B
                    return ModelPerformanceLevel.LIGHTWEIGHT
            elif "B" in parameter_size:  # Billion parameters
                param_num = float(parameter_size.replace("B", ""))
                if param_num < 2:
                    return ModelPerformanceLevel.LIGHTWEIGHT
                elif param_num < 8:
                    return ModelPerformanceLevel.STANDARD
                else:
                    return ModelPerformanceLevel.ADVANCED
        except Exception:
            pass  # Parameter parsing failed, use default below

        # Default classification
        return ModelPerformanceLevel.STANDARD

    async def _load_model_performance_history(self, model_info: ModelInfo):
        """Load historical performance data for a model"""
        redis_client = await self._get_redis_client()
        if self._performance_tracker:
            await self._performance_tracker.load_performance(model_info)
        else:
            # Fallback to old method if tracker not initialized
            await model_info.load_performance_from_redis(redis_client, self.logger)

    async def _save_model_performance(
        self,
        model_name: str,
        response_time: float,
        tokens_per_second: float,
        success: bool,
    ):
        """Save performance metrics for a model (updates in-memory model and persists to Redis)"""
        # Use performance tracker if available (Tell Don't Ask)
        await self._get_redis_client()  # Ensure tracker is initialized
        if self._performance_tracker:
            await self._performance_tracker.update_and_save(
                model_name, response_time, tokens_per_second, success, self._models_cache
            )
        else:
            # Fallback to old implementation if tracker not available
            if model_name in self._models_cache:
                model = self._models_cache[model_name]
                model.update_performance(response_time, tokens_per_second, success)
                redis_client = await self._get_redis_client()
                await model.save_performance_to_redis(
                    redis_client, self._cache_ttl, self.logger
                )

    def analyze_task_complexity(self, task_request: TaskRequest) -> TaskComplexity:
        """Analyze task complexity based on query content and type (backward compatibility)"""
        # Delegate to TaskRequest (Tell Don't Ask)
        return task_request.analyze_complexity(self.complexity_keywords)

    def get_system_resources(self) -> Dict[str, float]:
        """Get current system resource utilization (backward compatibility)"""
        # Delegate to resource analyzer (Tell Don't Ask)
        resources = self._resource_analyzer.get_current_resources()
        return resources.to_dict()  # Return dict for backward compatibility

    async def select_optimal_model(self, task_request: TaskRequest) -> Optional[str]:
        """Select the optimal model for a given task"""
        try:
            # Ensure we have fresh model data
            if not self._models_cache:
                await self.refresh_available_models()

            if not self._models_cache:
                self.logger.error("No models available")
                return None

            # Analyze task complexity (Tell Don't Ask - task knows its complexity)
            complexity = task_request.analyze_complexity(self.complexity_keywords)

            # Get current system resources (Tell Don't Ask - analyzer knows resources)
            resources = self._resource_analyzer.get_current_resources()

            # Get suitable models based on complexity (Tell selector to filter)
            suitable_models = self._model_selector.filter_by_complexity(
                list(self._models_cache.values()), complexity
            )

            if not suitable_models:
                self.logger.warning(
                    f"No suitable models found for complexity: {complexity}"
                )
                return list(self._models_cache.keys())[0]  # Fallback to first available

            # Filter by resource constraints (Tell selector to filter by resources)
            resource_filtered = self._model_selector.filter_by_resources(
                suitable_models, resources
            )

            if not resource_filtered:
                self.logger.warning(
                    "No models pass resource filtering, using least resource-intensive"
                ),
                resource_filtered = sorted(suitable_models, key=lambda m: m.size_gb)[:1]

            # Score and rank models (Tell selector to rank)
            ranked_models = self._model_selector.rank_by_performance(
                resource_filtered, task_request
            )

            # Select best model
            selected_model = ranked_models[0] if ranked_models else None

            if selected_model:
                self.logger.info(
                    f"Selected model: {selected_model.name} "
                    f"(complexity: {complexity.value}, performance: {selected_model.performance_level.value})"
                )
                return selected_model.name

            return None

        except Exception as e:
            self.logger.error(f"Error selecting optimal model: {e}")
            return list(self._models_cache.keys())[0] if self._models_cache else None

    # Backward compatibility methods (delegate to new components)
    def _filter_models_by_complexity(
        self, complexity: TaskComplexity, models: List[ModelInfo]
    ) -> List[ModelInfo]:
        """Filter models based on task complexity requirements (backward compatibility)"""
        return self._model_selector.filter_by_complexity(models, complexity)

    def _filter_models_by_resources(
        self, models: List[ModelInfo], resources: Dict[str, float]
    ) -> List[ModelInfo]:
        """Filter models based on available system resources (backward compatibility)"""
        # Convert dict to SystemResources for new API
        system_resources = SystemResources(
            cpu_percent=resources.get("cpu_percent", 50.0),
            memory_percent=resources.get("memory_percent", 50.0),
            available_memory_gb=resources.get("available_memory_gb", 8.0),
        )
        return self._model_selector.filter_by_resources(models, system_resources)

    def _rank_models_by_performance(
        self, models: List[ModelInfo], task_request: TaskRequest
    ) -> List[ModelInfo]:
        """Rank models by expected performance for the task (backward compatibility)"""
        return self._model_selector.rank_by_performance(models, task_request)

    async def track_model_performance(
        self, model_name: str, response_time: float, response_tokens: int, success: bool
    ):
        """Track model performance for future optimization"""
        try:
            tokens_per_second = (
                response_tokens / response_time if response_time > 0 else 0
            )
            # Delegate to _save_model_performance which now handles both in-memory and Redis updates
            await self._save_model_performance(
                model_name, response_time, tokens_per_second, success
            )

        except Exception as e:
            self.logger.error(f"Error tracking performance for {model_name}: {e}")

    async def get_optimization_suggestions(self) -> List[Dict[str, Any]]:
        """Get suggestions for model optimization"""
        suggestions = []

        try:
            if not self._models_cache:
                await self.refresh_available_models()

            # Analyze model usage patterns
            models_with_history = [
                m for m in self._models_cache.values() if m.use_count > 0
            ]

            if not models_with_history:
                suggestions.append(
                    {
                        "type": "info",
                        "message": "No model usage history available yet",
                        "action": (
                            "Continue using the system to build performance profiles"
                        ),
                    }
                )
                return suggestions

            # Calculate averages for comparison
            avg_success_rate = sum(m.success_rate for m in models_with_history) / len(
                models_with_history
            )
            avg_response_time = sum(
                m.avg_response_time for m in models_with_history
            ) / len(models_with_history)

            # Find underperforming models (models answer about themselves)
            underperforming = [
                m for m in models_with_history if m.is_underperforming(avg_success_rate)
            ]

            if underperforming:
                suggestions.append(
                    {
                        "type": "warning",
                        "message": (
                            f"Found {len(underperforming)} underperforming models"
                        ),
                        "models": [m.name for m in underperforming],
                        "action": (
                            "Consider avoiding these models or investigating issues"
                        ),
                    }
                )

            # Find slow models (models answer about themselves)
            slow_models = [m for m in models_with_history if m.is_slow(avg_response_time)]

            if slow_models:
                suggestions.append(
                    {
                        "type": "performance",
                        "message": f"Found {len(slow_models)} slow models",
                        "models": [
                            {
                                "name": m.name,
                                "avg_time": f"{m.avg_response_time:.2f}s",
                            }
                            for m in slow_models
                        ],
                        "action": (
                            "Consider using faster alternatives for time-sensitive tasks"
                        ),
                    }
                )

            # Suggest model upgrades (models answer about themselves)
            lightweight_overused = [
                m for m in models_with_history if m.is_overused_lightweight()
            ]

            if lightweight_overused:
                suggestions.append(
                    {
                        "type": "optimization",
                        "message": "Heavily used lightweight models detected",
                        "models": [m.name for m in lightweight_overused],
                        "action": (
                            "Consider upgrading to more capable models for better quality"
                        ),
                    }
                )

            # Resource optimization (Tell Don't Ask - resources know if they allow large models)
            resources = self._resource_analyzer.get_current_resources()
            if resources.allows_large_models():
                large_models = [
                    m
                    for m in self._models_cache.values()
                    if m.performance_level == ModelPerformanceLevel.ADVANCED
                ]
                if large_models:
                    suggestions.append(
                        {
                            "type": "resource",
                            "message": (
                                "System has available resources for larger models"
                            ),
                            "available_models": [m.name for m in large_models],
                            "action": (
                                "Consider using more capable models for better results"
                            ),
                        }
                    )

            return suggestions

        except Exception as e:
            self.logger.error(f"Error generating optimization suggestions: {e}")
            return [{"type": "error", "message": str(e)}]


# Global optimizer instance (thread-safe)
import threading

_model_optimizer = None
_model_optimizer_lock = threading.Lock()


def get_model_optimizer() -> ModelOptimizer:
    """Get the global model optimizer instance (thread-safe)"""
    global _model_optimizer
    if _model_optimizer is None:
        with _model_optimizer_lock:
            # Double-check after acquiring lock
            if _model_optimizer is None:
                _model_optimizer = ModelOptimizer()
    return _model_optimizer
