# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""DeepSeek pricing source (GH#6480).

DeepSeek does not expose a stable machine-readable pricing API. This source
returns the authoritative hardcoded table as the baseline. When DeepSeek
publishes a pricing API endpoint, replace _fetch_from_api() body and remove
the hardcoded fallback.
"""

from __future__ import annotations

from llm_shared.pricing.sources import BaselinePricingSource

_PROVIDER = "deepseek"

# Hardcoded baseline — kept in sync with ssot_constants.MODEL_PRICING_PER_1M_TOKENS.
# Keys use the same model IDs as DEEPSEEK_* constants (GH#6480).
_BASELINE: list[tuple[str, float, float]] = [
    # (model_id, input_per_1m, output_per_1m)
    ("deepseek-v3", 0.27, 1.10),
    ("deepseek-r1", 0.55, 2.19),
]


class DeepSeekPricingSource(BaselinePricingSource):
    provider = _PROVIDER
    _PROVIDER = _PROVIDER
    _BASELINE = _BASELINE
