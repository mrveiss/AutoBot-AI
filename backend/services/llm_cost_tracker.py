# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM Cost Tracking Service - Track and analyze LLM API usage costs.

This module provides comprehensive cost tracking for all LLM API calls:
- Token counting (input/output)
- Cost calculation per provider/model
- Session/user attribution
- Time series storage in Redis
- Budget alerting

Related Issues: #59 (Advanced Analytics & Business Intelligence)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from src.utils.redis_client import RedisDatabase, get_redis_client

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    """Supported LLM providers"""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"
    GOOGLE = "google"
    OPENROUTER = "openrouter"
    LOCAL = "local"


# Model pricing per 1M tokens (USD) - Updated 2025
# Format: {"input": price_per_1M_input_tokens, "output": price_per_1M_output_tokens}
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # Anthropic Claude models
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    "claude-3-sonnet-20240229": {"input": 3.00, "output": 15.00},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    # OpenAI models
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "o1": {"input": 15.00, "output": 60.00},
    "o1-mini": {"input": 3.00, "output": 12.00},
    # Google models
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    # Local/Ollama models (free)
    "llama3": {"input": 0.0, "output": 0.0},
    "llama3.1": {"input": 0.0, "output": 0.0},
    "llama3.2": {"input": 0.0, "output": 0.0},
    "mistral": {"input": 0.0, "output": 0.0},
    "mixtral": {"input": 0.0, "output": 0.0},
    "codellama": {"input": 0.0, "output": 0.0},
    "qwen2.5": {"input": 0.0, "output": 0.0},
    "deepseek-coder": {"input": 0.0, "output": 0.0},
}


@dataclass
class LLMUsageRecord:
    """Record of a single LLM API call"""

    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    endpoint: Optional[str] = None
    latency_ms: Optional[float] = None
    success: bool = True
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "endpoint": self.endpoint,
            "latency_ms": self.latency_ms,
            "success": self.success,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMUsageRecord":
        """Create from dictionary"""
        return cls(
            provider=data["provider"],
            model=data["model"],
            input_tokens=data["input_tokens"],
            output_tokens=data["output_tokens"],
            cost_usd=data["cost_usd"],
            timestamp=data["timestamp"],
            session_id=data.get("session_id"),
            user_id=data.get("user_id"),
            endpoint=data.get("endpoint"),
            latency_ms=data.get("latency_ms"),
            success=data.get("success", True),
            error_message=data.get("error_message"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class BudgetAlert:
    """Budget alert configuration"""

    name: str
    threshold_usd: float
    period: str  # "daily", "weekly", "monthly"
    notify_at_percent: List[int] = field(default_factory=lambda: [50, 75, 90, 100])
    enabled: bool = True


class LLMCostTracker:
    """
    Tracks LLM API usage costs across all providers.

    Features:
    - Real-time cost calculation
    - Per-session and per-user attribution
    - Redis-based time series storage
    - Budget alerting
    - Cost trend analysis
    """

    REDIS_KEY_PREFIX = "llm_cost:"
    USAGE_LIST_KEY = f"{REDIS_KEY_PREFIX}usage"
    DAILY_TOTALS_KEY = f"{REDIS_KEY_PREFIX}daily"
    MODEL_TOTALS_KEY = f"{REDIS_KEY_PREFIX}by_model"
    SESSION_TOTALS_KEY = f"{REDIS_KEY_PREFIX}by_session"
    BUDGET_ALERTS_KEY = f"{REDIS_KEY_PREFIX}budget_alerts"

    def __init__(self):
        self._redis_client = None
        self._budget_alerts: List[BudgetAlert] = []
        self._current_period_costs: Dict[str, float] = {}

    async def get_redis(self):
        """Get async Redis client"""
        if self._redis_client is None:
            self._redis_client = await get_redis_client(
                async_client=True, database=RedisDatabase.ANALYTICS
            )
        return self._redis_client

    def calculate_cost(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> float:
        """
        Calculate cost for a given model and token counts.

        Args:
            model: Model name (e.g., "claude-3-5-sonnet-20241022")
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Cost in USD
        """
        # Normalize model name (handle variations)
        model_lower = model.lower()

        # Find matching pricing
        pricing = None
        for model_key, price_data in MODEL_PRICING.items():
            if model_key.lower() in model_lower or model_lower in model_key.lower():
                pricing = price_data
                break

        if pricing is None:
            # Default to zero for unknown models (assume local/free)
            logger.warning(f"Unknown model pricing for: {model}, assuming free")
            return 0.0

        # Calculate cost (pricing is per 1M tokens)
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        return round(input_cost + output_cost, 6)

    async def track_usage(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        endpoint: Optional[str] = None,
        latency_ms: Optional[float] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LLMUsageRecord:
        """
        Track an LLM API usage event.

        Args:
            provider: LLM provider (anthropic, openai, etc.)
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            session_id: Optional session identifier
            user_id: Optional user identifier
            endpoint: Optional API endpoint called
            latency_ms: Optional response latency in milliseconds
            success: Whether the call succeeded
            error_message: Error message if failed
            metadata: Additional metadata

        Returns:
            LLMUsageRecord with calculated cost
        """
        cost = self.calculate_cost(model, input_tokens, output_tokens)
        timestamp = datetime.utcnow().isoformat()

        record = LLMUsageRecord(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            timestamp=timestamp,
            session_id=session_id,
            user_id=user_id,
            endpoint=endpoint,
            latency_ms=latency_ms,
            success=success,
            error_message=error_message,
            metadata=metadata or {},
        )

        # Store in Redis
        await self._store_usage_record(record)

        # Check budget alerts
        await self._check_budget_alerts(cost)

        logger.debug(
            f"Tracked LLM usage: {provider}/{model} - "
            f"{input_tokens}in/{output_tokens}out = ${cost:.6f}"
        )

        return record

    async def _store_usage_record(self, record: LLMUsageRecord) -> None:
        """Store usage record in Redis"""
        try:
            redis = await self.get_redis()

            # Store in usage list (keep last 100k records)
            await redis.lpush(self.USAGE_LIST_KEY, json.dumps(record.to_dict()))
            await redis.ltrim(self.USAGE_LIST_KEY, 0, 99999)

            # Update daily totals
            today = datetime.utcnow().strftime("%Y-%m-%d")
            daily_key = f"{self.DAILY_TOTALS_KEY}:{today}"
            await redis.incrbyfloat(daily_key, record.cost_usd)
            await redis.expire(daily_key, 86400 * 90)  # Keep 90 days

            # Update model totals
            model_key = f"{self.MODEL_TOTALS_KEY}:{record.model}"
            await redis.hincrby(model_key, "input_tokens", record.input_tokens)
            await redis.hincrby(model_key, "output_tokens", record.output_tokens)
            await redis.hincrbyfloat(model_key, "cost_usd", record.cost_usd)
            await redis.hincrby(model_key, "call_count", 1)

            # Update session totals if session provided
            if record.session_id:
                session_key = f"{self.SESSION_TOTALS_KEY}:{record.session_id}"
                await redis.hincrbyfloat(session_key, "cost_usd", record.cost_usd)
                await redis.hincrby(session_key, "input_tokens", record.input_tokens)
                await redis.hincrby(session_key, "output_tokens", record.output_tokens)
                await redis.expire(session_key, 86400 * 30)  # Keep 30 days

        except Exception as e:
            logger.error(f"Failed to store LLM usage record: {e}")

    async def _check_budget_alerts(self, cost: float) -> None:
        """Check if any budget alerts should be triggered"""
        # Implementation for budget alerts - can be extended
        pass

    async def get_cost_summary(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get cost summary for a time period.

        Args:
            start_date: Start of period (default: 30 days ago)
            end_date: End of period (default: now)

        Returns:
            Summary dict with totals and breakdowns
        """
        if end_date is None:
            end_date = datetime.utcnow()
        if start_date is None:
            start_date = end_date - timedelta(days=30)

        try:
            redis = await self.get_redis()

            # Get daily totals for the period
            daily_costs = {}
            current = start_date
            while current <= end_date:
                date_str = current.strftime("%Y-%m-%d")
                daily_key = f"{self.DAILY_TOTALS_KEY}:{date_str}"
                cost = await redis.get(daily_key)
                if cost:
                    daily_costs[date_str] = float(cost)
                current += timedelta(days=1)

            total_cost = sum(daily_costs.values())

            # Get model breakdown
            model_costs = {}
            model_keys = await redis.keys(f"{self.MODEL_TOTALS_KEY}:*")
            for key in model_keys:
                key_str = key if isinstance(key, str) else key.decode("utf-8")
                model_name = key_str.split(":")[-1]
                model_data = await redis.hgetall(key)
                if model_data:
                    model_costs[model_name] = {
                        "cost_usd": float(model_data.get(b"cost_usd", 0) or model_data.get("cost_usd", 0)),
                        "input_tokens": int(model_data.get(b"input_tokens", 0) or model_data.get("input_tokens", 0)),
                        "output_tokens": int(model_data.get(b"output_tokens", 0) or model_data.get("output_tokens", 0)),
                        "call_count": int(model_data.get(b"call_count", 0) or model_data.get("call_count", 0)),
                    }

            return {
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                },
                "total_cost_usd": round(total_cost, 4),
                "daily_costs": daily_costs,
                "by_model": model_costs,
                "avg_daily_cost": round(total_cost / max(len(daily_costs), 1), 4),
            }

        except Exception as e:
            logger.error(f"Failed to get cost summary: {e}")
            return {
                "error": str(e),
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                },
                "total_cost_usd": 0,
            }

    async def get_cost_by_session(self, session_id: str) -> Dict[str, Any]:
        """Get cost breakdown for a specific session"""
        try:
            redis = await self.get_redis()
            session_key = f"{self.SESSION_TOTALS_KEY}:{session_id}"
            data = await redis.hgetall(session_key)

            if not data:
                return {"session_id": session_id, "found": False}

            return {
                "session_id": session_id,
                "found": True,
                "cost_usd": float(data.get(b"cost_usd", 0) or data.get("cost_usd", 0)),
                "input_tokens": int(data.get(b"input_tokens", 0) or data.get("input_tokens", 0)),
                "output_tokens": int(data.get(b"output_tokens", 0) or data.get("output_tokens", 0)),
            }

        except Exception as e:
            logger.error(f"Failed to get session cost: {e}")
            return {"session_id": session_id, "error": str(e)}

    async def get_cost_trends(self, days: int = 30) -> Dict[str, Any]:
        """
        Get cost trends over time.

        Args:
            days: Number of days to analyze

        Returns:
            Trend data including daily costs and growth rates
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        summary = await self.get_cost_summary(start_date, end_date)

        daily_costs = summary.get("daily_costs", {})
        sorted_dates = sorted(daily_costs.keys())

        # Calculate trends
        if len(sorted_dates) >= 2:
            first_half = sorted_dates[: len(sorted_dates) // 2]
            second_half = sorted_dates[len(sorted_dates) // 2 :]

            first_half_avg = sum(daily_costs[d] for d in first_half) / len(first_half)
            second_half_avg = sum(daily_costs[d] for d in second_half) / len(second_half)

            if first_half_avg > 0:
                growth_rate = ((second_half_avg - first_half_avg) / first_half_avg) * 100
            else:
                growth_rate = 0
        else:
            growth_rate = 0

        return {
            "period_days": days,
            "total_cost_usd": summary.get("total_cost_usd", 0),
            "daily_costs": daily_costs,
            "trend": "increasing" if growth_rate > 5 else "decreasing" if growth_rate < -5 else "stable",
            "growth_rate_percent": round(growth_rate, 2),
            "avg_daily_cost": summary.get("avg_daily_cost", 0),
        }

    async def get_recent_usage(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent usage records"""
        try:
            redis = await self.get_redis()
            records = await redis.lrange(self.USAGE_LIST_KEY, 0, limit - 1)
            return [json.loads(r) for r in records]
        except Exception as e:
            logger.error(f"Failed to get recent usage: {e}")
            return []


# Singleton instance
_cost_tracker: Optional[LLMCostTracker] = None


def get_cost_tracker() -> LLMCostTracker:
    """Get the singleton cost tracker instance"""
    global _cost_tracker
    if _cost_tracker is None:
        _cost_tracker = LLMCostTracker()
    return _cost_tracker
