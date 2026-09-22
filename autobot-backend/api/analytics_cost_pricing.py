# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The payload behind ``GET /cost/pricing`` (#16230).

Extracted from `analytics_cost.py`, which is a grandfathered file at its
file-size ceiling (#5060) and may not grow. The endpoint there is now the route
and the auth check; everything it answers with is assembled here.
"""

from __future__ import annotations

from typing import Any, Dict

from autobot_shared.local_models import LOCAL_MODEL_NAMES
from llm_shared.pricing.sync_cache import PricingCacheCold, get_cached_snapshot


def build_pricing_payload() -> Dict[str, Any]:
    """Every model the live catalogue prices, plus the local models it never will."""
    try:
        snapshot = get_cached_snapshot()
    except PricingCacheCold:
        snapshot = {}

    pricing_list = []

    for model, pricing in snapshot.items():
        pricing_list.append(
            {
                "model": model,
                # `pricing.provider` is stamped by the live source itself
                # (LiteLLM/OpenRouter) rather than guessed from the model
                # name -- the old name-substring heuristic only worked
                # because the static table it read from was a short, fully
                # enumerated list; the live catalogue is neither.
                "provider": pricing.provider or "unknown",
                "input_price_per_1m": pricing.input_per_1m,
                "output_price_per_1m": pricing.output_per_1m,
                "is_free": pricing.input_per_1m == 0 and pricing.output_per_1m == 0,
            }
        )

    # Local models are never in the live catalogue (#16316) -- free by
    # construction, not absent because nobody priced them.
    for model in sorted(LOCAL_MODEL_NAMES):
        pricing_list.append(
            {
                "model": model,
                "provider": "local",
                "input_price_per_1m": 0.0,
                "output_price_per_1m": 0.0,
                "is_free": True,
            }
        )

    # Sort by provider then by price
    pricing_list.sort(key=lambda x: (x["provider"], -x["input_price_per_1m"]))

    # #16233: manufactured freshness is exactly what this replaces a fixed
    # literal to avoid -- the real freshest `updated_at` the live catalogue
    # states. When no entry carries one, the honest answer is `None`, not
    # today: the hardcoded baselines (#16230's last-resort fallback) carry
    # `updated_at=None` precisely because nobody knows when their literals were
    # last true, and reporting today's date over them would put the frozen
    # "2025-01-01" literal's defect back in a more credible shape -- a stale
    # catalogue that reads as refreshed this morning.
    catalogue_dates = [p.updated_at for p in snapshot.values() if p.updated_at is not None]
    pricing_date = max(catalogue_dates).date().isoformat() if catalogue_dates else None
    #: Provenance, so a caller can act on WHY the date is missing rather than
    #: guessing. Nothing but the baseline fallback writes "baseline".
    sources = sorted({p.source for p in snapshot.values() if p.source})

    return {
        "pricing_date": pricing_date,
        "pricing_date_unknown_reason": (
            None if pricing_date else "no catalogue entry states a fetch date; prices are from the hardcoded baselines"
        ),
        "sources": sources,
        "currency": "USD",
        "models": pricing_list,
        "total_models": len(pricing_list),
    }
