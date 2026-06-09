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

from autobot_shared.logging_manager import get_logger
from llm_shared.pricing.sources import ModelPricing, PricingSource

logger = get_logger(__name__)

_PROVIDER = "deepseek"

# Hardcoded baseline — kept in sync with ssot_constants.MODEL_PRICING_PER_1M_TOKENS.
# Keys use the same model IDs as DEEPSEEK_* constants (GH#6480).
_BASELINE: list[tuple[str, float, float]] = [
    # (model_id, input_per_1m, output_per_1m)
    ("deepseek-v3", 0.27, 1.10),
    ("deepseek-r1", 0.55, 2.19),
]


class DeepSeekPricingSource(PricingSource):
    provider = _PROVIDER

    async def fetch(self) -> dict[str, ModelPricing]:
        now = self._now()
        result: dict[str, ModelPricing] = {}
        for model_id, inp, out in _BASELINE:
            result[model_id] = ModelPricing(
                provider=_PROVIDER,
                model_id=model_id,
                input_per_1m=inp,
                output_per_1m=out,
                updated_at=now,
            )
        logger.debug("DeepSeekPricingSource.fetch returned %d models", len(result))
        return result
