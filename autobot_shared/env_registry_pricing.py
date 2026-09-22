# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pricing AUTOBOT_* environment variable registrations.

Split out of ``env_registry_backend_services.py`` (#16230), which #16229's five
pricing variables had already grown and which #16230's three more pushed past
the 600-line hard limit. Split by component rather than by cutting the file in
half at a line number: every sibling here is one component's variables, and the
pricing set is now large enough and self-contained enough to be one.

Importing this module registers the variables below into
``autobot_shared.env_registry.REGISTRY`` as a side effect, exactly like the
``register_env_var(...)`` calls in ``env_registry.py`` itself.
"""

from __future__ import annotations

from autobot_shared.env_registry import EnvVarSpec, register_env_var

#: Default pricing catalogue URLs, keyed by the variable that overrides each (#16229).
#: One home for the value: live_sources.py reads it back from REGISTRY, so the code,
#: the registry and the generated docs table cannot drift apart.
_PRICING_LITELLM_FILE = "model_prices_and_context_window.json"
_PRICING_URL_DEFAULTS = {
    "AUTOBOT_PRICING_LITELLM_URL": "https://raw.githubusercontent.com/BerriAI/litellm/main/" + _PRICING_LITELLM_FILE,
    "AUTOBOT_PRICING_OPENROUTER_URL": "https://openrouter.ai/api/v1/models",
}

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PRICING_CROSSCHECK_TOLERANCE_PERCENT",
        type=float,
        default=10.0,
        description=(
            "Percent difference between LiteLLM's and OpenRouter's price for one model above which the "
            "pricing refresh flags a disagreement. Flagged, never resolved silently (#16229)."
        ),
        component="pricing",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PRICING_FETCH_TIMEOUT_SECONDS",
        type=float,
        default=30.0,
        description=(
            "Total timeout, in seconds, for one live pricing catalogue fetch. A timed-out fetch is a failed "
            "refresh and leaves stored prices to age, never looking fresh (#16229)."
        ),
        component="pricing",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PRICING_LITELLM_URL",
        type=str,
        default=_PRICING_URL_DEFAULTS["AUTOBOT_PRICING_LITELLM_URL"],
        description=(
            "URL of LiteLLM's model price map, the primary live pricing catalogue. Fetched public-only "
            "through the egress guard (#16229)."
        ),
        component="pricing",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PRICING_OPENROUTER_URL",
        type=str,
        default=_PRICING_URL_DEFAULTS["AUTOBOT_PRICING_OPENROUTER_URL"],
        description=(
            "URL of OpenRouter's public models API, the cross-check pricing catalogue. Fetched public-only "
            "through the egress guard (#16229)."
        ),
        component="pricing",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PRICING_REFRESH_INTERVAL_HOURS",
        type=int,
        default=24,
        description=(
            "Hours between automatic pricing refreshes: the Celery beat cadence, and the floor under the "
            "Redis TTL so stored prices can never expire before the next scheduled refresh (#16231)."
        ),
        component="pricing",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PRICING_LOCAL_CACHE_REFRESH_INTERVAL_S",
        type=int,
        default=300,
        description=(
            "Seconds between re-reads of the pricing store into each process's own in-memory mirror "
            "(llm_shared/pricing/sync_cache.py, #16230). Independent of "
            "AUTOBOT_PRICING_REFRESH_INTERVAL_HOURS, which is how often Redis itself is refreshed from "
            "the live catalogues: this only has to stay close enough to that upstream write to be a "
            "mirror, and a short interval also recovers a worker that restarted mid-cycle rather than "
            "leaving it cold for the rest of the daily cadence."
        ),
        component="pricing",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PRICING_FIRST_REFRESH_TIMEOUT_S",
        type=float,
        default=10.0,
        description=(
            "Bound, in seconds, on the single pricing refresh awaited at startup before the app "
            "serves traffic (#16230). Without it the scheduler's first tick raced incoming "
            "requests, and budget.py refuses a cost event against a cold cache rather than "
            "recording zero. Exceeding the bound is non-fatal: the cache begins cold, which every "
            "caller already handles, and the next scheduled tick fills it."
        ),
        component="pricing",
    )
)

register_env_var(
    EnvVarSpec(
        name="AUTOBOT_PRICING_LOCAL_CACHE_MAX_AGE_S",
        type=int,
        default=3600,
        description=(
            "Age, in seconds, past which a process's pricing mirror is refused as stale rather than "
            "served (PricingCacheStale, #16230). This is what stops a scheduler that quietly stopped "
            "refreshing from looking identical to one that is working -- above this bound a reader gets "
            "an exception, never an old price presented as current. Must exceed "
            "AUTOBOT_PRICING_LOCAL_CACHE_REFRESH_INTERVAL_S by enough to survive a few failed ticks."
        ),
        component="pricing",
    )
)
