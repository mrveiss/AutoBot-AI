# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Ollama Model Performance Optimizer

Issue #381: This file has been refactored into the model_optimization/ package.
This thin facade maintains backward compatibility while delegating to focused modules.

See: src/utils/model_optimization/
- types.py: TaskComplexity, ModelPerformanceLevel, SystemResources, TaskRequest, ModelInfo
- system_resources.py: SystemResourceAnalyzer for system resource analysis
- performance_tracking.py: ModelPerformanceTracker for Redis persistence
- model_selection.py: ModelSelector and ModelClassifier for model selection

Intelligently manages and optimizes LLM model usage based on task complexity,
performance requirements, and system resources.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Dict, List, Optional

from config import UnifiedConfigManager

from autobot_shared.http_client import get_http_client
from autobot_shared.redis_client import get_redis_client

# Re-export all public API from the package for backward compatibility
from backend.utils.model_optimization import (
    CODE_COMPLEXITY_KEYWORDS,
    CODE_TASK_TYPES,
    ModelClassifier,
    ModelInfo,
    ModelPerformanceLevel,
    ModelPerformanceTracker,
    ModelSelector,
    SystemResourceAnalyzer,
    SystemResources,
    TaskComplexity,
    TaskRequest,
)

# Create singleton config instance
config = UnifiedConfigManager()

logger = logging.getLogger(__name__)

__all__ = [
    # Types and enums
    "TaskComplexity",
    "ModelPerformanceLevel",
    "SystemResources",
    "TaskRequest",
    "ModelInfo",
    # Constants
    "CODE_TASK_TYPES",
    "CODE_COMPLEXITY_KEYWORDS",
    # Analyzers and selectors
    "SystemResourceAnalyzer",
    "ModelPerformanceTracker",
    "ModelSelector",
    "ModelClassifier",
    # Main class
    "ModelOptimizer",
    # Singleton access
    "get_model_optimizer",
]


class ModelOptimizer:
    """
    Intelligent model selection and performance optimization.

    Issue #381: Refactored to delegate to model_optimization package components.
    """

    def __init__(self):
        """Initialize model optimizer with caching and performance tracking."""
        self.logger = logging.getLogger(__name__)
        self._redis_client = None
        self._models_cache: Dict[str, ModelInfo] = {}
        self._performance_history: Dict[str, Any] = {}
        self._ollama_base_url = (
            f"http://{config.get_host('ollama')}:{config.get_port('ollama')}"
        )

        # Issue #378: Lock for Redis client initialization
        self._redis_init_lock = asyncio.Lock()

        # Configuration
        self._performance_threshold = config.get(
            "llm.optimization.performance_threshold", 0.8
        )
        self._cache_ttl = config.get("llm.optimization.cache_ttl", 3600)  # 1 hour
        self._min_samples = config.get("llm.optimization.min_samples", 5)

        # Model classification rules - loaded from config (zero hardcode policy)
        self._classifier = ModelClassifier()
        self.model_classifications = self._classifier.load_model_classifications()

        # Task complexity mapping - Issue #620: Extracted to helper method
        self.complexity_keywords = self._build_default_complexity_keywords()

        # Initialize new components (Tell Don't Ask pattern)
        self._resource_analyzer = SystemResourceAnalyzer(self.logger)
        self._model_selector = ModelSelector(self._min_samples)
        self._performance_tracker: Optional[ModelPerformanceTracker] = None

    def _build_default_complexity_keywords(self) -> Dict[TaskComplexity, List[str]]:
        """Build default task complexity keyword mappings. Issue #620.

        Returns:
            Dictionary mapping TaskComplexity levels to keyword lists
        """
        return {
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

    async def _get_redis_client(self):
        """Get Redis client for caching performance data.

        Issue #378: Uses double-checked locking to prevent race condition
        when multiple coroutines try to initialize the client simultaneously.
        """
        if self._redis_client is None:
            async with self._redis_init_lock:
                # Double-check after acquiring lock
                if self._redis_client is None:
                    try:
                        self._redis_client = get_redis_client(
                            async_client=True,
                            db=config.get("redis.databases.llm_cache.db", 5),
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
        """Refresh the list of available models from Ollama."""
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
                        performance_level = self._classifier.classify_model_performance(
                            name, parameter_size, self.model_classifications
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
                    self.logger.info("Refreshed %s available models", len(models))
                    return models

                else:
                    self.logger.error(
                        "Failed to fetch models: HTTP %s", response.status
                    )
                    return []

        except Exception as e:
            self.logger.error("Error refreshing models: %s", e)
            return []

    async def _load_model_performance_history(self, model_info: ModelInfo):
        """Load historical performance data for a model."""
        await self._get_redis_client()
        if self._performance_tracker:
            await self._performance_tracker.load_performance(model_info)

    async def _save_model_performance(
        self,
        model_name: str,
        response_time: float,
        tokens_per_second: float,
        success: bool,
    ):
        """Save performance metrics for a model."""
        await self._get_redis_client()
        if self._performance_tracker:
            await self._performance_tracker.update_and_save(
                model_name,
                response_time,
                tokens_per_second,
                success,
                self._models_cache,
            )

    def analyze_task_complexity(self, task_request: TaskRequest) -> TaskComplexity:
        """Analyze task complexity based on query content and type."""
        return task_request.analyze_complexity(self.complexity_keywords)

    def get_system_resources(self) -> Dict[str, float]:
        """Get current system resource utilization."""
        resources = self._resource_analyzer.get_current_resources()
        return resources.to_dict()

    def _filter_suitable_models(
        self, complexity: TaskComplexity
    ) -> Optional[List[ModelInfo]]:
        """Filter models by complexity and return suitable candidates. Issue #620.

        Args:
            complexity: Task complexity level

        Returns:
            List of suitable models, or None to use first available model
        """
        suitable_models = self._model_selector.filter_by_complexity(
            list(self._models_cache.values()), complexity
        )

        if not suitable_models:
            self.logger.warning(
                f"No suitable models found for complexity: {complexity}"
            )
            return None

        return suitable_models

    def _apply_resource_filtering(
        self, suitable_models: List[ModelInfo], resources: SystemResources
    ) -> List[ModelInfo]:
        """Apply resource constraints to filter models. Issue #620.

        Args:
            suitable_models: Models that match complexity requirements
            resources: Current system resource availability

        Returns:
            List of models that pass resource filtering
        """
        resource_filtered = self._model_selector.filter_by_resources(
            suitable_models, resources
        )

        if not resource_filtered:
            self.logger.warning(
                "No models pass resource filtering, using least resource-intensive"
            )
            return sorted(suitable_models, key=lambda m: m.size_gb)[:1]

        return resource_filtered

    def _select_and_log_model(
        self,
        ranked_models: List[ModelInfo],
        complexity: TaskComplexity,
    ) -> Optional[str]:
        """Select best model from ranked list and log selection. Issue #620.

        Args:
            ranked_models: Models ranked by performance score
            complexity: Task complexity for logging

        Returns:
            Name of selected model, or None if no models available
        """
        selected_model = ranked_models[0] if ranked_models else None

        if selected_model:
            self.logger.info(
                f"Selected model: {selected_model.name} "
                f"(complexity: {complexity.value}, "
                f"performance: {selected_model.performance_level.value})"
            )
            return selected_model.name

        return None

    async def select_optimal_model(self, task_request: TaskRequest) -> Optional[str]:
        """Select the optimal model for a given task. Issue #620."""
        try:
            # Ensure we have fresh model data
            if not self._models_cache:
                await self.refresh_available_models()

            if not self._models_cache:
                self.logger.error("No models available")
                return None

            # Analyze task complexity and get resources
            complexity = task_request.analyze_complexity(self.complexity_keywords)
            resources = self._resource_analyzer.get_current_resources()

            # Filter by complexity
            suitable_models = self._filter_suitable_models(complexity)
            if suitable_models is None:
                return list(self._models_cache.keys())[0]

            # Filter by resources and rank
            resource_filtered = self._apply_resource_filtering(
                suitable_models, resources
            )
            ranked_models = self._model_selector.rank_by_performance(
                resource_filtered, task_request
            )

            return self._select_and_log_model(ranked_models, complexity)

        except Exception as e:
            self.logger.error("Error selecting optimal model: %s", e)
            return list(self._models_cache.keys())[0] if self._models_cache else None

    # Backward compatibility methods
    def _filter_models_by_complexity(
        self, complexity: TaskComplexity, models: List[ModelInfo]
    ) -> List[ModelInfo]:
        """Filter models based on task complexity requirements."""
        return self._model_selector.filter_by_complexity(models, complexity)

    def _filter_models_by_resources(
        self, models: List[ModelInfo], resources: Dict[str, float]
    ) -> List[ModelInfo]:
        """Filter models based on available system resources."""
        system_resources = SystemResources(
            cpu_percent=resources.get("cpu_percent", 50.0),
            memory_percent=resources.get("memory_percent", 50.0),
            available_memory_gb=resources.get("available_memory_gb", 8.0),
        )
        return self._model_selector.filter_by_resources(models, system_resources)

    def _rank_models_by_performance(
        self, models: List[ModelInfo], task_request: TaskRequest
    ) -> List[ModelInfo]:
        """Rank models by expected performance for the task."""
        return self._model_selector.rank_by_performance(models, task_request)

    async def track_model_performance(
        self, model_name: str, response_time: float, response_tokens: int, success: bool
    ):
        """Track model performance for future optimization."""
        try:
            tokens_per_second = (
                response_tokens / response_time if response_time > 0 else 0
            )
            await self._save_model_performance(
                model_name, response_time, tokens_per_second, success
            )
        except Exception as e:
            self.logger.error("Error tracking performance for %s: %s", model_name, e)

    async def get_optimization_suggestions(self) -> List[Dict[str, Any]]:
        """Get suggestions for model optimization."""
        try:
            if not self._models_cache:
                await self.refresh_available_models()

            models_with_history = [
                m for m in self._models_cache.values() if m.use_count > 0
            ]

            if not models_with_history:
                return [self._build_no_history_suggestion()]

            suggestions = []
            avg_success_rate = sum(m.success_rate for m in models_with_history) / len(
                models_with_history
            )
            avg_response_time = sum(
                m.avg_response_time for m in models_with_history
            ) / len(models_with_history)

            suggestions.extend(
                self._check_underperforming_models(
                    models_with_history, avg_success_rate
                )
            )
            suggestions.extend(
                self._check_slow_models(models_with_history, avg_response_time)
            )
            suggestions.extend(
                self._check_overused_lightweight_models(models_with_history)
            )
            suggestions.extend(self._check_resource_optimization())

            return suggestions

        except Exception as e:
            self.logger.error("Error generating optimization suggestions: %s", e)
            return [{"type": "error", "message": str(e)}]

    def _build_no_history_suggestion(self) -> Dict[str, Any]:
        """Build suggestion for no usage history."""
        return {
            "type": "info",
            "message": "No model usage history available yet",
            "action": "Continue using the system to build performance profiles",
        }

    def _check_underperforming_models(
        self, models: List[ModelInfo], avg_success_rate: float
    ) -> List[Dict[str, Any]]:
        """Check for underperforming models."""
        underperforming = [m for m in models if m.is_underperforming(avg_success_rate)]
        if not underperforming:
            return []
        return [
            {
                "type": "warning",
                "message": f"Found {len(underperforming)} underperforming models",
                "models": [m.name for m in underperforming],
                "action": "Consider avoiding these models or investigating issues",
            }
        ]

    def _check_slow_models(
        self, models: List[ModelInfo], avg_response_time: float
    ) -> List[Dict[str, Any]]:
        """Check for slow models."""
        slow_models = [m for m in models if m.is_slow(avg_response_time)]
        if not slow_models:
            return []
        return [
            {
                "type": "performance",
                "message": f"Found {len(slow_models)} slow models",
                "models": [
                    {"name": m.name, "avg_time": f"{m.avg_response_time:.2f}s"}
                    for m in slow_models
                ],
                "action": "Consider using faster alternatives for time-sensitive tasks",
            }
        ]

    def _check_overused_lightweight_models(
        self, models: List[ModelInfo]
    ) -> List[Dict[str, Any]]:
        """Check for overused lightweight models."""
        lightweight_overused = [m for m in models if m.is_overused_lightweight()]
        if not lightweight_overused:
            return []
        return [
            {
                "type": "optimization",
                "message": "Heavily used lightweight models detected",
                "models": [m.name for m in lightweight_overused],
                "action": "Consider upgrading to more capable models for better quality",
            }
        ]

    def _check_resource_optimization(self) -> List[Dict[str, Any]]:
        """Check for resource optimization opportunities."""
        resources = self._resource_analyzer.get_current_resources()
        if not resources.allows_large_models():
            return []

        large_models = [
            m
            for m in self._models_cache.values()
            if m.performance_level == ModelPerformanceLevel.ADVANCED
        ]
        if not large_models:
            return []

        return [
            {
                "type": "resource",
                "message": "System has available resources for larger models",
                "available_models": [m.name for m in large_models],
                "action": "Consider using more capable models for better results",
            }
        ]


# Global optimizer instance (thread-safe)
_model_optimizer: Optional[ModelOptimizer] = None
_model_optimizer_lock = threading.Lock()


def get_model_optimizer() -> ModelOptimizer:
    """Get the global model optimizer instance (thread-safe)."""
    global _model_optimizer
    if _model_optimizer is None:
        with _model_optimizer_lock:
            # Double-check after acquiring lock
            if _model_optimizer is None:
                _model_optimizer = ModelOptimizer()
    return _model_optimizer
