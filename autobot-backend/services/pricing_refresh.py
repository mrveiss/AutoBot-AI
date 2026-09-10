# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Daily Celery beat task: refresh model pricing from live catalogues into Redis (GH#6480, #16229).

Wired into celery_app.py beat_schedule as "pricing-refresh-daily".

LiteLLM's price map is the primary catalogue and OpenRouter's models API the
cross-check (``llm_shared/pricing/crosscheck.py``). A disagreement is recorded
and flagged, never resolved silently. A catalogue that fails -- or returns
nothing -- is recorded as a failure and writes nothing, so stored prices keep
their real fetch time and age into "stale" instead of looking fresh.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from autobot_shared.env_utils import env_float
from autobot_shared.logging_manager import get_logger
from celery_app import celery_app

if TYPE_CHECKING:
    from llm_shared.pricing.crosscheck import CrossCheckReport
    from llm_shared.pricing.sources import ModelPricing

logger = get_logger(__name__)

CROSSCHECK_TOLERANCE_PERCENT: float = env_float("AUTOBOT_PRICING_CROSSCHECK_TOLERANCE_PERCENT", 10.0)
_MAX_LOGGED_DISAGREEMENTS = 20


def _build_sources():
    """The primary catalogue, then the cross-check catalogue."""
    from llm_shared.pricing.live_sources import LiteLLMPricingSource, OpenRouterPricingSource

    return LiteLLMPricingSource(), OpenRouterPricingSource()


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _fetch(source, store, summary: dict) -> "dict[str, ModelPricing]":
    """Fetch one catalogue and record the attempt; an empty result is a failure."""
    try:
        pricings = await source.fetch()
    except Exception as exc:  # noqa: BLE001 -- recorded as a failed source, never as fresh prices
        logger.exception("pricing_refresh: %s fetch raised: %s", source.provider, exc)
        pricings = {}
    ok = bool(pricings)
    await store.set_refresh_status(source.provider, success=ok, model_count=len(pricings))
    summary["sources"][source.provider] = {"success": ok, "model_count": len(pricings)}
    if not ok:
        logger.warning("pricing_refresh: %s returned no prices; nothing written from it", source.provider)
    return pricings


def _merge(primary: dict, secondary: dict, verdicts: dict, secondary_only: list) -> "dict[str, ModelPricing]":
    """Primary prices labelled with their cross-check verdict, then models only the cross-check lists."""
    merged: dict = {}
    for key, pricing in primary.items():
        pricing.crosscheck = verdicts.get(key, "unchecked")
        merged[f"{pricing.source}:{key}"] = pricing
    for key in secondary_only:
        pricing = secondary[key]
        pricing.crosscheck = "single"
        merged[f"{pricing.source}:{key}"] = pricing
    return merged


def _log_disagreements(report: "CrossCheckReport") -> None:
    for flag in report.disagreed[:_MAX_LOGGED_DISAGREEMENTS]:
        logger.warning(
            "pricing_crosscheck_disagreement model=%s openrouter=%s field=%s litellm_value=%.4f "
            "openrouter_value=%.4f percent=%.1f",
            flag["model"],
            flag["secondary"],
            flag["field"],
            flag["primary_value"],
            flag["secondary_value"],
            flag["percent"],
        )
    if len(report.disagreed) > _MAX_LOGGED_DISAGREEMENTS:
        logger.warning(
            "pricing_crosscheck: %d further disagreements not logged; the stored report has them all",
            len(report.disagreed) - _MAX_LOGGED_DISAGREEMENTS,
        )


async def _refresh_all() -> dict:
    """Fetch both catalogues, cross-check them, write the result; return a summary."""
    from llm_shared.pricing.crosscheck import cross_check
    from llm_shared.pricing.redis_store import PricingRedisStore

    store = PricingRedisStore()
    primary_source, secondary_source = _build_sources()
    await store.retain_refresh_status({primary_source.provider, secondary_source.provider})
    summary: dict = {"sources": {}}
    primary = await _fetch(primary_source, store, summary)
    secondary = await _fetch(secondary_source, store, summary)
    if not primary:
        return summary
    report, verdicts, secondary_only = cross_check(primary, secondary, CROSSCHECK_TOLERANCE_PERCENT)
    merged = _merge(primary, secondary, verdicts, secondary_only)
    summary["written"] = await store.set_many(merged)
    summary["indexed"] = await store.set_model_index(merged)
    summary["crosscheck"] = report.to_dict()
    await store.set_crosscheck(summary["crosscheck"])
    _log_disagreements(report)
    return summary


@celery_app.task(bind=True, name="pricing.refresh_daily")
def refresh_pricing_daily(self):
    """Celery beat task: pull pricing from the live catalogues and cache it in Redis."""
    logger.info("pricing_refresh: starting daily refresh")
    try:
        summary = _run_async(_refresh_all())
        logger.info("pricing_refresh: complete — %s", {k: v for k, v in summary.items() if k != "crosscheck"})
        return summary
    except Exception as exc:
        logger.exception("pricing_refresh: fatal error: %s", exc)
        raise
