# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which model names are local/self-hosted, and therefore free by construction (#16316).

Before #16230, `autobot_shared.model_pricing.MODEL_PRICING_PER_1M_TOKENS` carried
an explicit `{"input": 0.0, "output": 0.0}` entry for every local model. That
table is gone -- pricing now comes from the live catalogue via
`llm_shared.pricing.redis_store.PricingRedisStore` (#16229) -- but a local model
was never priced *by* that table, it was priced *despite* never leaving the
operator's machine. LiteLLM and OpenRouter publish hosted-API prices only, so a
local model resolves to no live price either, and #15860's rule (`UnpricedModel`
on a missing price) would otherwise refuse every cost event for it -- a real
regression from the pre-#16230 behaviour, not a re-introduction of the bug
#15860 fixed.

This module is the one place that distinguishes the two zero-price reasons:
"free by construction" (a local model, checked here, first, before any pricing
lookup) versus "priced at zero because nobody looked it up" (never true --
absence from the live catalogue means unpriced, not free, for every model NOT
in `LOCAL_MODEL_NAMES`).

`LOCAL_MODEL_NAMES` is the exact set the old table's zero entries covered --
not a new classification, a name for one that already existed. Extracted here
rather than added to `ssot_constants.py` (it defines the `LOCAL_*` constants
this module imports) because that file sits at its own file-size ratchet
ceiling and a grandfathered file may not grow -- the same reason
`model_pricing.py` was its own file before this one replaced it.
"""

from __future__ import annotations

from autobot_shared.ssot_constants import (
    LOCAL_CODELLAMA,
    LOCAL_DEEPSEEK_CODER,
    LOCAL_DEEPSEEK_R1,
    LOCAL_GEMMA2,
    LOCAL_GEMMA3,
    LOCAL_LLAMA3,
    LOCAL_LLAMA31,
    LOCAL_LLAMA32,
    LOCAL_LLAMA33,
    LOCAL_MISTRAL,
    LOCAL_MIXTRAL,
    LOCAL_PHI3,
    LOCAL_PHI4,
    LOCAL_QWEN25,
    LOCAL_QWEN3,
)

LOCAL_MODEL_NAMES: frozenset[str] = frozenset(
    {
        LOCAL_LLAMA3,
        LOCAL_LLAMA31,
        LOCAL_LLAMA32,
        LOCAL_LLAMA33,
        LOCAL_MISTRAL,
        LOCAL_MIXTRAL,
        LOCAL_CODELLAMA,
        LOCAL_QWEN25,
        LOCAL_QWEN3,
        LOCAL_DEEPSEEK_CODER,
        LOCAL_DEEPSEEK_R1,
        LOCAL_PHI3,
        LOCAL_PHI4,
        LOCAL_GEMMA2,
        LOCAL_GEMMA3,
    }
)


def is_local_model(model_id: str) -> bool:
    """True when *model_id* is free by construction, never billed per token.

    Case-sensitive and exact -- these are the bare Ollama-served names
    (`"llama3"`, not `"Llama3"` or `"ollama/llama3"`), matching how every
    caller of `ingest_cost_event`/`calculate_cost` has always passed them.
    """
    return model_id in LOCAL_MODEL_NAMES
