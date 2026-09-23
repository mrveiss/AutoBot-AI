# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Response models for ``GET /cost/pricing`` (#16230).

Split out of `schemas_analytics.py`, which is grandfathered at its file-size
ceiling (#5060) and may not grow -- and `#16230` needed two new fields on
`ModelPricingResponse` to stop the endpoint reporting a fetch date it does not
have.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ModelPricingEntry(BaseModel):
    model: str
    provider: str
    input_price_per_1m: float
    output_price_per_1m: float
    is_free: bool


class ModelPricingResponse(BaseModel):
    """Response for GET /cost/pricing."""

    #: `None` when nothing states a fetch date (the #16230 baselines). Not
    #: defaulted to today: that is the manufactured freshness #16233 AC3 forbids.
    pricing_date: Optional[str] = None
    pricing_date_unknown_reason: Optional[str] = None
    #: "litellm", "openrouter", or "baseline" for the frozen last-resort tables.
    sources: List[str] = Field(default_factory=list)
    currency: str
    models: List[ModelPricingEntry]
    total_models: int
