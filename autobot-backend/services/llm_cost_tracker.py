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

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import RedisDatabase, get_redis_client
from autobot_shared.redis_mixin import AsyncRedisClientMixin
from autobot_shared.time_utils import now_utc, utc_timestamp
from constants.model_constants import (
    ANTHROPIC_CLAUDE_HAIKU4_5,
    ANTHROPIC_CLAUDE_OPUS4,
    ANTHROPIC_CLAUDE_SONNET4,
    DEEPSEEK_R1_API,
    DEEPSEEK_V3,
    GOOGLE_GEMINI15_PRO,
    GOOGLE_GEMINI20_FLASH,
    GOOGLE_GEMINI25_PRO,
    MODEL_PRICING_PER_1M_TOKENS,
    OPENAI_GPT4_TURBO,
    OPENAI_GPT4O,
    OPENAI_GPT35_TURBO,
    OPENAI_GPT41,
    OPENAI_O1,
    OPENAI_O1_MINI,
    OPENAI_O3,
    OPENAI_O3_MINI,
    OPENAI_O4_MINI,
)
from constants.ttl_constants import TTL_30_DAYS, TTL_90_DAYS

logger = get_logger(__name__)

# Pricing was last verified on this date. A WARNING is emitted at import time
# if this is older than PRICING_STALENESS_DAYS days. (#1961)
# GH#6480: This hardcoded version is a fallback. The actual refresh timestamp
# is populated by the pricing_refresh_daily Celery Beat task into Redis.
PRICING_VERSION: str = "2026-03-22"
PRICING_STALENESS_DAYS: int = 90


class LLMProvider(str, Enum):
    """Supported LLM providers"""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"
    GOOGLE = "google"
    OPENROUTER = "openrouter"
    LOCAL = "local"


# Model pricing per 1M tokens (USD) - single source of truth in
# constants/model_constants.py (#3528). Update PRICING_VERSION above when
# prices change.
MODEL_PRICING: Dict[str, Dict[str, float]] = MODEL_PRICING_PER_1M_TOKENS


def _get_last_refresh_from_redis() -> str | None:
    """
    Fetch the latest refresh timestamp from Redis refresh_status (GH#6480).

    The pricing_refresh_daily task stores {provider: {last_refresh_at, ...}} in Redis.
    This function returns the most recent last_refresh_at across all providers.
    Returns None if Redis is unavailable or no refresh status exists.
    """
    try:
        redis = get_redis_client(database="analytics")
        if redis is None:
            return None

        raw = redis.get("model_pricing:refresh_status")
        if raw is None:
            return None

        status = json.loads(raw)
        refresh_dates = [
            info.get("last_refresh_at")
            for info in status.values()
            if isinstance(info, dict) and info.get("last_refresh_at")
        ]

        if refresh_dates:
            # Extract just the date part (YYYY-MM-DD) from the ISO timestamp
            latest = max(refresh_dates)
            return latest.split("T")[0] if latest else None
        return None
    except Exception as exc:
        logger.debug("Failed to fetch pricing refresh status from Redis: %s", exc)
        return None


def _check_pricing_staleness() -> None:
    """
    Emit a WARNING if pricing is older than PRICING_STALENESS_DAYS.

    Checks Redis first for the actual last refresh timestamp from the
    pricing_refresh_daily task (GH#6480). Falls back to hardcoded PRICING_VERSION
    if Redis is unavailable. Called once at module import time. Issue #1961.
    """
    last_refresh_date = _get_last_refresh_from_redis()

    # Use Redis refresh date if available; otherwise fall back to hardcoded version
    version_to_check = last_refresh_date if last_refresh_date else PRICING_VERSION

    try:
        version_date = date.fromisoformat(version_to_check)
    except ValueError:
        logger.warning(
            "Pricing version %r is not a valid ISO date; cannot check staleness.",
            version_to_check,
        )
        return

    age_days = (date.today() - version_date).days
    if age_days > PRICING_STALENESS_DAYS:
        logger.warning(
            "LLM pricing table is %d days old (last verified %s, threshold %d days). "
            "Review the pricing_refresh_daily Celery Beat task or update PRICING_VERSION. "
            "Issue #1961.",
            age_days,
            version_to_check,
            PRICING_STALENESS_DAYS,
        )


_check_pricing_staleness()


@dataclass
class LLMUsageRecord:
    """Record of a single LLM API call"""

    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: str
    session_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    endpoint: str | None = None
    latency_ms: float | None = None
    success: bool = True
    error_message: str | None = None
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
            "agent_id": self.agent_id,
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
            agent_id=data.get("agent_id"),
            endpoint=data.get("endpoint"),
            latency_ms=data.get("latency_ms"),
            success=data.get("success", True),
            error_message=data.get("error_message"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class TrackUsageRequest:
    """
    Request parameters for tracking LLM usage.

    Issue #375: Reduces long parameter list in track_usage().
    Groups all tracking parameters into a single request object.
    """

    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    session_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    endpoint: str | None = None
    latency_ms: float | None = None
    success: bool = True
    error_message: str | None = None
    metadata: Dict[str, Any] | None = None


@dataclass
class BudgetAlert:
    """Budget alert configuration"""

    name: str
    threshold_usd: float
    period: str  # "daily", "weekly", "monthly"
    notify_at_percent: List[int] = field(default_factory=lambda: [50, 75, 90, 100])
    enabled: bool = True


class LLMCostTracker(AsyncRedisClientMixin):
    """
    Tracks LLM API usage costs across all providers.

    Features:
    - Real-time cost calculation
    - Per-session and per-user attribution
    - Redis-based time series storage
    - Budget alerting
    - Cost trend analysis
    """

    _redis_database = RedisDatabase.ANALYTICS

    REDIS_KEY_PREFIX = "llm_cost:"
    USAGE_LIST_KEY = f"{REDIS_KEY_PREFIX}usage"
    DAILY_TOTALS_KEY = f"{REDIS_KEY_PREFIX}daily"
    MODEL_TOTALS_KEY = f"{REDIS_KEY_PREFIX}by_model"
    SESSION_TOTALS_KEY = f"{REDIS_KEY_PREFIX}by_session"
    AGENT_TOTALS_KEY = f"{REDIS_KEY_PREFIX}by_agent"
    USER_TOTALS_KEY = f"{REDIS_KEY_PREFIX}by_user"
    AGENT_BUDGET_KEY = f"{REDIS_KEY_PREFIX}agent_budget"
    BUDGET_ALERTS_KEY = f"{REDIS_KEY_PREFIX}budget_alerts"

    def __init__(self) -> None:
        """Initialize cost tracker with empty alerts."""
        self._budget_alerts: List[BudgetAlert] = []
        self._current_period_costs: Dict[str, float] = {}

    async def get_redis(self):
        """Get async Redis client"""
        return await self._get_redis()

    # Pattern-based pricing fallbacks for unknown models (#1961).
    # Ordered from most specific to least specific.
    _FALLBACK_PATTERNS: List[tuple] = [
        ("claude-opus", ANTHROPIC_CLAUDE_OPUS4),
        ("claude-sonnet", ANTHROPIC_CLAUDE_SONNET4),
        ("claude-haiku", ANTHROPIC_CLAUDE_HAIKU4_5),
        ("claude", ANTHROPIC_CLAUDE_SONNET4),
        ("gpt-4o", OPENAI_GPT4O),
        ("gpt-4.1", OPENAI_GPT41),
        ("gpt-4", OPENAI_GPT4_TURBO),
        ("gpt-3.5", OPENAI_GPT35_TURBO),
        ("o1-mini", OPENAI_O1_MINI),
        ("o3-mini", OPENAI_O3_MINI),
        ("o4-mini", OPENAI_O4_MINI),
        ("o1", OPENAI_O1),
        ("o3", OPENAI_O3),
        ("gemini-2.5", GOOGLE_GEMINI25_PRO),
        ("gemini-2.0", GOOGLE_GEMINI20_FLASH),
        ("gemini-1.5", GOOGLE_GEMINI15_PRO),
        ("gemini", GOOGLE_GEMINI20_FLASH),
        ("deepseek-v3", DEEPSEEK_V3),
        ("deepseek-r1", DEEPSEEK_R1_API),
    ]

    def _estimate_pricing_by_pattern(self, model_lower: str) -> Dict[str, float] | None:
        """
        Return pricing estimate for an unknown model using name-pattern heuristics.

        Iterates _FALLBACK_PATTERNS in order and returns the pricing for the
        first pattern that matches as a substring. Returns None if no pattern
        matches (caller should treat the model as local/free). Issue #1961.
        """
        for pattern, reference_model in self._FALLBACK_PATTERNS:
            if pattern in model_lower:
                pricing = MODEL_PRICING.get(reference_model)
                if pricing:
                    logger.warning(
                        "Unknown model %r matched fallback pattern %r; "
                        "using %r pricing as estimate. Verify in MODEL_PRICING. (#1961)",
                        model_lower,
                        pattern,
                        reference_model,
                    )
                    return pricing
        return None

    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate cost for a given model and token counts.

        For models not in MODEL_PRICING, a pattern-based heuristic is applied
        before falling back to $0.00 for unrecognised (presumed local) models.
        Issue #1961 added the heuristic fallback.

        Args:
            model: Model name (e.g., "claude-3-5-sonnet-20241022")
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Cost in USD
        """
        # Normalize model name (handle variations)
        model_lower = model.lower()

        # 1. Exact match — fastest and most precise path
        pricing = MODEL_PRICING.get(model_lower)

        # 2. Prefix match (longest key first) — handles versioned suffixes such as
        #    "gpt-4o-2024-11-20" matching "gpt-4o", while preventing "o3" from
        #    incorrectly matching "o3-mini". Fixes bidirectional substring bug (#2030).
        if pricing is None:
            for model_key in sorted(MODEL_PRICING, key=len, reverse=True):
                if model_lower.startswith(model_key.lower()):
                    pricing = MODEL_PRICING[model_key]
                    break

        if pricing is None:
            # Pattern-based heuristic for unknown cloud models (#1961)
            pricing = self._estimate_pricing_by_pattern(model_lower)

        if pricing is None:
            logger.warning(
                "Unknown model %r has no pricing entry and matched no fallback pattern; "
                "cost recorded as $0.00. Add to MODEL_PRICING in llm_cost_tracker.py "
                "if this is a paid API model. (#1961)",
                model,
            )
            return 0.0

        # Calculate cost (pricing is per 1M tokens)
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        return round(input_cost + output_cost, 6)

    def _extract_params_from_request(self, request: "TrackUsageRequest") -> tuple:
        """Helper for _extract_usage_params. Ref: #1088."""
        return (
            request.provider,
            request.model,
            request.input_tokens,
            request.output_tokens,
            request.session_id,
            request.user_id,
            request.agent_id,
            request.endpoint,
            request.latency_ms,
            request.success,
            request.error_message,
            request.metadata,
        )

    def _extract_params_from_kwargs(
        self,
        provider: str | None,
        model: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
        session_id: str | None,
        user_id: str | None,
        agent_id: str | None,
        endpoint: str | None,
        latency_ms: float | None,
        success: bool,
        error_message: str | None,
        metadata: Dict[str, Any] | None,
    ) -> tuple:
        """Helper for _extract_usage_params. Ref: #1088."""
        if provider is None or model is None or input_tokens is None or output_tokens is None:
            raise ValueError(
                "Either 'request' object or 'provider', 'model', " "'input_tokens', 'output_tokens' are required"
            )
        return (
            provider,
            model,
            input_tokens,
            output_tokens,
            session_id,
            user_id,
            agent_id,
            endpoint,
            latency_ms,
            success,
            error_message,
            metadata,
        )

    def _extract_usage_params(
        self,
        request: "TrackUsageRequest" | None,
        provider: str | None,
        model: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
        session_id: str | None,
        user_id: str | None,
        agent_id: str | None,
        endpoint: str | None,
        latency_ms: float | None,
        success: bool,
        error_message: str | None,
        metadata: Dict[str, Any] | None,
    ) -> tuple:
        """
        Extract usage parameters from request object or individual args.

        Issue #665: Extracted from track_usage to reduce function length.
        Issue #1088: Delegated branches to _extract_params_from_request /
            _extract_params_from_kwargs.

        Args:
            request: Optional TrackUsageRequest object
            Other args: Individual parameters (used if request is None)

        Returns:
            Tuple of all extracted parameters

        Raises:
            ValueError: If required parameters are missing
        """
        if request is not None:
            return self._extract_params_from_request(request)
        return self._extract_params_from_kwargs(
            provider,
            model,
            input_tokens,
            output_tokens,
            session_id,
            user_id,
            agent_id,
            endpoint,
            latency_ms,
            success,
            error_message,
            metadata,
        )

    def _create_usage_record(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        session_id: str | None,
        user_id: str | None,
        agent_id: str | None,
        endpoint: str | None,
        latency_ms: float | None,
        success: bool,
        error_message: str | None,
        metadata: Dict[str, Any] | None,
    ) -> "LLMUsageRecord":
        """
        Create LLMUsageRecord with all parameters.

        Issue #665: Extracted from track_usage to reduce function length.

        Args:
            All usage record parameters

        Returns:
            LLMUsageRecord instance
        """
        return LLMUsageRecord(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            timestamp=utc_timestamp(),
            session_id=session_id,
            user_id=user_id,
            agent_id=agent_id,
            endpoint=endpoint,
            latency_ms=latency_ms,
            success=success,
            error_message=error_message,
            metadata=metadata or {},
        )

    def _resolve_usage_params(
        self,
        request: TrackUsageRequest | None,
        provider: str | None,
        model: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
        session_id: str | None,
        user_id: str | None,
        agent_id: str | None,
        endpoint: str | None,
        latency_ms: float | None,
        success: bool,
        error_message: str | None,
        metadata: Dict[str, Any] | None,
    ) -> tuple:
        """Helper for track_usage. Ref: #1088."""
        return self._extract_usage_params(
            request,
            provider,
            model,
            input_tokens,
            output_tokens,
            session_id,
            user_id,
            agent_id,
            endpoint,
            latency_ms,
            success,
            error_message,
            metadata,
        )

    async def _redis_pricing_lookup(self, model_lower: str) -> Dict[str, float] | None:
        """Check Redis cache for model pricing before falling back to hardcoded table (GH#6480).

        Redis keys are written by services.pricing_refresh.refresh_pricing_daily.
        Returns a legacy {input: float, output: float} dict or None on miss/error.
        """
        try:
            from llm_shared.pricing.redis_store import PricingRedisStore

            store = PricingRedisStore()
            # Try known providers in order; first hit wins.
            for provider in ("anthropic", "openai", "google", "deepseek"):
                cached = await store.get(provider, model_lower)
                if cached is not None:
                    return cached.as_legacy_dict()
        except Exception as exc:
            logger.debug("_redis_pricing_lookup failed for %r: %s", model_lower, exc)
        return None

    async def _build_and_persist_record(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        session_id: str | None,
        user_id: str | None,
        agent_id: str | None,
        endpoint: str | None,
        latency_ms: float | None,
        success: bool,
        error_message: str | None,
        metadata: Dict[str, Any] | None,
    ) -> LLMUsageRecord:
        """Helper for track_usage. Ref: #1088."""
        # GH#6480: check Redis-cached pricing before falling back to hardcoded table.
        model_lower = model.lower()
        redis_pricing = await self._redis_pricing_lookup(model_lower)
        if redis_pricing is not None:
            input_cost = (input_tokens / 1_000_000) * redis_pricing["input"]
            output_cost = (output_tokens / 1_000_000) * redis_pricing["output"]
            cost = round(input_cost + output_cost, 6)
        else:
            cost = self.calculate_cost(model, input_tokens, output_tokens)
        record = self._create_usage_record(
            provider,
            model,
            input_tokens,
            output_tokens,
            cost,
            session_id,
            user_id,
            agent_id,
            endpoint,
            latency_ms,
            success,
            error_message,
            metadata,
        )
        # Issue #379: Parallelize independent tracking operations
        await asyncio.gather(
            self._store_usage_record(record),
            self._check_budget_alerts(cost),
        )
        # Budget policy evaluation — fire-and-forget background task (GH#6470)
        if record.agent_id:
            try:
                from services.budget_policy import trigger_budget_evaluation

                trigger_budget_evaluation(agent_id=record.agent_id)
            except Exception:
                pass  # never let policy evaluation block cost tracking
        logger.debug(
            "Tracked LLM usage: %s/%s - %din/%dout = $%.6f",
            provider,
            model,
            input_tokens,
            output_tokens,
            cost,
        )
        return record

    async def track_usage(
        self,
        request: TrackUsageRequest | None = None,
        *,  # Force keyword-only args for backwards compatibility
        provider: str | None = None,
        model: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        agent_id: str | None = None,
        endpoint: str | None = None,
        latency_ms: float | None = None,
        success: bool = True,
        error_message: str | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> LLMUsageRecord:
        """Track an LLM API usage event. Ref: #1088.

        Supports request object or individual keyword params (legacy).
        Delegates to _resolve_usage_params then _build_and_persist_record.

        Returns:
            LLMUsageRecord with calculated cost
        """
        params = self._resolve_usage_params(
            request,
            provider,
            model,
            input_tokens,
            output_tokens,
            session_id,
            user_id,
            agent_id,
            endpoint,
            latency_ms,
            success,
            error_message,
            metadata,
        )
        return await self._build_and_persist_record(*params)

    async def _store_usage_record(self, record: LLMUsageRecord) -> None:
        """Store usage record in Redis.

        Issue #379: Uses Redis pipeline to batch all operations,
        eliminating 10+ sequential await round-trips.
        """
        try:
            redis = await self.get_redis()

            # Prepare keys
            today = now_utc().strftime("%Y-%m-%d")
            daily_key = f"{self.DAILY_TOTALS_KEY}:{today}"
            model_key = f"{self.MODEL_TOTALS_KEY}:{record.model}"

            # Issue #379: Batch all Redis operations using pipeline
            async with redis.pipeline() as pipe:
                # Store in usage list (keep last 100k records)
                await pipe.lpush(self.USAGE_LIST_KEY, json.dumps(record.to_dict()))
                await pipe.ltrim(self.USAGE_LIST_KEY, 0, 99999)

                # Update daily totals
                await pipe.incrbyfloat(daily_key, record.cost_usd)
                await pipe.expire(daily_key, TTL_90_DAYS)  # Keep 90 days

                # Update model totals
                await pipe.hincrby(model_key, "input_tokens", record.input_tokens)
                await pipe.hincrby(model_key, "output_tokens", record.output_tokens)
                await pipe.hincrbyfloat(model_key, "cost_usd", record.cost_usd)
                await pipe.hincrby(model_key, "call_count", 1)

                # Update session totals if session provided
                if record.session_id:
                    session_key = f"{self.SESSION_TOTALS_KEY}:{record.session_id}"
                    await pipe.hincrbyfloat(session_key, "cost_usd", record.cost_usd)
                    await pipe.hincrby(session_key, "input_tokens", record.input_tokens)
                    await pipe.hincrby(session_key, "output_tokens", record.output_tokens)
                    await pipe.expire(session_key, TTL_30_DAYS)  # Keep 30 days

                # Update per-agent totals if agent provided (#1401)
                if record.agent_id:
                    agent_key = f"{self.AGENT_TOTALS_KEY}:{record.agent_id}"
                    await pipe.hincrbyfloat(agent_key, "cost_usd", record.cost_usd)
                    await pipe.hincrby(agent_key, "input_tokens", record.input_tokens)
                    await pipe.hincrby(agent_key, "output_tokens", record.output_tokens)
                    await pipe.hincrby(agent_key, "call_count", 1)
                    daily_agent_key = f"{self.AGENT_TOTALS_KEY}:{record.agent_id}" f":daily:{today}"
                    await pipe.incrbyfloat(daily_agent_key, record.cost_usd)
                    await pipe.expire(daily_agent_key, TTL_90_DAYS)

                # Update per-user totals if user provided (#1807)
                if record.user_id:
                    user_key = f"{self.USER_TOTALS_KEY}:{record.user_id}"
                    await pipe.hincrbyfloat(user_key, "cost_usd", record.cost_usd)
                    await pipe.hincrby(user_key, "input_tokens", record.input_tokens)
                    await pipe.hincrby(user_key, "output_tokens", record.output_tokens)
                    await pipe.hincrby(user_key, "call_count", 1)
                    daily_user_key = f"{self.USER_TOTALS_KEY}:{record.user_id}:daily:{today}"
                    await pipe.incrbyfloat(daily_user_key, record.cost_usd)
                    await pipe.expire(daily_user_key, TTL_90_DAYS)

                # Execute all operations in single round-trip
                await pipe.execute()

        except Exception as e:
            logger.error("Failed to store LLM usage record: %s", e)

    async def _check_budget_alerts(self, cost: float) -> None:
        """Check if any budget alerts should be triggered"""
        # Implementation for budget alerts - can be extended

    async def _fetch_daily_costs(self, redis, start_date: datetime, end_date: datetime) -> Dict[str, float]:
        """
        Fetch daily costs from Redis using pipeline (Issue #665: extracted helper).

        Args:
            redis: Redis client
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Dict mapping date strings to cost values
        """
        date_strs = []
        daily_keys = []
        current = start_date
        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            date_strs.append(date_str)
            daily_keys.append(f"{self.DAILY_TOTALS_KEY}:{date_str}")
            current += timedelta(days=1)

        daily_costs = {}
        if daily_keys:
            pipe = redis.pipeline()
            for key in daily_keys:
                pipe.get(key)
            results = await pipe.execute()

            for date_str, cost in zip(date_strs, results):
                if cost:
                    daily_costs[date_str] = float(cost)

        return daily_costs

    async def _fetch_model_costs(self, redis) -> Dict[str, Dict[str, Any]]:
        """
        Fetch model cost breakdown from Redis (Issue #665: extracted helper).

        Args:
            redis: Redis client

        Returns:
            Dict mapping model names to cost/usage data
        """
        model_costs = {}
        model_keys = [key async for key in redis.scan_iter(f"{self.MODEL_TOTALS_KEY}:*")]

        if not model_keys:
            return model_costs

        pipe = redis.pipeline()
        for key in model_keys:
            pipe.hgetall(key)
        model_data_list = await pipe.execute()

        for key, model_data in zip(model_keys, model_data_list):
            if not model_data:
                continue

            key_str = key if isinstance(key, str) else key.decode("utf-8")
            model_name = key_str.split(":")[-1]

            model_costs[model_name] = {
                "cost_usd": float(model_data.get(b"cost_usd", 0) or model_data.get("cost_usd", 0)),
                "input_tokens": int(model_data.get(b"input_tokens", 0) or model_data.get("input_tokens", 0)),
                "output_tokens": int(model_data.get(b"output_tokens", 0) or model_data.get("output_tokens", 0)),
                "call_count": int(model_data.get(b"call_count", 0) or model_data.get("call_count", 0)),
            }

        return model_costs

    async def get_cost_summary(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> Dict[str, Any]:
        """
        Get cost summary for a time period.

        Issue #665: Refactored to use extracted helper methods.

        Args:
            start_date: Start of period (default: 30 days ago)
            end_date: End of period (default: now)

        Returns:
            Summary dict with totals and breakdowns
        """
        if end_date is None:
            end_date = now_utc()
        if start_date is None:
            start_date = end_date - timedelta(days=30)

        try:
            redis = await self.get_redis()

            # Fetch costs using helpers (Issue #665)
            daily_costs = await self._fetch_daily_costs(redis, start_date, end_date)
            model_costs = await self._fetch_model_costs(redis)

            total_cost = sum(daily_costs.values())

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
            logger.error("Failed to get cost summary: %s", e)
            return {
                "error": "Failed to retrieve cost summary",
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
            logger.error("Failed to get session cost: %s", e)
            return {
                "session_id": session_id,
                "error": "Failed to retrieve session cost",
            }

    async def get_cost_trends(self, days: int = 30) -> Dict[str, Any]:
        """
        Get cost trends over time.

        Args:
            days: Number of days to analyze

        Returns:
            Trend data including daily costs and growth rates
        """
        end_date = now_utc()
        start_date = end_date - timedelta(days=days)

        summary = await self.get_cost_summary(start_date, end_date)

        daily_costs = summary.get("daily_costs", {})
        sorted_dates = sorted(daily_costs)

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
            "trend": ("increasing" if growth_rate > 5 else "decreasing" if growth_rate < -5 else "stable"),
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
            logger.error("Failed to get recent usage: %s", e)
            return []

    async def get_cost_by_agent(self, agent_id: str) -> Dict[str, Any]:
        """Get cost breakdown for a specific agent (#1401)."""
        try:
            redis = await self.get_redis()
            agent_key = f"{self.AGENT_TOTALS_KEY}:{agent_id}"
            data = await redis.hgetall(agent_key)

            if not data:
                return {"agent_id": agent_id, "found": False}

            return {
                "agent_id": agent_id,
                "found": True,
                "cost_usd": float(data.get(b"cost_usd", 0) or data.get("cost_usd", 0)),
                "input_tokens": int(data.get(b"input_tokens", 0) or data.get("input_tokens", 0)),
                "output_tokens": int(data.get(b"output_tokens", 0) or data.get("output_tokens", 0)),
                "call_count": int(data.get(b"call_count", 0) or data.get("call_count", 0)),
            }
        except Exception as e:
            logger.error("Failed to get agent cost: %s", e)
            return {"agent_id": agent_id, "error": "Failed to retrieve agent cost"}

    async def get_all_agent_costs(self) -> List[Dict[str, Any]]:
        """Get cost breakdown for all agents (#1401)."""
        try:
            redis = await self.get_redis()
            pattern = f"{self.AGENT_TOTALS_KEY}:*"
            agent_keys = [
                k
                async for k in redis.scan_iter(pattern)
                if b":daily:" not in (k if isinstance(k, bytes) else k.encode())
            ]

            if not agent_keys:
                return []

            pipe = redis.pipeline()
            for key in agent_keys:
                pipe.hgetall(key)
            results = await pipe.execute()

            agents = []
            for key, data in zip(agent_keys, results):
                if not data:
                    continue
                key_str = key if isinstance(key, str) else key.decode("utf-8")
                agent_id = key_str.split(":")[-1]
                agents.append(
                    {
                        "agent_id": agent_id,
                        "cost_usd": float(data.get(b"cost_usd", 0) or data.get("cost_usd", 0)),
                        "input_tokens": int(data.get(b"input_tokens", 0) or data.get("input_tokens", 0)),
                        "output_tokens": int(data.get(b"output_tokens", 0) or data.get("output_tokens", 0)),
                        "call_count": int(data.get(b"call_count", 0) or data.get("call_count", 0)),
                    }
                )

            agents.sort(key=lambda x: x["cost_usd"], reverse=True)
            return agents
        except Exception as e:
            logger.error("Failed to get all agent costs: %s", e)
            return []

    async def set_agent_budget(self, agent_id: str, budget_monthly_usd: float) -> Dict[str, Any]:
        """Set monthly budget for an agent (#1401)."""
        try:
            redis = await self.get_redis()
            budget_cents = int(budget_monthly_usd * 100)
            await redis.hset(
                self.AGENT_BUDGET_KEY,
                agent_id,
                json.dumps(
                    {
                        "budget_monthly_cents": budget_cents,
                        "updated_at": utc_timestamp(),
                    }
                ),
            )
            return {
                "agent_id": agent_id,
                "budget_monthly_usd": budget_monthly_usd,
                "budget_monthly_cents": budget_cents,
                "status": "set",
            }
        except Exception as e:
            logger.error("Failed to set agent budget: %s", e)
            return {"agent_id": agent_id, "error": "Failed to set agent budget"}

    async def get_agent_budget(self, agent_id: str) -> Dict[str, Any] | None:
        """Get budget config for an agent (#1401)."""
        try:
            redis = await self.get_redis()
            raw = await redis.hget(self.AGENT_BUDGET_KEY, agent_id)
            if not raw:
                return None
            raw_str = raw if isinstance(raw, str) else raw.decode("utf-8")
            return json.loads(raw_str)
        except Exception as e:
            logger.error("Failed to get agent budget: %s", e)
            return None

    async def get_all_agent_budgets(
        self,
    ) -> Dict[str, Dict[str, Any]]:
        """Get all agent budget configs (#1401)."""
        try:
            redis = await self.get_redis()
            raw_data = await redis.hgetall(self.AGENT_BUDGET_KEY)
            budgets = {}
            for k, v in raw_data.items():
                k_str = k if isinstance(k, str) else k.decode("utf-8")
                v_str = v if isinstance(v, str) else v.decode("utf-8")
                budgets[k_str] = json.loads(v_str)
            return budgets
        except Exception as e:
            logger.error("Failed to get agent budgets: %s", e)
            return {}

    async def check_agent_budget(self, agent_id: str) -> Dict[str, Any]:
        """Check if agent has exceeded budget (#1401)."""
        budget = await self.get_agent_budget(agent_id)
        if not budget:
            return {
                "agent_id": agent_id,
                "has_budget": False,
                "exceeded": False,
            }

        cost_data = await self.get_cost_by_agent(agent_id)
        spent_usd = cost_data.get("cost_usd", 0)
        budget_cents = budget.get("budget_monthly_cents", 0)
        budget_usd = budget_cents / 100.0
        spent_cents = int(spent_usd * 100)
        exceeded = budget_cents > 0 and spent_cents >= budget_cents
        utilization = (spent_usd / budget_usd * 100) if budget_usd > 0 else 0

        return {
            "agent_id": agent_id,
            "has_budget": True,
            "budget_monthly_usd": budget_usd,
            "spent_usd": spent_usd,
            "remaining_usd": max(budget_usd - spent_usd, 0),
            "utilization_percent": round(utilization, 2),
            "exceeded": exceeded,
        }

    async def get_cost_by_user(self, user_id: str) -> dict[str, Any]:
        """Get cost breakdown for a specific user (#1807)."""
        try:
            redis = await self.get_redis()
            user_key = f"{self.USER_TOTALS_KEY}:{user_id}"
            data = await redis.hgetall(user_key)

            if not data:
                return {"user_id": user_id, "found": False}

            def _int(v: Any) -> int:
                return int(v) if v else 0

            def _float(v: Any) -> float:
                return float(v) if v else 0.0

            return {
                "user_id": user_id,
                "found": True,
                "cost_usd": _float(data.get(b"cost_usd") or data.get("cost_usd")),
                "input_tokens": _int(data.get(b"input_tokens") or data.get("input_tokens")),
                "output_tokens": _int(data.get(b"output_tokens") or data.get("output_tokens")),
                "call_count": _int(data.get(b"call_count") or data.get("call_count")),
            }
        except Exception as e:
            logger.error("Failed to get user cost: %s", e)
            return {"user_id": user_id, "error": "Failed to retrieve user cost"}

    async def set_budget_alert(self, name: str, alert_data: dict) -> None:
        """Persist a budget alert configuration to Redis (#5731)."""
        try:
            redis = await self._get_redis()
            if redis is None:
                logger.warning("Redis unavailable — budget alert '%s' not persisted", name)
                return
            await redis.hset(self.BUDGET_ALERTS_KEY, name, json.dumps(alert_data))
        except Exception as e:
            logger.error("Failed to persist budget alert '%s': %s", name, e)

    async def get_all_budget_alerts(self) -> dict:
        """Return all budget alert configurations from Redis (#5731).

        Returns:
            Dict mapping alert name (str) to decoded alert dict.
        """
        try:
            redis = await self._get_redis()
            if redis is None:
                logger.warning("Redis unavailable — returning empty budget alerts")
                return {}
            raw = await redis.hgetall(self.BUDGET_ALERTS_KEY)
            result = {}
            for k, v in raw.items():
                k_str = k if isinstance(k, str) else k.decode("utf-8")
                v_str = v if isinstance(v, str) else v.decode("utf-8")
                result[k_str] = json.loads(v_str)
            return result
        except Exception as e:
            logger.error("Failed to retrieve budget alerts: %s", e)
            return {}

    async def get_all_user_costs(self) -> list[dict[str, Any]]:
        """Get cost breakdown for all users (#1807)."""
        try:
            redis = await self.get_redis()
            pattern = f"{self.USER_TOTALS_KEY}:*"
            # Exclude daily sub-keys; use SCAN to avoid O(N) block on large keyspaces (#4443)
            user_keys = [
                k
                async for k in redis.scan_iter(pattern)
                if b":daily:" not in (k if isinstance(k, bytes) else k.encode())
            ]

            if not user_keys:
                return []

            pipe = redis.pipeline()
            for key in user_keys:
                pipe.hgetall(key)
            results = await pipe.execute()

            def _int(v: Any) -> int:
                return int(v) if v else 0

            def _float(v: Any) -> float:
                return float(v) if v else 0.0

            users = []
            for key, data in zip(user_keys, results):
                if not data:
                    continue
                key_str = key if isinstance(key, str) else key.decode("utf-8")
                user_id = key_str.split(":")[-1]
                users.append(
                    {
                        "user_id": user_id,
                        "cost_usd": _float(data.get(b"cost_usd") or data.get("cost_usd")),
                        "input_tokens": _int(data.get(b"input_tokens") or data.get("input_tokens")),
                        "output_tokens": _int(data.get(b"output_tokens") or data.get("output_tokens")),
                        "call_count": _int(data.get(b"call_count") or data.get("call_count")),
                    }
                )

            users.sort(key=lambda x: x["cost_usd"], reverse=True)
            return users
        except Exception as e:
            logger.error("Failed to get all user costs: %s", e)
            return []


# Singleton instance (thread-safe)
import threading

_cost_tracker: LLMCostTracker | None = None
_cost_tracker_lock = threading.Lock()


def get_cost_tracker() -> LLMCostTracker:
    """Get the singleton cost tracker instance (thread-safe)."""
    global _cost_tracker
    if _cost_tracker is None:
        with _cost_tracker_lock:
            # Double-check after acquiring lock
            if _cost_tracker is None:
                _cost_tracker = LLMCostTracker()
    return _cost_tracker
