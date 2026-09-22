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

from autobot_shared.local_models import LOCAL_MODEL_NAMES, is_local_model
from llm_shared.pricing.sync_cache import PricingCacheCold, get_cached_snapshot


def _unknown_date_reason(pricing_date, snapshot, sources) -> str | None:
    """Why `pricing_date` is `None`, distinguishing the three ways it can happen."""
    if pricing_date:
        return None
    if not snapshot:
        return (
            "the pricing cache is cold or stale, so no catalogue price could be read at all; "
            "only locally-served models are listed"
        )
    if sources == ["baseline"]:
        return "prices come from the hardcoded baselines, which record no fetch date"
    return "the catalogue returned prices but none of them states a fetch date"


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
        # Name the actual reason (#16230 review). The first version said
        # "prices are from the hardcoded baselines" for every dateless case --
        # but a cold or stale cache also produces no date, and then the response
        # holds no catalogue prices at all, only the local models appended
        # below. Reporting "baselines" there is a confident wrong answer about
        # provenance, in the field that exists to stop exactly that.
        "pricing_date_unknown_reason": _unknown_date_reason(pricing_date, snapshot, sources),
        "sources": sources,
        "currency": "USD",
        "models": pricing_list,
        "total_models": len(pricing_list),
    }


#: The rate an unmatched model is estimated at, per 1M tokens. Carried over from
#: the static-table version (#3528) and named here rather than left as two bare
#: floats inside a method: they are the one price in this module that no
#: catalogue supplies, and #16233's census cannot see a scalar literal the way it
#: sees a table.
#:
#: Not zero, deliberately -- an unmatched model reading as free is #15860's
#: defect, and this is an analytics projection where a rough number beats a
#: confident nothing. Not the catalogue's average either, which would be a
#: figure nobody chose.
UNMATCHED_MODEL_INPUT_PER_1M = 1.0
UNMATCHED_MODEL_OUTPUT_PER_1M = 5.0


def estimate_pattern_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate one LLM request's cost for the pattern analytics (#16230).

    Extracted from `analytics_llm_patterns.py`, which is grandfathered at its
    file-size ceiling (#5060) and may not grow.

    Matching is exact, then longest-prefix -- the same order
    `LLMCostTracker.calculate_cost` uses. The extraction originally preserved a
    bidirectional substring scan returning the FIRST match, so with both
    "gpt-4.1" and "gpt-4.1-mini" in the catalogue a request for the mini could be
    billed at the base rate depending only on dict iteration order (#2030's
    shape, raised again in #16230 review). Two estimates that differ by which
    order Redis happened to return keys in is not an estimate.

    One difference from the tracker remains and is deliberate: an unmatched model
    falls to a nominal rate here rather than $0.00, because this is a projection
    surface where a rough number beats a confident nothing, and #15860's rule
    says unmatched must not read as free. Changing that would move published
    analytics numbers.
    """
    model_lower = model.lower()

    if is_local_model(model_lower):
        return 0.0

    try:
        snapshot = get_cached_snapshot()
    except PricingCacheCold:
        # An analytics estimate, not a billing figure (unlike llc/services/budget.py,
        # which refuses): a cold or stale cache falls to the same "nothing matched"
        # default below rather than raising.
        snapshot = {}

    pricing = snapshot.get(model_lower)
    if pricing is None:
        for model_name in sorted(snapshot, key=len, reverse=True):
            if model_lower.startswith(model_name):
                pricing = snapshot[model_name]
                break
    if pricing is not None:
        return round(
            (input_tokens / 1_000_000) * pricing.input_per_1m + (output_tokens / 1_000_000) * pricing.output_per_1m,
            6,
        )

    return round(
        (input_tokens / 1_000_000) * UNMATCHED_MODEL_INPUT_PER_1M
        + (output_tokens / 1_000_000) * UNMATCHED_MODEL_OUTPUT_PER_1M,
        6,
    )
