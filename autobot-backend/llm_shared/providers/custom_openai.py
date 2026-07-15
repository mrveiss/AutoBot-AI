# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Custom OpenAI-compatible endpoint provider for the multi-provider LLM layer (#1806).

Works with any server that exposes the OpenAI ``/v1/chat/completions`` API,
including vLLM, llama.cpp server, LM Studio, Ollama in OpenAI-compat mode,
Jan.ai, and similar projects.

Configuration (via settings dict or environment variables):

  - ``base_url`` / ``CUSTOM_OPENAI_BASE_URL``   — required base URL
  - ``api_key``  / ``CUSTOM_OPENAI_API_KEY``    — optional (defaults to "none")
  - ``default_model``                            — model to use when not specified

Moved from llm_providers/ as part of Phase 2 consolidation (MVA-178 / GH#7637).
Consolidated onto :class:`OpenAICompatibleProvider` (#11517) — only the genuine
deltas live here: mandatory base_url, permissive api_key default, and optional
per-instance provider naming.
"""

from __future__ import annotations

from typing import Any, Dict

from autobot_shared.ssot_config import config

from .openai_compatible import OpenAICompatibleProvider


class CustomOpenAIProvider(OpenAICompatibleProvider):
    """
    Provider for any server exposing an OpenAI-compatible REST API.

    Backed by the ``openai`` Python SDK configured to point at a custom
    ``base_url``, so it benefits from the SDK's retry/backoff logic and
    async streaming support without extra dependencies.
    """

    provider_name = "custom_openai"

    def __init__(
        self,
        settings: Dict[str, Any] | None = None,
        instance_name: str | None = None,
    ) -> None:
        super().__init__(settings)
        if instance_name:
            self.provider_name = instance_name

    def _resolve_base_url(self) -> str:
        """Resolve the endpoint base URL from settings or environment (required)."""
        url = self._get_setting("base_url") or config.custom_openai_base_url
        if not url:
            raise ValueError(
                "Custom OpenAI base_url not configured. "
                "Provide base_url in provider settings or set CUSTOM_OPENAI_BASE_URL."
            )
        return url.rstrip("/")

    def _resolve_api_key(self) -> str:
        """Resolve the API key (many local servers accept any non-empty string)."""
        return self._get_setting("api_key") or config.custom_openai_api_key or "none"


__all__ = ["CustomOpenAIProvider"]
