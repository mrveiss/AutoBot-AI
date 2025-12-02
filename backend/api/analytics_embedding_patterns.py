# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Embedding Usage Pattern Analyzer - Vectorization Cost Tracking API

This module provides analytics for embedding operations used in vectorization:
- Embedding request tracking
- Token usage and cost estimation
- Batch size optimization
- Model efficiency metrics
- Processing time analysis

Related Issues: #285 (Embedding Usage Tracking - Vectorizer Cost Optimization)
Parent Epic: #217 (Advanced Code Intelligence)
Related: #229 (LLM Integration Pattern Analyzer - CLOSED)
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.utils.redis_client import RedisDatabase, get_redis_client

router = APIRouter()
logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Constants
# =============================================================================


class EmbeddingProvider(str, Enum):
    """Embedding providers"""

    OLLAMA = "ollama"
    OPENAI = "openai"
    HUGGINGFACE = "huggingface"
    LOCAL = "local"


class EmbeddingOperation(str, Enum):
    """Types of embedding operations"""

    DOCUMENT_VECTORIZATION = "document_vectorization"
    QUERY_EMBEDDING = "query_embedding"
    BATCH_VECTORIZATION = "batch_vectorization"
    REINDEX = "reindex"


# Embedding model costs per 1M tokens (USD) - estimated
EMBEDDING_MODEL_COSTS = {
    # Ollama (local - free but has compute cost estimation)
    "nomic-embed-text:latest": {"cost_per_1m": 0.0, "compute_cost": 0.001},
    "nomic-embed-text": {"cost_per_1m": 0.0, "compute_cost": 0.001},
    "mxbai-embed-large:latest": {"cost_per_1m": 0.0, "compute_cost": 0.002},
    "snowflake-arctic-embed:latest": {"cost_per_1m": 0.0, "compute_cost": 0.0015},
    # OpenAI
    "text-embedding-3-small": {"cost_per_1m": 0.02, "compute_cost": 0.0},
    "text-embedding-3-large": {"cost_per_1m": 0.13, "compute_cost": 0.0},
    "text-embedding-ada-002": {"cost_per_1m": 0.10, "compute_cost": 0.0},
}

# Default cost for unknown models
DEFAULT_EMBEDDING_COST = {"cost_per_1m": 0.0, "compute_cost": 0.001}


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class EmbeddingUsageRecord:
    """Record of a single embedding operation"""

    operation_id: str
    operation_type: EmbeddingOperation
    model: str
    provider: EmbeddingProvider
    token_count: int
    document_count: int
    batch_size: int
    processing_time: float
    success: bool
    timestamp: datetime
    cost: float = 0.0
    source: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbeddingStats:
    """Aggregated embedding statistics"""

    total_operations: int
    total_tokens: int
    total_documents: int
    total_cost: float
    avg_processing_time: float
    success_rate: float
    avg_batch_size: float
    tokens_per_second: float


@dataclass
class BatchOptimizationRecommendation:
    """Recommendation for batch size optimization"""

    current_avg_batch_size: float
    recommended_batch_size: int
    potential_speedup: float
    reasoning: str


# =============================================================================
# Pydantic Models
# =============================================================================


class EmbeddingUsageRequest(BaseModel):
    """Request to record embedding usage"""

    operation_type: str = Field(
        default="document_vectorization", description="Type of embedding operation"
    )
    model: str = Field(..., description="Embedding model used")
    provider: str = Field(default="ollama", description="Embedding provider")
    token_count: int = Field(..., description="Total tokens processed")
    document_count: int = Field(default=1, description="Number of documents processed")
    batch_size: int = Field(default=1, description="Batch size used")
    processing_time: float = Field(..., description="Processing time in seconds")
    success: bool = Field(default=True, description="Whether operation succeeded")
    source: Optional[str] = Field(None, description="Source of the operation")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class EmbeddingStatsResponse(BaseModel):
    """Response model for embedding statistics"""

    total_operations: int
    total_tokens: int
    total_documents: int
    total_cost: float
    avg_processing_time: float
    success_rate: float
    avg_batch_size: float
    tokens_per_second: float
    period: str
    timestamp: str


# =============================================================================
# Embedding Pattern Analyzer Engine
# =============================================================================


class EmbeddingPatternAnalyzer:
    """Engine for analyzing embedding usage patterns and optimization"""

    def __init__(self):
        self._redis = None
        self._usage_key = "autobot:embedding_patterns:usage"
        self._stats_key = "autobot:embedding_patterns:stats"
        self._model_stats_key = "autobot:embedding_patterns:model_stats"
        self._lock = asyncio.Lock()

    async def _get_redis(self):
        """Get Redis client lazily"""
        if self._redis is None:
            async with self._lock:
                if self._redis is None:
                    self._redis = await get_redis_client(
                        async_client=True, database=RedisDatabase.ANALYTICS
                    )
        return self._redis

    def _calculate_cost(self, model: str, token_count: int) -> float:
        """Calculate cost for embedding operation"""
        model_lower = model.lower()
        cost_info = EMBEDDING_MODEL_COSTS.get(model_lower, DEFAULT_EMBEDDING_COST)

        # API cost (for cloud providers)
        api_cost = (token_count / 1_000_000) * cost_info.get("cost_per_1m", 0.0)

        # Compute cost (for local models)
        compute_cost = (token_count / 1_000_000) * cost_info.get("compute_cost", 0.0)

        return api_cost + compute_cost

    async def record_usage(self, request: EmbeddingUsageRequest) -> Dict[str, Any]:
        """Record an embedding usage event"""
        try:
            redis = await self._get_redis()
            operation_id = f"emb_{int(time.time() * 1000)}_{hash(request.model) % 10000}"

            # Calculate cost
            cost = self._calculate_cost(request.model, request.token_count)

            # Create usage record
            record = {
                "operation_id": operation_id,
                "operation_type": request.operation_type,
                "model": request.model,
                "provider": request.provider,
                "token_count": request.token_count,
                "document_count": request.document_count,
                "batch_size": request.batch_size,
                "processing_time": request.processing_time,
                "success": request.success,
                "timestamp": datetime.now().isoformat(),
                "cost": cost,
                "source": request.source or "unknown",
                "metadata": request.metadata or {},
            }

            # Store in Redis with 30-day retention
            record_key = f"{self._usage_key}:{operation_id}"
            await redis.setex(record_key, 30 * 24 * 3600, json.dumps(record))

            # Update aggregated stats
            await self._update_stats(request, cost)

            logger.debug(
                f"Recorded embedding usage: {request.document_count} docs, "
                f"{request.token_count} tokens, {request.processing_time:.3f}s"
            )

            return {
                "status": "recorded",
                "operation_id": operation_id,
                "cost": cost,
                "tokens_per_second": (
                    request.token_count / request.processing_time
                    if request.processing_time > 0
                    else 0
                ),
            }

        except Exception as e:
            logger.error(f"Failed to record embedding usage: {e}")
            return {"status": "error", "error": str(e)}

    async def _update_stats(self, request: EmbeddingUsageRequest, cost: float):
        """Update aggregated statistics"""
        try:
            redis = await self._get_redis()

            # Update daily stats
            today = datetime.now().strftime("%Y-%m-%d")
            daily_key = f"{self._stats_key}:daily:{today}"

            # Use Redis HINCRBY for atomic updates
            await redis.hincrby(daily_key, "total_operations", 1)
            await redis.hincrby(daily_key, "total_tokens", request.token_count)
            await redis.hincrby(daily_key, "total_documents", request.document_count)
            await redis.hincrbyfloat(daily_key, "total_cost", cost)
            await redis.hincrbyfloat(
                daily_key, "total_processing_time", request.processing_time
            )
            await redis.hincrby(daily_key, "total_batch_size", request.batch_size)

            if request.success:
                await redis.hincrby(daily_key, "successful_operations", 1)

            # Set TTL for daily stats (90 days)
            await redis.expire(daily_key, 90 * 24 * 3600)

            # Update model-specific stats
            model_key = f"{self._model_stats_key}:{request.model}"
            await redis.hincrby(model_key, "total_operations", 1)
            await redis.hincrby(model_key, "total_tokens", request.token_count)
            await redis.hincrbyfloat(model_key, "total_cost", cost)
            await redis.expire(model_key, 90 * 24 * 3600)

        except Exception as e:
            logger.error(f"Failed to update embedding stats: {e}")

    async def get_stats(
        self,
        days: int = 7,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get embedding usage statistics for a time period"""
        try:
            redis = await self._get_redis()

            total_ops = 0
            total_tokens = 0
            total_documents = 0
            total_cost = 0.0
            total_processing_time = 0.0
            total_batch_size = 0
            successful_ops = 0

            # Aggregate daily stats - batch fetch using pipeline to eliminate N+1
            dates = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
            daily_keys = [f"{self._stats_key}:daily:{date}" for date in dates]

            async with redis.pipeline() as pipe:
                for key in daily_keys:
                    await pipe.hgetall(key)
                all_stats = await pipe.execute()

            for stats in all_stats:
                if stats:
                    total_ops += int(stats.get(b"total_operations", 0))
                    total_tokens += int(stats.get(b"total_tokens", 0))
                    total_documents += int(stats.get(b"total_documents", 0))
                    total_cost += float(stats.get(b"total_cost", 0))
                    total_processing_time += float(
                        stats.get(b"total_processing_time", 0)
                    )
                    total_batch_size += int(stats.get(b"total_batch_size", 0))
                    successful_ops += int(stats.get(b"successful_operations", 0))

            # Calculate derived metrics
            avg_processing_time = (
                total_processing_time / total_ops if total_ops > 0 else 0
            )
            success_rate = successful_ops / total_ops if total_ops > 0 else 1.0
            avg_batch_size = total_batch_size / total_ops if total_ops > 0 else 0
            tokens_per_second = (
                total_tokens / total_processing_time if total_processing_time > 0 else 0
            )

            return {
                "status": "success",
                "stats": {
                    "total_operations": total_ops,
                    "total_tokens": total_tokens,
                    "total_documents": total_documents,
                    "total_cost": round(total_cost, 6),
                    "avg_processing_time": round(avg_processing_time, 3),
                    "success_rate": round(success_rate, 4),
                    "avg_batch_size": round(avg_batch_size, 2),
                    "tokens_per_second": round(tokens_per_second, 2),
                    "period_days": days,
                },
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to get embedding stats: {e}")
            return {"status": "error", "error": str(e)}

    async def get_model_comparison(self) -> Dict[str, Any]:
        """Get comparison of embedding model usage"""
        try:
            redis = await self._get_redis()

            # Get all model stats keys
            cursor = 0
            models = []

            while True:
                cursor, keys = await redis.scan(
                    cursor, match=f"{self._model_stats_key}:*", count=100
                )

                # Batch fetch all hashes using pipeline - eliminates N+1
                if keys:
                    async with redis.pipeline() as pipe:
                        for key in keys:
                            await pipe.hgetall(key)
                        all_stats = await pipe.execute()

                    for key, stats in zip(keys, all_stats):
                        key_str = key.decode() if isinstance(key, bytes) else key
                        model_name = key_str.split(":")[-1]

                        if stats:
                            total_ops = int(stats.get(b"total_operations", 0))
                            total_tokens = int(stats.get(b"total_tokens", 0))
                            total_cost = float(stats.get(b"total_cost", 0))

                            models.append(
                                {
                                    "model": model_name,
                                    "total_operations": total_ops,
                                    "total_tokens": total_tokens,
                                    "total_cost": round(total_cost, 6),
                                    "tokens_per_operation": (
                                        total_tokens / total_ops if total_ops > 0 else 0
                                    ),
                                }
                            )

                if cursor == 0:
                    break

            # Sort by usage
            models.sort(key=lambda x: x["total_operations"], reverse=True)

            return {
                "status": "success",
                "models": models,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to get model comparison: {e}")
            return {"status": "error", "error": str(e)}

    async def get_batch_optimization_recommendations(self) -> Dict[str, Any]:
        """Get recommendations for batch size optimization"""
        try:
            stats = await self.get_stats(days=7)

            if stats.get("status") != "success":
                return stats

            current_stats = stats.get("stats", {})
            avg_batch_size = current_stats.get("avg_batch_size", 1)
            tokens_per_second = current_stats.get("tokens_per_second", 0)

            recommendations = []

            # Batch size optimization
            if avg_batch_size < 10:
                recommendations.append(
                    {
                        "type": "increase_batch_size",
                        "current_value": round(avg_batch_size, 2),
                        "recommended_value": 50,
                        "potential_improvement": "2-3x throughput increase",
                        "reasoning": (
                            "Current batch size is low. Increasing to 50 documents "
                            "per batch can significantly improve throughput."
                        ),
                    }
                )
            elif avg_batch_size > 100:
                recommendations.append(
                    {
                        "type": "reduce_batch_size",
                        "current_value": round(avg_batch_size, 2),
                        "recommended_value": 50,
                        "potential_improvement": "Better memory efficiency",
                        "reasoning": (
                            "Large batch sizes may cause memory issues. "
                            "Consider reducing to 50 for stability."
                        ),
                    }
                )

            # Throughput optimization
            if tokens_per_second < 1000:
                recommendations.append(
                    {
                        "type": "improve_throughput",
                        "current_value": round(tokens_per_second, 2),
                        "recommended_value": 5000,
                        "potential_improvement": "5x speed increase",
                        "reasoning": (
                            "Low throughput detected. Consider using GPU acceleration "
                            "or switching to a faster embedding model."
                        ),
                    }
                )

            return {
                "status": "success",
                "recommendations": recommendations,
                "current_stats": current_stats,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to get optimization recommendations: {e}")
            return {"status": "error", "error": str(e)}


# =============================================================================
# Global Analyzer Instance
# =============================================================================

import threading

_embedding_analyzer: Optional[EmbeddingPatternAnalyzer] = None
_embedding_analyzer_lock = threading.Lock()


def get_embedding_analyzer() -> EmbeddingPatternAnalyzer:
    """Get or create the global embedding analyzer (thread-safe)."""
    global _embedding_analyzer
    if _embedding_analyzer is None:
        with _embedding_analyzer_lock:
            if _embedding_analyzer is None:
                _embedding_analyzer = EmbeddingPatternAnalyzer()
    return _embedding_analyzer


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/record")
async def record_embedding_usage(request: EmbeddingUsageRequest):
    """Record an embedding usage event"""
    analyzer = get_embedding_analyzer()
    result = await analyzer.record_usage(request)

    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error"))

    return JSONResponse(
        status_code=200,
        content=result,
    )


@router.get("/stats")
async def get_embedding_stats(
    days: int = Query(default=7, ge=1, le=90, description="Number of days to analyze"),
    model: Optional[str] = Query(None, description="Filter by model"),
):
    """Get embedding usage statistics"""
    analyzer = get_embedding_analyzer()
    result = await analyzer.get_stats(days=days, model=model)

    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error"))

    return JSONResponse(
        status_code=200,
        content=result,
    )


@router.get("/model-comparison")
async def get_model_comparison():
    """Get comparison of embedding model usage"""
    analyzer = get_embedding_analyzer()
    result = await analyzer.get_model_comparison()

    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error"))

    return JSONResponse(
        status_code=200,
        content=result,
    )


@router.get("/optimization-recommendations")
async def get_optimization_recommendations():
    """Get batch optimization recommendations"""
    analyzer = get_embedding_analyzer()
    result = await analyzer.get_batch_optimization_recommendations()

    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error"))

    return JSONResponse(
        status_code=200,
        content=result,
    )


@router.get("/health")
async def embedding_analytics_health():
    """Health check for embedding analytics"""
    try:
        analyzer = get_embedding_analyzer()
        redis = await analyzer._get_redis()
        await redis.ping()

        return JSONResponse(
            status_code=200,
            content={
                "status": "healthy",
                "service": "embedding_analytics",
                "redis_connected": True,
                "timestamp": datetime.now().isoformat(),
            },
        )
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": "embedding_analytics",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            },
        )
