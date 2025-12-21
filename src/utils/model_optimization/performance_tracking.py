# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Performance Tracking Module

Issue #381: Extracted from model_optimizer.py god class refactoring.
Contains model performance tracking and persistence to Redis.
"""

import logging
import time
from typing import Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from .types import ModelInfo

logger = logging.getLogger(__name__)


class ModelPerformanceTracker:
    """Manages performance tracking and persistence to Redis (Tell Don't Ask)."""

    def __init__(self, redis_client, cache_ttl: int, logger_instance=None):
        """Initialize tracker with Redis client, TTL, and logger."""
        self._redis_client = redis_client
        self._cache_ttl = cache_ttl
        self._logger = logger_instance or logger

    async def load_performance(self, model_info: "ModelInfo") -> None:
        """Load performance history from Redis into ModelInfo."""
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
        """Save performance metrics from ModelInfo to Redis."""
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
            self._logger.error("Error saving performance for %s: %s", model_info.name, e)

    async def update_and_save(
        self,
        model_name: str,
        response_time: float,
        tokens_per_second: float,
        success: bool,
        model_cache: Dict[str, "ModelInfo"],
    ) -> None:
        """Update model performance and persist - one method does both."""
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
        """Update Redis when model not in cache (fallback path)."""
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
            self._logger.error("Error saving performance for %s: %s", model_name, e)
