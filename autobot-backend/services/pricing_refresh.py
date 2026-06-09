# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Daily Celery beat task: refresh MODEL_PRICING from provider sources into Redis (GH#6480).

Wired into celery_app.py beat_schedule as "pricing-refresh-daily".

Fallback chain in llm_cost_tracker.calculate_cost():
  1. Redis (written by this task)
  2. Hardcoded MODEL_PRICING_PER_1M_TOKENS
  3. Pattern-based heuristic

Drift detection: when a fetched price differs from the hardcoded table by more
than DRIFT_THRESHOLD_PERCENT, a structured audit event is emitted so operators
can update the hardcoded table.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from autobot_shared.logging_manager import get_logger
from celery_app import celery_app
from constants.model_constants import MODEL_PRICING_PER_1M_TOKENS

if TYPE_CHECKING:
    from llm_shared.pricing.sources import ModelPricing

logger = get_logger(__name__)

DRIFT_THRESHOLD_PERCENT: float = 10.0


# All active pricing sources; add new providers here.
def _build_sources():
    from llm_shared.pricing.anthropic_source import AnthropicPricingSource
    from llm_shared.pricing.deepseek_source import DeepSeekPricingSource
    from llm_shared.pricing.google_source import GooglePricingSource
    from llm_shared.pricing.openai_source import OpenAIPricingSource

    return [
        AnthropicPricingSource(),
        DeepSeekPricingSource(),
        GooglePricingSource(),
        OpenAIPricingSource(),
    ]


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _refresh_all() -> dict:
    """Fetch from all sources, write to Redis, return summary."""
    from llm_shared.pricing.redis_store import PricingRedisStore

    store = PricingRedisStore()
    sources = _build_sources()
    summary: dict[str, dict] = {}

    for source in sources:
        provider = source.provider
        try:
            pricings = await source.fetch()
            if not pricings:
                logger.warning("pricing_refresh: %s returned empty dict", provider)
                await store.set_refresh_status(provider, success=False, model_count=0)
                summary[provider] = {"success": False, "model_count": 0}
                continue

            _detect_drift(provider, pricings)

            count = await store.set_many(pricings)
            await store.set_refresh_status(provider, success=True, model_count=count)
            summary[provider] = {"success": True, "model_count": count}
            logger.info("pricing_refresh: %s — wrote %d entries to Redis", provider, count)
        except Exception as exc:
            logger.exception("pricing_refresh: unexpected error for %s: %s", provider, exc)
            await store.set_refresh_status(provider, success=False, model_count=0)
            summary[provider] = {"success": False, "error": str(exc)}

    return summary


def _detect_drift(provider: str, fetched: "dict[str, ModelPricing]") -> None:
    """Log structured WARNING when fetched price diverges from hardcoded table by >threshold."""
    for model_id, new_pricing in fetched.items():
        hardcoded = MODEL_PRICING_PER_1M_TOKENS.get(model_id)
        if hardcoded is None:
            continue

        for field_name, new_val, old_val in [
            ("input", new_pricing.input_per_1m, hardcoded.get("input", 0)),
            ("output", new_pricing.output_per_1m, hardcoded.get("output", 0)),
        ]:
            if old_val == 0:
                continue
            pct_diff = abs(new_val - old_val) / old_val * 100
            if pct_diff > DRIFT_THRESHOLD_PERCENT:
                logger.warning(
                    "pricing_drift provider=%s model=%s field=%s "
                    "hardcoded=%.4f fetched=%.4f drift_pct=%.1f%% "
                    "— update MODEL_PRICING_PER_1M_TOKENS in ssot_constants.py (GH#6480)",
                    provider,
                    model_id,
                    field_name,
                    old_val,
                    new_val,
                    pct_diff,
                )


@celery_app.task(bind=True, name="pricing.refresh_daily")
def refresh_pricing_daily(self):
    """Celery beat task: pull pricing from all known sources and cache in Redis."""
    logger.info("pricing_refresh: starting daily refresh")
    try:
        summary = _run_async(_refresh_all())
        logger.info("pricing_refresh: complete — %s", summary)
        return summary
    except Exception as exc:
        logger.exception("pricing_refresh: fatal error: %s", exc)
        raise
