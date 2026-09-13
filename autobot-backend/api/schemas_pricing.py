# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request models for the admin pricing API (GH#6480).

Moved out of ``api/admin_pricing.py`` unchanged, so the OpenAPI schema and the
generated frontend types stay identical (#16229).
"""

from pydantic import BaseModel, Field


class PricingOverrideRequest(BaseModel):
    input_per_1m: float = Field(..., gt=0, description="Input cost per 1M tokens (USD)")
    output_per_1m: float = Field(..., gt=0, description="Output cost per 1M tokens (USD)")
    cache_read_per_1m: float = Field(0.0, ge=0)
    cache_write_per_1m: float = Field(0.0, ge=0)
