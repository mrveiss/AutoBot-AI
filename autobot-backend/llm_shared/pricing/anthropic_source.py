# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Anthropic pricing source (GH#6480).

Anthropic does not expose a machine-readable pricing API. This source
returns the authoritative hardcoded table as the baseline. When Anthropic
publishes a pricing API endpoint, replace _fetch_from_api() body and remove
the hardcoded fallback.
"""

from __future__ import annotations

from autobot_shared.model_pricing import MODEL_PRICING_PER_1M_TOKENS
from autobot_shared.ssot_claude_models import CLAUDE_FABLE, CLAUDE_HAIKU, CLAUDE_OPUS, CLAUDE_SONNET
from llm_shared.pricing.sources import BaselinePricingSource

_PROVIDER = "anthropic"

# Hardcoded baseline. The canonical table is `autobot_shared.model_pricing.
# MODEL_PRICING_PER_1M_TOKENS` (it moved out of `ssot_constants` in #15910, and
# this pointer named the old home until #15912). Agreement is enforced by
# `repo_tests/model_pricing_tables_agree_15912_test.py`, not by remembering:
# this table's `deepseek-r1` had been charging API rates against the local
# model's id, and `PER_1K` had two prices years out of date.
# Keys use the same model IDs as ANTHROPIC_* constants (GH#6480).
#: Cache-read prices of the current generation (per 1M). ``None`` is "not stated by the source": unknown,
#: never 0.0 (which reads as free). Cache-write prices are not stated and are not recorded.
_CURRENT_CACHE_READ_PER_1M: dict[str, float | None] = {
    CLAUDE_FABLE: 0.25,
    CLAUDE_OPUS: 0.20,
    CLAUDE_SONNET: 0.20,
    CLAUDE_HAIKU: None,
}

# Input/output prices of the current generation are read from the canonical table, not restated (#20884).
_BASELINE: list[tuple[str, float, float, float | None]] = [
    # (model_id, input_per_1m, output_per_1m, cache_read_per_1m)
    *(
        (model, MODEL_PRICING_PER_1M_TOKENS[model]["input"], MODEL_PRICING_PER_1M_TOKENS[model]["output"], cache_read)
        for model, cache_read in _CURRENT_CACHE_READ_PER_1M.items()
    ),
    ("claude-opus-4-0", 15.00, 75.00, 1.50),
    ("claude-haiku-4-5", 0.80, 4.00, 0.08),
    ("claude-sonnet-4-0", 3.00, 15.00, 0.30),
    ("claude-3-5-sonnet-20241022", 3.00, 15.00, 0.30),
    ("claude-3-5-haiku-20241022", 0.80, 4.00, 0.08),
    ("claude-3-opus-20240229", 15.00, 75.00, 1.50),
    ("claude-3-sonnet-20240229", 3.00, 15.00, 0.30),
    ("claude-3-haiku-20240307", 0.25, 1.25, 0.03),
]


class AnthropicPricingSource(BaselinePricingSource):
    provider = _PROVIDER
    _PROVIDER = _PROVIDER
    _BASELINE = _BASELINE
