# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Groq provider for the multi-provider LLM layer (#4096).

Groq exposes an OpenAI-compatible Chat Completions API so this implementation
delegates to the ``groq`` SDK (which mirrors the ``openai`` SDK surface).
The local ``groq`` package is imported lazily so the rest of the application
boots normally when the package is absent.

API key is read (in priority order) from:
  1. ``settings["api_key"]``
  2. Environment variable ``GROQ_API_KEY``

API keys are never logged.

Moved from llm_providers/ as part of Phase 2 consolidation (MVA-178 / GH#7637).
Consolidated onto :class:`OpenAICompatibleProvider` (#11517) — only the genuine
Groq deltas live here: the ``groq`` SDK client and the historical omission of
``top_p`` from the payload.
"""

from __future__ import annotations

from typing import List

from autobot_shared.ssot_config import config
from constants.model_constants import (
    GROQ_GEMMA2_9B,
    GROQ_LLAMA3_8B,
    GROQ_LLAMA3_70B,
    GROQ_LLAMA31_8B,
    GROQ_LLAMA33_70B,
    GROQ_MIXTRAL_8X7B,
)
from llm_shared.types import ProviderType

from .openai_compatible import OpenAICompatibleProvider

GROQ_MODELS: List[str] = [
    GROQ_LLAMA33_70B,
    GROQ_LLAMA3_70B,
    GROQ_LLAMA31_8B,
    GROQ_LLAMA3_8B,
    GROQ_MIXTRAL_8X7B,
    GROQ_GEMMA2_9B,
]

_DEFAULT_MODEL = GROQ_LLAMA31_8B


class GroqProvider(OpenAICompatibleProvider):
    """
    Groq LLM provider implementation.

    Supports chat completion and streaming for Llama, Mixtral, and Gemma
    model families hosted on Groq's ultra-low-latency inference API.
    Requires the ``groq`` package (``pip install groq``).
    """

    provider_name = ProviderType.GROQ.value
    default_model = _DEFAULT_MODEL
    fallback_models = tuple(GROQ_MODELS)
    include_top_p = False  # historical Groq payload never sent top_p
    missing_key_error = "Groq API key not configured. Set GROQ_API_KEY or provide api_key in provider settings."

    def _resolve_api_key(self) -> str | None:
        """Resolve API key from settings or environment."""
        if self._api_key:
            return self._api_key
        self._api_key = self._get_setting("api_key") or config.groq_api_key
        return self._api_key

    def _create_client(self):
        """Lazily construct the async Groq client (mirrors the openai SDK surface)."""
        try:
            import groq
        except ImportError as exc:
            raise ImportError("groq package not installed. Run: pip install groq") from exc
        api_key = self._resolve_api_key()
        if not api_key:
            raise ValueError(self.missing_key_error)
        return groq.AsyncGroq(api_key=api_key)


__all__ = ["GroqProvider", "GROQ_MODELS"]
