# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Integration Pattern Analyzer - Cost Optimization API

This module provides intelligent analysis of LLM usage patterns for cost optimization:
- Prompt analysis and pattern detection
- Token usage tracking and trends
- Caching opportunity identification
- Model usage efficiency metrics
- Cost-per-task analysis
- Optimization recommendations

Related Issues: #229 (LLM Integration Pattern Analyzer)
"""

import asyncio
import hashlib
import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from redis.exceptions import RedisError

from src.utils.redis_client import RedisDatabase, get_redis_client

# Issue #552: Added prefix to match frontend calls at /api/llm-patterns/*
router = APIRouter(prefix="/llm-patterns", tags=["llm-patterns", "analytics"])
logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Constants
# =============================================================================

# O(1) lookup optimization constant (Issue #326)
EXPENSIVE_MODELS = {"opus", "gpt-4"}


class PromptCategory(str, Enum):
    """Categories of LLM prompts"""

    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    DOCUMENTATION = "documentation"
    ANALYSIS = "analysis"
    CHAT = "chat"
    TASK_PLANNING = "task_planning"
    TRANSLATION = "translation"
    SUMMARIZATION = "summarization"
    UNKNOWN = "unknown"


class OptimizationType(str, Enum):
    """Types of optimization opportunities"""

    CACHE_PROMPT = "cache_prompt"
    USE_SMALLER_MODEL = "use_smaller_model"
    REDUCE_CONTEXT = "reduce_context"
    BATCH_REQUESTS = "batch_requests"
    TEMPLATE_REUSE = "template_reuse"


class CostLevel(str, Enum):
    """Cost level classification"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Simple prompt categories that don't require expensive models (O(1) lookup)
SIMPLE_PROMPT_CATEGORIES = {
    PromptCategory.CHAT,
    PromptCategory.TRANSLATION,
    PromptCategory.SUMMARIZATION,
}


# Model costs per 1M tokens (USD)
MODEL_COSTS = {
    # Anthropic
    "claude-3-opus": {"input": 15.00, "output": 75.00},
    "claude-3-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-haiku": {"input": 0.25, "output": 1.25},
    "claude-sonnet-4": {"input": 3.00, "output": 15.00},
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    # Google
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    # Local (free)
    "llama3": {"input": 0.0, "output": 0.0},
    "mistral": {"input": 0.0, "output": 0.0},
    "codellama": {"input": 0.0, "output": 0.0},
}

# Pattern detection rules for prompt categorization
PROMPT_PATTERNS = {
    PromptCategory.CODE_GENERATION: [
        r"generate\s+(?:code|function|class|method)",
        r"write\s+(?:a\s+)?(?:python|javascript|typescript)",
        r"create\s+(?:a\s+)?(?:function|class|script)",
        r"implement\s+",
        r"code\s+(?:for|that|to)\s+",
    ],
    PromptCategory.CODE_REVIEW: [
        r"review\s+(?:this\s+)?code",
        r"check\s+(?:for\s+)?(?:bugs|errors|issues)",
        r"improve\s+(?:this\s+)?code",
        r"refactor\s+",
        r"optimize\s+(?:this\s+)?code",
    ],
    PromptCategory.DOCUMENTATION: [
        r"document\s+",
        r"write\s+(?:a\s+)?docstring",
        r"add\s+(?:comments|documentation)",
        r"explain\s+(?:this\s+)?code",
        r"readme\s+",
    ],
    PromptCategory.ANALYSIS: [
        r"analyze\s+",
        r"find\s+(?:bugs|issues|problems)",
        r"debug\s+",
        r"investigate\s+",
        r"diagnose\s+",
    ],
    PromptCategory.TASK_PLANNING: [
        r"plan\s+(?:the\s+)?(?:task|project|implementation)",
        r"break\s+down\s+",
        r"steps\s+to\s+",
        r"how\s+(?:should|would)\s+(?:I|we)",
        r"strategy\s+for\s+",
    ],
    PromptCategory.TRANSLATION: [
        r"translate\s+",
        r"convert\s+(?:to|from)\s+",
        r"rewrite\s+in\s+",
    ],
    PromptCategory.SUMMARIZATION: [
        r"summarize\s+",
        r"summary\s+of\s+",
        r"tldr\s+",
        r"brief\s+overview",
    ],
}


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class PromptUsageRecord:
    """Record of a single prompt usage"""

    prompt_hash: str
    prompt_preview: str
    category: PromptCategory
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    timestamp: datetime
    response_time: float
    success: bool
    session_id: Optional[str] = None


@dataclass
class CacheOpportunity:
    """Identified caching opportunity"""

    prompt_hash: str
    prompt_preview: str
    occurrence_count: int
    potential_savings: float
    avg_tokens: int
    recommendation: str


@dataclass
class OptimizationRecommendation:
    """Optimization recommendation"""

    type: OptimizationType
    title: str
    description: str
    potential_savings: float
    priority: int
    affected_prompts: int
    implementation_steps: List[str]


@dataclass
class ModelUsageStats:
    """Usage statistics for a model"""

    model: str
    request_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost: float
    avg_response_time: float
    success_rate: float
    cost_per_request: float


# =============================================================================
# Pydantic Models
# =============================================================================


class PromptAnalysisRequest(BaseModel):
    """Request for prompt analysis"""

    prompt: str = Field(..., description="The prompt to analyze")
    model: Optional[str] = Field(None, description="Model used or planned")


class UsageRecordRequest(BaseModel):
    """Request to record LLM usage"""

    prompt: str = Field(..., description="The prompt sent")
    model: str = Field(..., description="Model used")
    input_tokens: int = Field(..., description="Input token count")
    output_tokens: int = Field(..., description="Output token count")
    response_time: float = Field(..., description="Response time in seconds")
    success: bool = Field(default=True)
    session_id: Optional[str] = Field(None)

    # === Issue #372: Feature Envy Reduction Methods ===

    def to_record_dict(
        self,
        prompt_hash: str,
        prompt_preview: str,
        category_value: str,
        cost: float,
    ) -> Dict[str, Any]:
        """Convert to record dictionary for storage (Issue #372 - reduces feature envy)."""
        return {
            "prompt_hash": prompt_hash,
            "prompt_preview": prompt_preview,
            "category": category_value,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost": cost,
            "timestamp": datetime.now().isoformat(),
            "response_time": self.response_time,
            "success": self.success,
            "session_id": self.session_id,
        }


class DateRangeParams(BaseModel):
    """Date range parameters"""

    start_date: Optional[str] = Field(None, description="Start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="End date (YYYY-MM-DD)")


# =============================================================================
# Pattern Analyzer Engine
# =============================================================================


class LLMPatternAnalyzer:
    """Engine for analyzing LLM usage patterns and identifying optimizations"""

    def __init__(self):
        """Initialize LLM pattern analyzer with Redis storage keys."""
        self._redis = None
        self._usage_key = "autobot:llm_patterns:usage"
        self._cache_key = "autobot:llm_patterns:cache"
        self._stats_key = "autobot:llm_patterns:stats"

    async def _get_redis(self):
        """Get Redis client lazily"""
        if self._redis is None:
            self._redis = await get_redis_client(
                async_client=True, database=RedisDatabase.MAIN
            )
        return self._redis

    def _hash_prompt(self, prompt: str) -> str:
        """Create a hash of the prompt for caching detection"""
        # Normalize prompt (lowercase, remove extra whitespace)
        normalized = " ".join(prompt.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def _categorize_prompt(self, prompt: str) -> PromptCategory:
        """Categorize a prompt based on pattern matching"""
        prompt_lower = prompt.lower()

        for category, patterns in PROMPT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, prompt_lower):
                    return category

        return PromptCategory.UNKNOWN

    def _calculate_cost(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Calculate cost for a request"""
        # Find matching model pricing
        model_lower = model.lower()
        pricing = None

        for model_name, costs in MODEL_COSTS.items():
            if model_name in model_lower or model_lower in model_name:
                pricing = costs
                break

        if not pricing:
            # Default to medium pricing
            pricing = {"input": 1.0, "output": 5.0}

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        return round(input_cost + output_cost, 6)

    def _get_prompt_preview(self, prompt: str, max_length: int = 100) -> str:
        """Get a preview of the prompt"""
        if len(prompt) <= max_length:
            return prompt
        return prompt[: max_length - 3] + "..."

    async def analyze_prompt(
        self, prompt: str, model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Analyze a single prompt for optimization opportunities"""
        prompt_hash = self._hash_prompt(prompt)
        category = self._categorize_prompt(prompt)

        # Count tokens (rough estimation)
        token_estimate = len(prompt.split()) * 1.3

        # Check for potential issues
        issues = []
        recommendations = []

        # Check prompt length
        if token_estimate > 2000:
            issues.append(
                {
                    "type": "long_prompt",
                    "message": "Prompt is very long, consider reducing context",
                    "severity": "warning",
                }
            )
            recommendations.append("Consider extracting only relevant code sections")

        # Check for redundancy
        words = prompt.lower().split()
        word_freq = defaultdict(int)
        for word in words:
            if len(word) > 4:
                word_freq[word] += 1

        repeated_words = [w for w, c in word_freq.items() if c > 3]
        if repeated_words:
            issues.append(
                {
                    "type": "redundancy",
                    "message": f"Possible redundancy detected: {', '.join(repeated_words[:5])}",
                    "severity": "info",
                }
            )

        # Check for caching potential
        try:
            redis = await self._get_redis()
            cache_key = f"{self._cache_key}:{prompt_hash}"
            cached = await redis.get(cache_key)

            if cached:
                cache_data = json.loads(cached)
                recommendations.append(
                    f"This prompt has been used {cache_data.get('count', 1)} times. "
                    "Consider caching the response."
                )
        except RedisError as e:
            logger.warning("Failed to check cache for prompt analysis: %s", e)
            cached = None

        # Model recommendations
        if model:
            if "opus" in model.lower() or "gpt-4" in model.lower():
                if category in SIMPLE_PROMPT_CATEGORIES:  # O(1) lookup (Issue #326)
                    recommendations.append(
                        "Consider using a smaller model (Haiku/GPT-3.5) for this task type"
                    )

        return {
            "prompt_hash": prompt_hash,
            "category": category.value,
            "estimated_tokens": int(token_estimate),
            "estimated_cost": self._calculate_cost(
                model or "gpt-4o", int(token_estimate), int(token_estimate * 1.5)
            ),
            "issues": issues,
            "recommendations": recommendations,
            "cache_potential": cached is not None,
        }

    async def record_usage(self, request: UsageRecordRequest) -> Dict[str, Any]:
        """Record an LLM usage event (Issue #372 - uses model methods)."""
        prompt_hash = self._hash_prompt(request.prompt)
        category = self._categorize_prompt(request.prompt)
        cost = self._calculate_cost(
            request.model, request.input_tokens, request.output_tokens
        )

        # Issue #372: Use model method to reduce feature envy
        record = request.to_record_dict(
            prompt_hash=prompt_hash,
            prompt_preview=self._get_prompt_preview(request.prompt),
            category_value=category.value,
            cost=cost,
        )

        try:
            redis = await self._get_redis()

            # Store usage record
            date_key = datetime.now().strftime("%Y-%m-%d")
            usage_key = f"{self._usage_key}:{date_key}"
            await redis.lpush(usage_key, json.dumps(record))
            await redis.expire(usage_key, 30 * 24 * 60 * 60)  # 30 days

            # Update cache tracking
            cache_key = f"{self._cache_key}:{prompt_hash}"
            cache_data = await redis.get(cache_key)

            if cache_data:
                data = json.loads(cache_data)
                data["count"] = data.get("count", 0) + 1
                data["total_cost"] = data.get("total_cost", 0) + cost
                data["last_seen"] = datetime.now().isoformat()
            else:
                data = {
                    "count": 1,
                    "total_cost": cost,
                    "first_seen": datetime.now().isoformat(),
                    "last_seen": datetime.now().isoformat(),
                    "preview": self._get_prompt_preview(request.prompt),
                }

            await redis.set(cache_key, json.dumps(data))
            await redis.expire(cache_key, 30 * 24 * 60 * 60)

            # Update stats
            await self._update_stats(request.model, cost, request.success)

            return {
                "recorded": True,
                "prompt_hash": prompt_hash,
                "category": category.value,
                "cost": cost,
                "cache_count": data["count"],
            }
        except RedisError as e:
            logger.error("Failed to record LLM usage: %s", e)
            raise RuntimeError(f"Failed to record LLM usage: {e}")

    async def _update_stats(self, model: str, cost: float, success: bool):
        """Update aggregate statistics.

        Issue #379: Uses Redis pipeline to batch all HINCRBY operations,
        eliminating 4-5 sequential await round-trips.
        """
        try:
            redis = await self._get_redis()
            date_key = datetime.now().strftime("%Y-%m-%d")
            stats_key = f"{self._stats_key}:{date_key}"

            # Issue #379: Batch all Redis operations using pipeline
            async with redis.pipeline() as pipe:
                await pipe.hincrby(stats_key, "total_requests", 1)
                await pipe.hincrbyfloat(stats_key, "total_cost", cost)
                await pipe.hincrby(stats_key, f"model:{model}", 1)

                if success:
                    await pipe.hincrby(stats_key, "successful_requests", 1)

                await pipe.expire(stats_key, 30 * 24 * 60 * 60)
                await pipe.execute()
        except RedisError as e:
            logger.warning("Failed to update LLM stats: %s", e)

    def _aggregate_day_stats(
        self, date: str, day_stats: dict, stats: Dict[str, Any]
    ) -> None:
        """Aggregate statistics for a single day. (Issue #315 - extracted)"""
        if not day_stats:
            return

        day_requests = int(day_stats.get("total_requests", 0))
        day_cost = float(day_stats.get("total_cost", 0))
        day_success = int(day_stats.get("successful_requests", 0))

        stats["total_requests"] += day_requests
        stats["total_cost"] += day_cost
        stats["successful_requests"] += day_success

        stats["by_date"].append(
            {
                "date": date,
                "requests": day_requests,
                "cost": round(day_cost, 4),
                "success_rate": (
                    round(day_success / day_requests * 100, 1)
                    if day_requests > 0
                    else 0
                ),
            }
        )

        # Extract model stats
        for key, value in day_stats.items():
            if key.startswith("model:"):
                model = key[6:]
                if model not in stats["by_model"]:
                    stats["by_model"][model] = 0
                stats["by_model"][model] += int(value)

    async def get_usage_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get usage statistics for the specified period"""
        stats = {
            "period_days": days,
            "total_requests": 0,
            "total_cost": 0.0,
            "successful_requests": 0,
            "by_date": [],
            "by_model": {},
            "by_category": {},
        }

        try:
            redis = await self._get_redis()

            # Build date keys and fetch all at once using pipeline - eliminates N+1 queries
            dates = [
                (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                for i in range(days)
            ]
            stats_keys = [f"{self._stats_key}:{date}" for date in dates]

            async with redis.pipeline() as pipe:
                for key in stats_keys:
                    await pipe.hgetall(key)
                all_day_stats = await pipe.execute()

            # Aggregate day stats using helper (Issue #315 - reduced depth)
            for date, day_stats in zip(dates, all_day_stats):
                self._aggregate_day_stats(date, day_stats, stats)

            # Calculate averages
            if stats["total_requests"] > 0:
                stats["avg_cost_per_request"] = round(
                    stats["total_cost"] / stats["total_requests"], 6
                )
                stats["success_rate"] = round(
                    stats["successful_requests"] / stats["total_requests"] * 100, 1
                )
            else:
                stats["avg_cost_per_request"] = 0
                stats["success_rate"] = 100

            stats["total_cost"] = round(stats["total_cost"], 4)

            return stats
        except RedisError as e:
            logger.error("Failed to get usage stats: %s", e)
            raise RuntimeError(f"Failed to get usage stats: {e}")

    def _parse_cache_opportunity(
        self, key: str, data: str, min_occurrences: int
    ) -> Optional[Dict[str, Any]]:
        """Parse a cache opportunity from Redis data. (Issue #315 - extracted)"""
        if not data:
            return None
        cache_info = json.loads(data)
        if cache_info.get("count", 0) < min_occurrences:
            return None
        return {
            "prompt_hash": key.split(":")[-1],
            "prompt_preview": cache_info.get("preview", ""),
            "occurrence_count": cache_info["count"],
            "total_cost": round(cache_info.get("total_cost", 0), 4),
            "potential_savings": round(cache_info.get("total_cost", 0) * 0.9, 4),
            "first_seen": cache_info.get("first_seen"),
            "last_seen": cache_info.get("last_seen"),
        }

    async def identify_cache_opportunities(
        self, min_occurrences: int = 3
    ) -> List[Dict[str, Any]]:
        """Identify prompts that could benefit from caching"""
        opportunities = []

        try:
            redis = await self._get_redis()
            cursor = 0

            while True:
                cursor, keys = await redis.scan(
                    cursor, match=f"{self._cache_key}:*", count=100
                )

                # Batch fetch and parse (Issue #315 - use list comp to reduce depth)
                if keys:
                    all_data = await redis.mget(keys)
                    parsed = [
                        self._parse_cache_opportunity(k, d, min_occurrences)
                        for k, d in zip(keys, all_data)
                    ]
                    opportunities.extend(o for o in parsed if o)

                if cursor == 0:
                    break

            opportunities.sort(key=lambda x: x["potential_savings"], reverse=True)
            return opportunities[:20]
        except RedisError as e:
            logger.error("Failed to identify cache opportunities: %s", e)
            raise RuntimeError(f"Failed to identify cache opportunities: {e}")

    def _build_caching_recommendation(
        self, cache_opportunities: List[Dict]
    ) -> Optional[Dict[str, Any]]:
        """Build caching recommendation if applicable (Issue #665: extracted helper)."""
        if not cache_opportunities:
            return None
        total_savings = sum(o["potential_savings"] for o in cache_opportunities)
        return {
            "type": OptimizationType.CACHE_PROMPT.value,
            "title": "Implement Prompt Caching",
            "description": f"Found {len(cache_opportunities)} frequently repeated prompts",
            "potential_savings": round(total_savings, 2),
            "priority": 1,
            "affected_prompts": len(cache_opportunities),
            "implementation_steps": [
                "Identify prompt patterns that produce consistent outputs",
                "Implement Redis-based response caching",
                "Set appropriate TTL based on data freshness needs",
                "Monitor cache hit rates",
            ],
        }

    def _build_model_downgrade_recommendation(
        self, stats: Dict, model_usage: Dict
    ) -> Optional[Dict[str, Any]]:
        """Build model downgrade recommendation if applicable (Issue #665: extracted helper)."""
        expensive_models = [
            m
            for m in model_usage
            if any(keyword in m.lower() for keyword in EXPENSIVE_MODELS)
        ]
        if not expensive_models:
            return None
        return {
            "type": OptimizationType.USE_SMALLER_MODEL.value,
            "title": "Consider Smaller Models for Simple Tasks",
            "description": f"High usage of expensive models: {', '.join(expensive_models)}",
            "potential_savings": stats["total_cost"] * 0.3,
            "priority": 2,
            "affected_prompts": sum(model_usage.get(m, 0) for m in expensive_models),
            "implementation_steps": [
                "Categorize prompts by complexity",
                "Route simple tasks to Haiku/GPT-3.5-turbo",
                "Reserve powerful models for complex reasoning",
                "A/B test quality vs cost tradeoffs",
            ],
        }

    def _build_batch_processing_recommendation(
        self, stats: Dict
    ) -> Optional[Dict[str, Any]]:
        """Build batch processing recommendation if applicable (Issue #665: extracted helper)."""
        if stats["total_requests"] <= 100:
            return None
        return {
            "type": OptimizationType.BATCH_REQUESTS.value,
            "title": "Implement Request Batching",
            "description": "High request volume could benefit from batching",
            "potential_savings": stats["total_cost"] * 0.1,
            "priority": 3,
            "affected_prompts": stats["total_requests"],
            "implementation_steps": [
                "Identify requests that can be grouped",
                "Implement async batch processing",
                "Reduce per-request overhead",
                "Monitor latency vs throughput tradeoffs",
            ],
        }

    def _build_context_reduction_recommendation(self, stats: Dict) -> Dict[str, Any]:
        """Build context reduction recommendation (Issue #665: extracted helper)."""
        return {
            "type": OptimizationType.REDUCE_CONTEXT.value,
            "title": "Optimize Context Length",
            "description": "Review prompts for unnecessary context",
            "potential_savings": stats["total_cost"] * 0.2,
            "priority": 4,
            "affected_prompts": int(stats["total_requests"] * 0.3),
            "implementation_steps": [
                "Analyze prompt lengths and identify outliers",
                "Extract only relevant code sections",
                "Use summarization for long documents",
                "Implement context window management",
            ],
        }

    async def get_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """
        Generate optimization recommendations based on usage patterns.

        Issue #665: Refactored to use extracted helper methods.
        """
        stats, cache_opportunities = await asyncio.gather(
            self.get_usage_stats(days=7),
            self.identify_cache_opportunities(min_occurrences=2),
        )

        recommendations = []
        model_usage = stats.get("by_model", {})

        # Build recommendations using helpers - append if not None
        caching_rec = self._build_caching_recommendation(cache_opportunities)
        if caching_rec:
            recommendations.append(caching_rec)

        model_rec = self._build_model_downgrade_recommendation(stats, model_usage)
        if model_rec:
            recommendations.append(model_rec)

        batch_rec = self._build_batch_processing_recommendation(stats)
        if batch_rec:
            recommendations.append(batch_rec)

        recommendations.append(self._build_context_reduction_recommendation(stats))

        return recommendations

    async def _fetch_usage_records_batch(self, redis, days: int = 7) -> List[List]:
        """
        Fetch usage records from Redis for the specified number of days.

        Issue #620: Extracted from get_model_comparison to reduce function length.

        Args:
            redis: Redis client instance
            days: Number of days to fetch (default: 7)

        Returns:
            List of record lists from Redis pipeline
        """
        dates = [
            (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(days)
        ]
        usage_keys = [f"{self._usage_key}:{date}" for date in dates]

        async with redis.pipeline() as pipe:
            for key in usage_keys:
                await pipe.lrange(key, 0, -1)
            return await pipe.execute()

    def _aggregate_model_usage_data(
        self, all_records_lists: List[List]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Aggregate usage records into per-model statistics.

        Issue #620: Extracted from get_model_comparison to reduce function length.

        Args:
            all_records_lists: List of record lists from Redis

        Returns:
            Dict mapping model names to aggregated statistics
        """
        models: Dict[str, Dict[str, Any]] = {}

        for records in all_records_lists:
            for record_str in records:
                try:
                    record = json.loads(record_str)
                    model = record.get("model", "unknown")

                    if model not in models:
                        models[model] = {
                            "model": model,
                            "request_count": 0,
                            "total_input_tokens": 0,
                            "total_output_tokens": 0,
                            "total_cost": 0.0,
                            "total_response_time": 0.0,
                            "success_count": 0,
                        }

                    models[model]["request_count"] += 1
                    models[model]["total_input_tokens"] += record.get("input_tokens", 0)
                    models[model]["total_output_tokens"] += record.get(
                        "output_tokens", 0
                    )
                    models[model]["total_cost"] += record.get("cost", 0)
                    models[model]["total_response_time"] += record.get(
                        "response_time", 0
                    )

                    if record.get("success", True):
                        models[model]["success_count"] += 1

                except json.JSONDecodeError:
                    continue

        return models

    def _build_model_comparison_result(
        self, models: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Build comparison result list with calculated averages.

        Issue #620: Extracted from get_model_comparison to reduce function length.

        Args:
            models: Aggregated model statistics

        Returns:
            List of model comparison dicts sorted by total cost
        """
        result = []
        for model_data in models.values():
            count = model_data["request_count"]
            if count > 0:
                result.append(
                    {
                        "model": model_data["model"],
                        "request_count": count,
                        "total_tokens": (
                            model_data["total_input_tokens"]
                            + model_data["total_output_tokens"]
                        ),
                        "total_cost": round(model_data["total_cost"], 4),
                        "avg_cost_per_request": round(
                            model_data["total_cost"] / count, 6
                        ),
                        "avg_response_time": round(
                            model_data["total_response_time"] / count, 2
                        ),
                        "success_rate": round(
                            model_data["success_count"] / count * 100, 1
                        ),
                    }
                )

        result.sort(key=lambda x: x["total_cost"], reverse=True)
        return result

    async def get_model_comparison(self) -> List[Dict[str, Any]]:
        """
        Compare costs and usage across different models.

        Issue #620: Refactored to use extracted helper methods.

        Returns:
            List of model comparison statistics sorted by total cost
        """
        redis = await self._get_redis()

        # Fetch records from last 7 days
        all_records_lists = await self._fetch_usage_records_batch(redis, days=7)

        # Aggregate into per-model statistics
        models = self._aggregate_model_usage_data(all_records_lists)

        # Build and return sorted comparison result
        return self._build_model_comparison_result(models)

    async def get_category_distribution(self) -> Dict[str, Any]:
        """Get distribution of prompt categories"""
        redis = await self._get_redis()

        categories = defaultdict(lambda: {"count": 0, "cost": 0.0})

        # Aggregate from last 7 days - batch fetch all lists using pipeline
        dates = [
            (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)
        ]
        usage_keys = [f"{self._usage_key}:{date}" for date in dates]

        async with redis.pipeline() as pipe:
            for key in usage_keys:
                await pipe.lrange(key, 0, -1)
            all_records_lists = await pipe.execute()

        for records in all_records_lists:
            for record_str in records:
                try:
                    record = json.loads(record_str)
                    category = record.get("category", "unknown")
                    categories[category]["count"] += 1
                    categories[category]["cost"] += record.get("cost", 0)
                except json.JSONDecodeError:
                    continue

        # Format result
        total_count = sum(c["count"] for c in categories.values())
        total_cost = sum(c["cost"] for c in categories.values())

        result = []
        for cat, data in categories.items():
            result.append(
                {
                    "category": cat,
                    "count": data["count"],
                    "percentage": (
                        round(data["count"] / total_count * 100, 1)
                        if total_count > 0
                        else 0
                    ),
                    "cost": round(data["cost"], 4),
                    "cost_percentage": (
                        round(data["cost"] / total_cost * 100, 1)
                        if total_cost > 0
                        else 0
                    ),
                }
            )

        result.sort(key=lambda x: x["count"], reverse=True)

        return {
            "categories": result,
            "total_count": total_count,
            "total_cost": round(total_cost, 4),
        }


# =============================================================================
# Singleton Instance
# =============================================================================

import threading

_analyzer: Optional[LLMPatternAnalyzer] = None
_analyzer_lock = threading.Lock()


def get_pattern_analyzer() -> LLMPatternAnalyzer:
    """Get or create pattern analyzer singleton (thread-safe)"""
    global _analyzer
    if _analyzer is None:
        with _analyzer_lock:
            # Double-check after acquiring lock
            if _analyzer is None:
                _analyzer = LLMPatternAnalyzer()
    return _analyzer


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/health")
async def get_health():
    """Get LLM pattern analyzer health status"""
    return {
        "status": "healthy",
        "service": "llm_pattern_analyzer",
        "features": [
            "prompt_analysis",
            "usage_tracking",
            "cache_detection",
            "cost_optimization",
            "model_comparison",
        ],
        "supported_categories": [c.value for c in PromptCategory],
        "optimization_types": [o.value for o in OptimizationType],
    }


@router.post("/analyze")
async def analyze_prompt(request: PromptAnalysisRequest):
    """
    Analyze a prompt for optimization opportunities.

    Returns category, token estimate, and recommendations.
    """
    analyzer = get_pattern_analyzer()
    return await analyzer.analyze_prompt(request.prompt, request.model)


@router.post("/record")
async def record_usage(request: UsageRecordRequest):
    """
    Record an LLM usage event.

    Tracks the request for pattern analysis and cost tracking.
    """
    analyzer = get_pattern_analyzer()
    return await analyzer.record_usage(request)


@router.get("/stats")
async def get_usage_stats(days: int = Query(default=7, ge=1, le=30)):
    """
    Get usage statistics for the specified period.

    Returns aggregate stats, daily breakdown, and model distribution.
    """
    analyzer = get_pattern_analyzer()
    return await analyzer.get_usage_stats(days)


@router.get("/cache-opportunities")
async def get_cache_opportunities(
    min_occurrences: int = Query(default=3, ge=2, le=100)
):
    """
    Identify prompts that could benefit from caching.

    Returns prompts that have been repeated multiple times.
    """
    analyzer = get_pattern_analyzer()
    opportunities = await analyzer.identify_cache_opportunities(min_occurrences)

    return {
        "opportunities": opportunities,
        "count": len(opportunities),
        "min_occurrences": min_occurrences,
    }


@router.get("/recommendations")
async def get_recommendations():
    """
    Get optimization recommendations based on usage patterns.

    Returns prioritized list of optimization opportunities.
    """
    analyzer = get_pattern_analyzer()
    return {"recommendations": await analyzer.get_optimization_recommendations()}


@router.get("/model-comparison")
async def get_model_comparison():
    """
    Compare costs and usage across different models.

    Returns per-model statistics for the last 7 days.
    """
    analyzer = get_pattern_analyzer()
    return {"models": await analyzer.get_model_comparison(), "period_days": 7}


@router.get("/category-distribution")
async def get_category_distribution():
    """
    Get distribution of prompt categories.

    Shows what types of prompts are being used most.
    """
    analyzer = get_pattern_analyzer()
    return await analyzer.get_category_distribution()


@router.get("/cost-breakdown")
async def get_cost_breakdown(days: int = Query(default=7, ge=1, le=30)):
    """
    Get detailed cost breakdown.

    Returns costs by model, category, and time period.
    """
    analyzer = get_pattern_analyzer()

    stats = await analyzer.get_usage_stats(days)
    models = await analyzer.get_model_comparison()
    categories = await analyzer.get_category_distribution()

    return {
        "period_days": days,
        "total_cost": stats["total_cost"],
        "total_requests": stats["total_requests"],
        "avg_cost_per_request": stats.get("avg_cost_per_request", 0),
        "by_model": models,
        "by_category": categories["categories"],
        "daily_trend": stats["by_date"],
    }
