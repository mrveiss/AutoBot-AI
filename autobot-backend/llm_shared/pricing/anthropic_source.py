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

from llm_shared.pricing.sources import BaselinePricingSource

_PROVIDER = "anthropic"

# Hardcoded baseline. The canonical table is `autobot_shared.model_pricing.
# MODEL_PRICING_PER_1M_TOKENS` (it moved out of `ssot_constants` in #15910, and
# this pointer named the old home until #15912). Agreement is enforced by
# `repo_tests/model_pricing_tables_agree_15912_test.py`, not by remembering:
# this table's `deepseek-r1` had been charging API rates against the local
# model's id, and `PER_1K` had two prices years out of date.
# Keys use the same model IDs as ANTHROPIC_* constants (GH#6480).
_BASELINE: list[tuple[str, float, float, float]] = [
    # (model_id, input_per_1m, output_per_1m, cache_read_per_1m)
    # Current generation (#20884; ids = autobot_shared.ssot_claude_models). Cache-write prices
    # are not stated by the source and are not recorded. Haiku's cache-read is not stated either,
    # so its 4th element is omitted (the source default of 0.0 applies, meaning unstated).
    ("claude-fable-5-1", 10.00, 50.00, 0.25),
    ("claude-opus-5-5", 4.00, 20.00, 0.20),
    ("claude-sonnet-5-5", 2.00, 10.00, 0.20),
    ("claude-haiku-5-5", 0.10, 0.50),
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
