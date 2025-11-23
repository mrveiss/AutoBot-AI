# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Ollama Model Performance Optimizer
Intelligently manages and optimizes LLM model usage based on task complexity,
performance requirements, and system resources.
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import psutil
import yaml

from src.unified_config_manager import UnifiedConfigManager

# Create singleton config instance
config = UnifiedConfigManager()
from src.constants.network_constants import NetworkConstants
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
class ModelInfo:
    """Information about an available model"""

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


@dataclass
class TaskRequest:
    """A request for model optimization"""

    query: str
    task_type: str  # 'chat', 'code', 'analysis', etc.
    max_response_time: Optional[float] = None
    min_quality: Optional[float] = None
    context_length: int = 0
    user_preference: Optional[str] = None


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
            default_model = os.getenv("AUTOBOT_DEFAULT_LLM_MODEL", "llama3.2:1b")
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
            default_model = os.getenv("AUTOBOT_DEFAULT_LLM_MODEL", "llama3.2:1b")
            logging.error(
                f"Error loading model classifications: {e}, using default: {default_model}"
            )
            return {
                ModelPerformanceLevel.LIGHTWEIGHT: [default_model],
                ModelPerformanceLevel.STANDARD: [default_model],
                ModelPerformanceLevel.ADVANCED: [default_model],
            }

    def __init__(self):
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

    async def _get_redis_client(self):
        """Get Redis client for caching performance data"""
        if self._redis_client is None:
            try:
                self._redis_client = get_redis_client(
                    async_client=True, db=config.get("redis.databases.llm_cache.db", 5)
                )
                if asyncio.iscoroutine(self._redis_client):
                    self._redis_client = await self._redis_client
            except Exception as e:
                self.logger.error(
                    f"Failed to initialize Redis client for model optimization: {e}"
                )
                self._redis_client = None
        return self._redis_client

    async def refresh_available_models(self) -> List[ModelInfo]:
        """Refresh the list of available models from Ollama"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self._ollama_base_url}/api/tags") as response:
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
            pass

        # Default classification
        return ModelPerformanceLevel.STANDARD

    async def _load_model_performance_history(self, model_info: ModelInfo):
        """Load historical performance data for a model"""
        try:
            redis_client = await self._get_redis_client()
            if not redis_client:
                return

            key = f"model_perf:{model_info.name}"
            perf_data = await redis_client.hgetall(key)

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
                    perf_data.get(b"success_rate") or perf_data.get("success_rate", 1.0)
                )
                model_info.last_used = float(
                    perf_data.get(b"last_used") or perf_data.get("last_used", 0)
                )
                model_info.use_count = int(
                    perf_data.get(b"use_count") or perf_data.get("use_count", 0)
                )

        except Exception as e:
            self.logger.error(
                f"Error loading performance history for {model_info.name}: {e}"
            )

    async def _save_model_performance(
        self,
        model_name: str,
        response_time: float,
        tokens_per_second: float,
        success: bool,
    ):
        """Save performance metrics for a model"""
        try:
            redis_client = await self._get_redis_client()
            if not redis_client:
                return

            key = f"model_perf:{model_name}"

            # Get existing data
            existing = await redis_client.hgetall(key)

            # Calculate running averages
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

                # Running average calculation
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

            # Save updated metrics
            await redis_client.hset(
                key,
                mapping={
                    "avg_response_time": str(new_avg_response),
                    "avg_tokens_per_second": str(new_avg_tokens),
                    "success_rate": str(new_success_rate),
                    "last_used": str(time.time()),
                    "use_count": str(new_count),
                },
            )

            # Set TTL
            await redis_client.expire(key, self._cache_ttl)

        except Exception as e:
            self.logger.error(f"Error saving performance for {model_name}: {e}")

    def analyze_task_complexity(self, task_request: TaskRequest) -> TaskComplexity:
        """Analyze task complexity based on query content and type"""
        query_lower = task_request.query.lower()
        task_type = task_request.task_type.lower()

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

        for complexity, keywords in self.complexity_keywords.items():
            for keyword in keywords:
                if keyword in query_lower:
                    complexity_scores[complexity] += 1

        # Consider query length as a factor
        query_length = len(task_request.query.split())
        if query_length > 50:
            complexity_scores[TaskComplexity.COMPLEX] += 1

        # Consider context length
        if task_request.context_length > 1000:
            complexity_scores[TaskComplexity.COMPLEX] += 1

        # Return highest scoring complexity
        if max(complexity_scores.values()) == 0:
            return TaskComplexity.MODERATE  # Default

        return max(complexity_scores.keys(), key=lambda k: complexity_scores[k])

    def get_system_resources(self) -> Dict[str, float]:
        """Get current system resource utilization"""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()

            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "available_memory_gb": memory.available / (1024**3),
            }
        except Exception as e:
            self.logger.error(f"Error getting system resources: {e}")
            return {
                "cpu_percent": 50.0,  # Conservative defaults
                "memory_percent": 50.0,
                "available_memory_gb": 8.0,
            }

    async def select_optimal_model(self, task_request: TaskRequest) -> Optional[str]:
        """Select the optimal model for a given task"""
        try:
            # Ensure we have fresh model data
            if not self._models_cache:
                await self.refresh_available_models()

            if not self._models_cache:
                self.logger.error("No models available")
                return None

            # Analyze task
            complexity = self.analyze_task_complexity(task_request)
            resources = self.get_system_resources()

            # Get suitable models based on complexity
            suitable_models = self._filter_models_by_complexity(
                complexity, list(self._models_cache.values())
            )

            if not suitable_models:
                self.logger.warning(
                    f"No suitable models found for complexity: {complexity}"
                )
                return list(self._models_cache.keys())[0]  # Fallback to first available

            # Filter by resource constraints
            resource_filtered = self._filter_models_by_resources(
                suitable_models, resources
            )

            if not resource_filtered:
                self.logger.warning(
                    "No models pass resource filtering, using least resource-intensive"
                )
                resource_filtered = sorted(suitable_models, key=lambda m: m.size_gb)[:1]

            # Score and rank models
            ranked_models = self._rank_models_by_performance(
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

    def _filter_models_by_complexity(
        self, complexity: TaskComplexity, models: List[ModelInfo]
    ) -> List[ModelInfo]:
        """Filter models based on task complexity requirements"""
        if complexity == TaskComplexity.SIMPLE:
            # Simple tasks can use any model, prefer lightweight for efficiency
            return models
        elif complexity == TaskComplexity.MODERATE:
            # Moderate tasks need at least standard models
            return [
                m
                for m in models
                if m.performance_level
                in [
                    ModelPerformanceLevel.STANDARD,
                    ModelPerformanceLevel.ADVANCED,
                    ModelPerformanceLevel.SPECIALIZED,
                ]
            ]
        elif complexity == TaskComplexity.COMPLEX:
            # Complex tasks need advanced models
            return [
                m
                for m in models
                if m.performance_level
                in [ModelPerformanceLevel.ADVANCED, ModelPerformanceLevel.SPECIALIZED]
            ]
        else:  # SPECIALIZED
            # Specialized tasks prefer the most capable models
            advanced_models = [
                m
                for m in models
                if m.performance_level == ModelPerformanceLevel.ADVANCED
            ]
            return advanced_models if advanced_models else models

    def _filter_models_by_resources(
        self, models: List[ModelInfo], resources: Dict[str, float]
    ) -> List[ModelInfo]:
        """Filter models based on available system resources"""
        available_memory_gb = resources.get("available_memory_gb", 8.0)
        cpu_percent = resources.get("cpu_percent", 50.0)

        # If system is under high load, prefer smaller models
        if cpu_percent > 80 or available_memory_gb < 4:
            return [m for m in models if m.size_gb < 4.0]
        elif available_memory_gb < 8:
            return [m for m in models if m.size_gb < 8.0]
        else:
            return models  # No resource constraints

    def _rank_models_by_performance(
        self, models: List[ModelInfo], task_request: TaskRequest
    ) -> List[ModelInfo]:
        """Rank models by expected performance for the task"""
        scored_models = []

        for model in models:
            score = 0.0

            # Performance history scoring
            if model.use_count >= self._min_samples:
                # Favor models with good historical performance
                score += model.success_rate * 30  # Success rate weight

                # Favor faster models if response time is important
                if task_request.max_response_time and model.avg_response_time > 0:
                    if model.avg_response_time <= task_request.max_response_time:
                        score += 20
                    else:
                        score -= 10  # Penalty for slow models

                # Favor models with higher token throughput
                score += min(model.avg_tokens_per_second / 10, 20)  # Cap at 20 points
            else:
                # New models get moderate score
                score += 15

            # Model capability scoring
            if model.performance_level == ModelPerformanceLevel.ADVANCED:
                score += 25
            elif model.performance_level == ModelPerformanceLevel.STANDARD:
                score += 15
            elif model.performance_level == ModelPerformanceLevel.LIGHTWEIGHT:
                score += 5

            # Recency bonus (favor recently used models)
            if model.last_used > 0:
                recency_hours = (time.time() - model.last_used) / 3600
                if recency_hours < 24:
                    score += max(5 - recency_hours / 5, 0)  # Bonus decreases over time

            # User preference bonus
            if (
                task_request.user_preference
                and task_request.user_preference in model.name
            ):
                score += 10

            scored_models.append((model, score))

        # Sort by score (descending)
        scored_models.sort(key=lambda x: x[1], reverse=True)

        return [model for model, score in scored_models]

    async def track_model_performance(
        self, model_name: str, response_time: float, response_tokens: int, success: bool
    ):
        """Track model performance for future optimization"""
        try:
            tokens_per_second = (
                response_tokens / response_time if response_time > 0 else 0
            )
            await self._save_model_performance(
                model_name, response_time, tokens_per_second, success
            )

            # Update in-memory cache
            if model_name in self._models_cache:
                model = self._models_cache[model_name]

                # Update running averages
                if model.use_count > 0:
                    total_count = model.use_count + 1
                    model.avg_response_time = (
                        model.avg_response_time * model.use_count + response_time
                    ) / total_count
                    model.avg_tokens_per_second = (
                        model.avg_tokens_per_second * model.use_count
                        + tokens_per_second
                    ) / total_count
                    model.success_rate = (
                        model.success_rate * model.use_count + (1.0 if success else 0.0)
                    ) / total_count
                else:
                    model.avg_response_time = response_time
                    model.avg_tokens_per_second = tokens_per_second
                    model.success_rate = 1.0 if success else 0.0

                model.use_count += 1
                model.last_used = time.time()

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
                        "action": "Continue using the system to build performance profiles",
                    }
                )
                return suggestions

            # Find underperforming models
            avg_success_rate = sum(m.success_rate for m in models_with_history) / len(
                models_with_history
            )
            underperforming = [
                m
                for m in models_with_history
                if m.success_rate < avg_success_rate * 0.8
            ]

            if underperforming:
                suggestions.append(
                    {
                        "type": "warning",
                        "message": f"Found {len(underperforming)} underperforming models",
                        "models": [m.name for m in underperforming],
                        "action": "Consider avoiding these models or investigating issues",
                    }
                )

            # Find slow models
            if models_with_history:
                avg_response_time = sum(
                    m.avg_response_time for m in models_with_history
                ) / len(models_with_history)
                slow_models = [
                    m
                    for m in models_with_history
                    if m.avg_response_time > avg_response_time * 1.5
                ]

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
                            "action": "Consider using faster alternatives for time-sensitive tasks",
                        }
                    )

            # Suggest model upgrades
            lightweight_overused = [
                m
                for m in models_with_history
                if m.performance_level == ModelPerformanceLevel.LIGHTWEIGHT
                and m.use_count > 50
            ]

            if lightweight_overused:
                suggestions.append(
                    {
                        "type": "optimization",
                        "message": "Heavily used lightweight models detected",
                        "models": [m.name for m in lightweight_overused],
                        "action": "Consider upgrading to more capable models for better quality",
                    }
                )

            # Resource optimization
            resources = self.get_system_resources()
            if resources["memory_percent"] < 70 and resources["cpu_percent"] < 60:
                large_models = [
                    m
                    for m in self._models_cache.values()
                    if m.performance_level == ModelPerformanceLevel.ADVANCED
                ]
                if large_models:
                    suggestions.append(
                        {
                            "type": "resource",
                            "message": "System has available resources for larger models",
                            "available_models": [m.name for m in large_models],
                            "action": "Consider using more capable models for better results",
                        }
                    )

            return suggestions

        except Exception as e:
            self.logger.error(f"Error generating optimization suggestions: {e}")
            return [{"type": "error", "message": str(e)}]


# Global optimizer instance
_model_optimizer = None


def get_model_optimizer() -> ModelOptimizer:
    """Get the global model optimizer instance"""
    global _model_optimizer
    if _model_optimizer is None:
        _model_optimizer = ModelOptimizer()
    return _model_optimizer
