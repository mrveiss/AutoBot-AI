# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Refresh model pricing from live catalogues into Redis (GH#6480, #16229, #16231).

Runs on the daily Celery beat task ("pricing-refresh-daily"), as a one-shot CLI
(``python -m services.pricing_refresh``) the builtin updater invokes right after
every install/update of ``autobot-backend`` (``api/_pricing_post_sync.py``), once
per worker start when the store is still empty (``pricing.refresh_if_empty``,
queued from the ``worker_ready`` signal below -- see its docstring for why this
lives here and not in the FastAPI lifespan, #16231/#16250), and on demand from
the admin "refresh now" endpoint (``api/admin_pricing.py``) -- one refresh
routine, four triggers.

LiteLLM's price map is the primary catalogue and OpenRouter's models API the
cross-check (``llm_shared/pricing/crosscheck.py``). A disagreement is recorded
and flagged, never resolved silently. A catalogue that fails -- or returns
nothing -- is recorded as a failure and writes nothing, so stored prices keep
their real fetch time and age into "stale" instead of looking fresh.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import TYPE_CHECKING

from celery.signals import worker_ready

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


async def refresh_all() -> dict:
    """Fetch both catalogues, cross-check them, write the result; return a summary.

    The one refresh routine every trigger (beat, post-sync CLI, first boot,
    admin "refresh now") calls (#16231).
    """
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


async def refresh_if_empty() -> dict | None:
    """Refresh once, only if the store has never been refreshed (#16231, AC2).

    Run by the ``pricing.refresh_if_empty`` Celery task below, queued when a
    worker comes up, so a first boot with an empty Redis has live prices
    without waiting for the next beat tick or an update. Never raises — a
    first-boot failure must not affect worker startup; the reason is logged
    and the next scheduled or on-demand refresh retries.
    """
    from llm_shared.pricing.redis_store import PricingRedisStore

    try:
        if await PricingRedisStore().get_refresh_status():
            return None
        summary = await refresh_all()
        logger.info("pricing_refresh: first-boot refresh — %s", {k: v for k, v in summary.items() if k != "crosscheck"})
        return summary
    except Exception as exc:  # noqa: BLE001 -- a first-boot failure must never affect startup
        logger.warning("pricing_refresh: first-boot refresh failed (non-critical): %s", exc)
        return None


@celery_app.task(name="pricing.refresh_if_empty")
def refresh_pricing_if_empty():
    """Celery task: run ``refresh_if_empty`` (#16231, AC2).

    Queued -- never run inline -- by the ``worker_ready`` handler below, so a
    slow or unreachable catalogue on first boot cannot delay the worker from
    coming up and accepting other work.
    """
    logger.info("pricing_refresh: worker-ready — checking for a first-boot refresh")
    return _run_async(refresh_if_empty())


@worker_ready.connect
def _queue_first_boot_refresh(**_kwargs) -> None:
    """Queue the first-boot pricing refresh when a Celery worker comes up.

    Not a FastAPI ``initialization/lifespan.py`` hook: pricing refresh already
    lives entirely on Celery (the daily beat task below), so "at startup" is
    naturally the Celery worker's own startup, not the web process's. It also
    keeps this change out of ``lifespan.py`` entirely -- that file's two
    pre-existing oversized functions (``cleanup_services``,
    ``_init_graph_rag_service``) trip the local function-length pre-commit
    hook on the *whole file* regardless of what changed (#16250), so a web
    lifespan hook would have blocked every future commit touching it.
    ``.delay()``, not a direct call: the check must never block worker
    startup (#16231).
    """
    refresh_pricing_if_empty.delay()


@celery_app.task(bind=True, name="pricing.refresh_daily")
def refresh_pricing_daily(self):
    """Celery beat task: pull pricing from the live catalogues and cache it in Redis."""
    logger.info("pricing_refresh: starting refresh")
    try:
        summary = _run_async(refresh_all())
        logger.info("pricing_refresh: complete — %s", {k: v for k, v in summary.items() if k != "crosscheck"})
        return summary
    except Exception as exc:
        logger.exception("pricing_refresh: fatal error: %s", exc)
        raise


def main() -> int:
    """One-shot CLI entry point: `python -m services.pricing_refresh` (#16231).

    Invoked by the builtin updater's post-sync step (autobot-slm-backend's
    ``api/_pricing_post_sync.py``) right after every install/update of
    autobot-backend, inside that component's own deployed venv. The summary is
    machine output for the caller, written as one JSON line on stdout — not a
    log line, since the caller parses it. Exits non-zero when nothing was
    written, so the caller can tell an offline/failed install apart from one
    that refreshed successfully, without parsing the summary itself.
    """
    summary = asyncio.run(refresh_all())
    sys.stdout.write(json.dumps(summary) + "\n")
    return 0 if summary.get("written", 0) > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
