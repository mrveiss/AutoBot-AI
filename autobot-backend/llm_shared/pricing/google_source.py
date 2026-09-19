# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Google pricing source (GH#6480).

Google Gemini does not expose a stable machine-readable pricing API. This source
returns the authoritative hardcoded table as the baseline. When Google publishes
a pricing API endpoint, replace _fetch_from_api() body and remove the hardcoded
fallback.
"""

from __future__ import annotations

from llm_shared.pricing.sources import BaselinePricingSource

_PROVIDER = "google"

# Hardcoded baseline. The canonical table is `autobot_shared.model_pricing.
# MODEL_PRICING_PER_1M_TOKENS` (it moved out of `ssot_constants` in #15910, and
# this pointer named the old home until #15912). Agreement is enforced by
# `repo_tests/model_pricing_tables_agree_15912_test.py`, not by remembering:
# this table's `deepseek-r1` had been charging API rates against the local
# model's id, and `PER_1K` had two prices years out of date.
# Keys use the same model IDs as GOOGLE_GEMINI* constants (GH#6480).
_BASELINE: list[tuple[str, float, float]] = [
    # (model_id, input_per_1m, output_per_1m)
    ("gemini-2.5-pro", 1.25, 5.00),
    ("gemini-2.5-flash", 0.075, 0.30),
    ("gemini-2.0-flash", 0.075, 0.30),
    ("gemini-1.5-pro", 1.25, 5.00),
    ("gemini-1.5-flash", 0.075, 0.30),
    ("gemini-pro", 0.50, 1.50),
    ("gemini-pro-vision", 0.50, 1.50),
]


class GooglePricingSource(BaselinePricingSource):
    provider = _PROVIDER
    _PROVIDER = _PROVIDER
    _BASELINE = _BASELINE
