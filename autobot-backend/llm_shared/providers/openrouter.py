# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
OpenRouter Provider - Unified interface for 200+ LLM models via OpenRouter API.

Issue #4341: Model Provider Flexibility & Vendor-Agnostic Switching

Configuration:
  - api_key: OpenRouter API key (from environment: OPENROUTER_API_KEY)
  - base_url: Optional custom base URL (default: https://openrouter.ai/api/v1)
  - default_model: Default model name for completions

Moved from llm_providers/ as part of Phase 2 consolidation (MVA-178 / GH#7637).
Consolidated onto :class:`OpenAICompatibleProvider` (#11517) — only the genuine
deltas live here: the OpenRouter gateway base URL, penalty-param forwarding
from ``metadata["api_kwargs"]``, and an empty static fallback (200+ live models
make any hardcoded list meaningless).
"""

from __future__ import annotations

from typing import List

from autobot_shared.ssot_config import config
from llm_shared.types import ProviderType

from .openai_compatible import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    """
    OpenRouter provider implementation.

    Supports chat completion and streaming across 200+ models from:
    OpenAI, Anthropic, Meta, Mistral, Google, Cohere, and more.

    Requires: openai package (pip install openai)
              OPENROUTER_API_KEY environment variable
    """

    # ProviderType.OPENROUTER is guaranteed to exist now that ProviderType is
    # a thin alias of the canonical union enum (#12661); the previous
    # hasattr() guard was defending against the pre-consolidation gap where
    # ProviderType lacked OPENROUTER (it only existed in the disagreeing
    # llm_cost_tracker.LLMProvider fork).
    provider_name = ProviderType.OPENROUTER.value
    default_model = "gpt-3.5-turbo"
    forward_penalty_params = True
    missing_key_error = "OpenRouter API key not found. Set OPENROUTER_API_KEY or provide api_key in settings."

    def _resolve_api_key(self) -> str | None:
        """Resolve API key from settings or environment."""
        if self._api_key:
            return self._api_key
        self._api_key = self._get_setting("api_key") or config.openrouter_api_key
        return self._api_key

    def _resolve_base_url(self) -> str:
        """Resolve base URL with the OpenRouter gateway default."""
        if self._base_url:
            return self._base_url
        default_url = "https://openrouter.ai/api/v1"
        self._base_url = self._get_setting("base_url") or config.openrouter_api_base_url or default_url
        return self._base_url

    def _fallback_model_list(self) -> List[str]:
        """No static fallback — OpenRouter's catalogue is live-only."""
        return []


__all__ = ["OpenRouterProvider"]
