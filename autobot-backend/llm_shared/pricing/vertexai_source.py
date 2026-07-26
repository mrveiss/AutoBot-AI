# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Vertex AI pricing source (GH#9009).

Vertex AI pricing for Gemini and Claude models. Gemini rates mirror the
Google AI Studio pricing; Claude-on-Vertex rates mirror the direct Anthropic
pricing. Hardcoded baseline until Google/Anthropic publish machine-readable
Vertex-specific pricing endpoints.
"""

from __future__ import annotations

from llm_shared.pricing.sources import BaselinePricingSource

_PROVIDER = "vertexai"

# (model_id, input_per_1m_usd, output_per_1m_usd)
_BASELINE: list[tuple[str, float, float]] = [
    # Gemini — same rates as Google AI Studio on Vertex
    ("gemini-2.5-pro", 1.25, 5.00),
    ("gemini-2.5-flash", 0.075, 0.30),
    ("gemini-2.0-flash", 0.075, 0.30),
    ("gemini-1.5-pro", 1.25, 5.00),
    ("gemini-1.5-flash", 0.075, 0.30),
    # Claude on Vertex — same rates as direct Anthropic API
    ("claude-opus-4@20251101", 15.00, 75.00),
    ("claude-sonnet-4-5@20251101", 3.00, 15.00),
    ("claude-3-5-sonnet-v2@20241022", 3.00, 15.00),
    ("claude-3-5-haiku@20241022", 0.80, 4.00),
    ("claude-3-opus@20240229", 15.00, 75.00),
]


class VertexAIPricingSource(BaselinePricingSource):
    provider = _PROVIDER
    _PROVIDER = _PROVIDER
    _BASELINE = _BASELINE
