# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
OpenAI provider for the multi-provider LLM layer (#1806).

Supports chat completion and streaming for all GPT/o1 model families.
API key is read (in priority order) from:
  1. ``settings["api_key"]``
  2. Environment variable ``OPENAI_API_KEY``
  3. ConfigManager (backward-compatible path)

API keys are never logged.

Moved from llm_providers/ as part of Phase 2 consolidation (MVA-178 / GH#7637).
Consolidated onto :class:`OpenAICompatibleProvider` (#11517) — only the genuine
OpenAI deltas live here: SSOT key fallback chain, optional base_url override,
reasoning-effort mapping (#9017), and prompt-cache payload normalisation (#7368).
"""

from __future__ import annotations

from typing import Any, Dict

from autobot_shared.ssot_config import config
from constants.model_constants import OPENAI_O1_MINI  # used in _OPENAI_MODELS list
from constants.model_constants import (
    OPENAI_GPT4,
    OPENAI_GPT4_TURBO,
    OPENAI_GPT4O,
    OPENAI_GPT4O_MINI,
    OPENAI_GPT35_TURBO,
)
from llm_shared.models import LLMRequest
from llm_shared.types import ProviderType

from .openai_compatible import OpenAICompatibleProvider
from .reasoning_effort import map_effort_to_provider_params

_OPENAI_MODELS = [
    OPENAI_GPT4O,
    OPENAI_GPT4O_MINI,
    OPENAI_GPT4_TURBO,
    OPENAI_GPT4,
    OPENAI_GPT35_TURBO,
    "o1-preview",
    OPENAI_O1_MINI,
]


class OpenAIProvider(OpenAICompatibleProvider):
    """
    OpenAI provider implementation.

    Supports chat completion and streaming for all GPT/o1 model families.
    Requires the ``openai`` package (``pip install openai``).
    """

    provider_name = ProviderType.OPENAI.value
    default_model = OPENAI_GPT4O_MINI
    fallback_models = tuple(_OPENAI_MODELS)
    sort_params_for_cache = True  # #7368: byte-exact payloads keep prompt caching warm
    missing_key_error = "OpenAI API key not configured. Set OPENAI_API_KEY or provide api_key in provider settings."

    def _resolve_api_key(self) -> str | None:
        """Resolve API key from settings, environment, or SSOT config."""
        if self._api_key:
            return self._api_key
        key = self._get_setting("api_key") or config.openai_api_key
        if not key:
            try:
                from autobot_shared.ssot_config import config as _ssot_config

                key = _ssot_config.llm.openai_api_key
            except Exception:
                pass
        self._api_key = key
        return self._api_key

    def _resolve_base_url(self) -> str | None:
        """Optional base URL override (Azure/OpenAI-compatible gateways)."""
        return self._get_setting("base_url") or config.openai_api_base_url

    def _extra_params(self, request: LLMRequest) -> Dict[str, Any]:
        """#9017: merge reasoning_effort params (e.g. ``{"reasoning_effort": "high"}`` for o1/o3)."""
        api_kwargs: Dict[str, Any] = request.metadata.get("api_kwargs") or {}
        return map_effort_to_provider_params(api_kwargs.get("reasoning_effort"), self.provider_name)


__all__ = ["OpenAIProvider"]
