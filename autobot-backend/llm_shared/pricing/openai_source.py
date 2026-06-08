# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""OpenAI pricing source (GH#6480).

OpenAI does not expose a stable machine-readable pricing API. This source
uses the hardcoded baseline as authoritative input and is structured to
accept a future live-fetch implementation without changes to callers.
"""

from __future__ import annotations

from autobot_shared.logging_manager import get_logger
from llm_shared.pricing.sources import ModelPricing, PricingSource

logger = get_logger(__name__)

_PROVIDER = "openai"

# Hardcoded baseline — kept in sync with ssot_constants.MODEL_PRICING_PER_1M_TOKENS.
_BASELINE: list[tuple[str, float, float]] = [
    # (model_id, input_per_1m, output_per_1m)
    ("gpt-4.1", 2.00, 8.00),
    ("gpt-4.1-mini", 0.40, 1.60),
    ("gpt-4.1-nano", 0.10, 0.40),
    ("gpt-4o", 2.50, 10.00),
    ("gpt-4o-mini", 0.15, 0.60),
    ("gpt-4-turbo", 10.00, 30.00),
    ("gpt-4", 30.00, 60.00),
    ("gpt-3.5-turbo", 0.50, 1.50),
    ("o1", 15.00, 60.00),
    ("o1-mini", 3.00, 12.00),
    ("o3", 2.00, 8.00),
    ("o3-mini", 1.10, 4.40),
    ("o4-mini", 1.10, 4.40),
]


class OpenAIPricingSource(PricingSource):
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
        logger.debug("OpenAIPricingSource.fetch returned %d models", len(result))
        return result
