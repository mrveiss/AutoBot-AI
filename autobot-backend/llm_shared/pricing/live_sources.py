# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Live pricing sources: LiteLLM's price map and OpenRouter's models API (#16229).

Neither catalogue is trusted alone. LiteLLM is the primary -- direct-provider
prices, broad coverage -- and OpenRouter is an independent second derivation
that ``crosscheck.py`` compares it against. Both are fetched over the shared
client with ``guard_egress=False``: public addresses only, redirects refused
(CLAUDE rule 8).

A price the source does not state is None, never 0. A missing cache price is
an unknown cache price, and OpenRouter's ``"-1"`` marks a variable-price router,
not a free model. ``"0"`` IS a real price -- OpenRouter's ``:free`` variants --
and is kept.

A fetch that fails -- an HTTP error, a timeout, malformed JSON, or a 200 whose
body is not the documented shape -- yields an empty mapping, and the refresh
treats empty as failure, so a broken fetch can never make pricing look fresh.
"""

from __future__ import annotations

import math
from datetime import datetime

import aiohttp

from autobot_shared.env_registry import REGISTRY
from autobot_shared.env_utils import env_float, env_str
from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger
from llm_shared.pricing.sources import ModelPricing, PricingSource

logger = get_logger(__name__)

# The default URLs live once, in the env registry that documents them (#16229).
LITELLM_PRICES_URL = env_str("AUTOBOT_PRICING_LITELLM_URL", REGISTRY["AUTOBOT_PRICING_LITELLM_URL"].default)
OPENROUTER_MODELS_URL = env_str("AUTOBOT_PRICING_OPENROUTER_URL", REGISTRY["AUTOBOT_PRICING_OPENROUTER_URL"].default)
FETCH_TIMEOUT_SECONDS = env_float("AUTOBOT_PRICING_FETCH_TIMEOUT_SECONDS", 30.0)
_TOKENS_PER_MILLION = 1_000_000


async def _fetch_json(url: str) -> object | None:
    """GET *url* through the guarded shared client; None on any failure, which is logged."""
    try:
        # guard_egress=False is not "unguarded": it permits public addresses only and
        # refuses redirects (rule 8). None is the unguarded mode.
        async with get_http_client().tracked_request(
            "GET", url, timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT_SECONDS), guard_egress=False
        ) as resp:
            if resp.status != 200:
                logger.warning("pricing fetch %s: HTTP %s", url, resp.status)
                return None
            # raw.githubusercontent.com serves JSON as text/plain.
            return await resp.json(content_type=None)
    except Exception as exc:  # noqa: BLE001 -- reported as a failed source, never as zero prices
        logger.warning("pricing fetch %s failed: %s", url, exc)
        return None


def per_1m(value: object) -> float | None:
    """A per-token price as USD per 1M tokens; None when absent, malformed or negative."""
    if value is None or isinstance(value, bool):
        return None
    try:
        per_token = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(per_token) or per_token < 0:  # NaN/inf are malformed; negative is a sentinel
        return None
    return per_token * _TOKENS_PER_MILLION


def parse_litellm(document: object, now: datetime) -> dict[str, ModelPricing]:
    """LiteLLM entries with both token prices, keyed by LiteLLM's model key.

    An entry missing either price, or its provider, is skipped -- not priced at 0.
    """
    if not isinstance(document, dict):
        return {}
    result: dict[str, ModelPricing] = {}
    for model_id, entry in document.items():
        if model_id == "sample_spec" or not isinstance(entry, dict):
            continue
        provider = entry.get("litellm_provider")
        inp, out = per_1m(entry.get("input_cost_per_token")), per_1m(entry.get("output_cost_per_token"))
        if not isinstance(provider, str) or not provider or inp is None or out is None:
            continue
        result[model_id] = ModelPricing(
            provider=provider,
            model_id=model_id,
            input_per_1m=inp,
            output_per_1m=out,
            cache_read_per_1m=per_1m(entry.get("cache_read_input_token_cost")),
            cache_write_per_1m=per_1m(entry.get("cache_creation_input_token_cost")),
            updated_at=now,
            source="litellm",
        )
    return result


def parse_openrouter(document: object, now: datetime) -> dict[str, ModelPricing]:
    """OpenRouter models with both token prices, keyed by the full id ("vendor/model[:variant]")."""
    models = document.get("data") if isinstance(document, dict) else None
    if not isinstance(models, list):
        return {}
    result: dict[str, ModelPricing] = {}
    for model in models:
        model_id = model.get("id") if isinstance(model, dict) else None
        pricing = model.get("pricing") if isinstance(model, dict) else None
        if not isinstance(model_id, str) or "/" not in model_id or not isinstance(pricing, dict):
            continue
        inp, out = per_1m(pricing.get("prompt")), per_1m(pricing.get("completion"))
        if inp is None or out is None:
            continue
        vendor, name = model_id.split("/", 1)
        result[model_id] = ModelPricing(
            provider=vendor,
            model_id=name,
            input_per_1m=inp,
            output_per_1m=out,
            cache_read_per_1m=per_1m(pricing.get("input_cache_read")),
            cache_write_per_1m=per_1m(pricing.get("input_cache_write")),
            updated_at=now,
            source="openrouter",
        )
    return result


class LiteLLMPricingSource(PricingSource):
    """Primary catalogue: LiteLLM's community-maintained map of direct-provider prices."""

    provider = "litellm"

    async def fetch(self) -> dict[str, ModelPricing]:
        return parse_litellm(await _fetch_json(LITELLM_PRICES_URL), self._now())


class OpenRouterPricingSource(PricingSource):
    """Cross-check catalogue: OpenRouter's public models API."""

    provider = "openrouter"

    async def fetch(self) -> dict[str, ModelPricing]:
        return parse_openrouter(await _fetch_json(OPENROUTER_MODELS_URL), self._now())
