# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Nous Portal Provider - Access Nous Research's curated open-source LLM models.

Issue #4341: Model Provider Flexibility & Vendor-Agnostic Switching

Configuration:
  - api_key: HuggingFace API token or custom endpoint key
  - base_url: Custom API base URL (e.g., for self-hosted Nous models)
  - default_model: Default model name

Moved from llm_providers/ as part of Phase 2 consolidation (MVA-178 / GH#7637).
Consolidated onto :class:`OpenAICompatibleProvider` (#11517) — only the genuine
deltas live here: the HF token fallback chain, the HF inference base URL,
a 2048 default ``max_tokens``, and penalty-param forwarding from
``metadata["api_kwargs"]``.
"""

from __future__ import annotations

from autobot_shared.ssot_config import config

from .openai_compatible import OpenAICompatibleProvider

NOUS_MODELS = [
    "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO",
    "NousResearch/Nous-Hermes-2-Mistral-7B-DPO",
    "NousResearch/Nous-Hermes-2-Vision-7B",
    "NousResearch/Nous-Hermes-Llama2-7b",
    "NousResearch/Nous-Hermes-Llama2-13b",
]


class NousPortalProvider(OpenAICompatibleProvider):
    """
    Nous Portal provider implementation.

    Provides access to curated open-source LLM models from Nous Research.
    Requires: openai package (pip install openai)
              HF_TOKEN or custom API key in environment
    """

    provider_name = "nous"
    default_model = NOUS_MODELS[0]
    fallback_models = tuple(NOUS_MODELS)
    default_max_tokens = 2048  # HF inference endpoints reject unbounded generations
    forward_penalty_params = True
    missing_key_error = "Nous API key not found. Set HF_TOKEN or provide api_key in settings."

    def _resolve_api_key(self) -> str | None:
        """Resolve API key from settings or the HF token fallback chain."""
        if self._api_key:
            return self._api_key
        self._api_key = (
            self._get_setting("api_key") or config.hf_token or config.huggingface_api_token or config.nous_api_key
        )
        return self._api_key

    def _resolve_base_url(self) -> str:
        """Resolve base URL with the HF inference default."""
        if self._base_url:
            return self._base_url
        default_url = "https://api-inference.huggingface.co/v1"
        self._base_url = self._get_setting("base_url") or config.nous_api_base_url or default_url
        return self._base_url


__all__ = ["NousPortalProvider", "NOUS_MODELS"]
