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

# Hardcoded baseline. The canonical table is `autobot_shared.model_pricing.
# MODEL_PRICING_PER_1M_TOKENS` (it moved out of `ssot_constants` in #15910, and
# this pointer named the old home until #15912). Agreement is enforced by
# `repo_tests/model_pricing_tables_agree_15912_test.py`, not by remembering:
# this table's `deepseek-r1` had been charging API rates against the local
# model's id, and `PER_1K` had two prices years out of date.
# Keys use the same model IDs as DEEPSEEK_* constants (GH#6480).
_BASELINE: list[tuple[str, float, float]] = [
    # (model_id, input_per_1m, output_per_1m)
    ("deepseek-v3", 0.27, 1.10),
    # #15912: was keyed "deepseek-r1". That is `LOCAL_DEEPSEEK_R1`, priced 0.0/0.0
    # as a locally-hosted model; the paid one is `DEEPSEEK_R1_API`. This table
    # charged API rates against the local model's id, so the same string meant
    # "free" or "$0.55/1M" depending on which table a consumer read.
    ("deepseek-r1-api", 0.55, 2.19),
]


class DeepSeekPricingSource(BaselinePricingSource):
    provider = _PROVIDER
    _PROVIDER = _PROVIDER
    _BASELINE = _BASELINE
