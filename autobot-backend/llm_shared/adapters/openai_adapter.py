# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
OpenAI Adapter - Adapter wrapping llm_providers.OpenAIProvider (#1403).

Delegates execution to ``llm_providers.OpenAIProvider`` which owns the
canonical OpenAI implementation (OTel tracing, circuit breaker, streaming).
This adapter's sole responsibility is the ``test_environment()`` diagnostic
method used by ``api/adapters.py``.
"""

import time
from typing import List

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

from ..models import LLMRequest, LLMResponse
from .base import (
    AdapterBase,
    AdapterConfig,
    DiagnosticLevel,
    DiagnosticMessage,
    EnvironmentTestResult,
)

logger = get_logger(__name__)


class OpenAIAdapter(AdapterBase):
    """Adapter wrapping the canonical OpenAIProvider (#1403)."""

    def __init__(self, config: AdapterConfig | None = None):
        super().__init__("openai_api", config)
        self._provider = None

    def _get_api_key(self) -> str | None:
        """Resolve OpenAI API key from config or environment."""
        return self.config.settings.get("api_key") or config.openai_api_key

    def _ensure_provider(self):
        """Lazily construct the canonical OpenAIProvider."""
        if self._provider is None:
            from llm_shared.providers.openai import OpenAIProvider

            api_key = self._get_api_key()
            settings = {"api_key": api_key} if api_key else {}
            self._provider = OpenAIProvider(settings=settings)
        return self._provider

    async def execute(self, request: LLMRequest) -> LLMResponse:
        """Execute LLM call via OpenAIProvider."""
        provider = self._ensure_provider()
        return await provider.chat_completion(request)

    async def test_environment(self) -> EnvironmentTestResult:
        """Test OpenAI API connectivity."""
        diagnostics: List[DiagnosticMessage] = []
        start = time.time()
        models: List[str] = []

        api_key = self._get_api_key()
        if not api_key:
            diagnostics.append(
                DiagnosticMessage(
                    level=DiagnosticLevel.ERROR,
                    message="OpenAI API key not configured",
                )
            )
            return EnvironmentTestResult(
                healthy=False,
                adapter_type="openai_api",
                diagnostics=diagnostics,
                response_time=time.time() - start,
            )

        diagnostics.append(
            DiagnosticMessage(
                level=DiagnosticLevel.INFO,
                message="API key configured",
            )
        )

        try:
            provider = self._ensure_provider()
            models = await provider.list_models()
            diagnostics.append(
                DiagnosticMessage(
                    level=DiagnosticLevel.INFO,
                    message=f"Found {len(models)} models",
                )
            )
        except Exception as exc:  # Issue #3866: log so server-side errors are visible
            logger.warning("OpenAIAdapter.test_environment() failed: %s", exc)
            diagnostics.append(
                DiagnosticMessage(
                    level=DiagnosticLevel.ERROR,
                    message="API call failed",
                )
            )

        elapsed = time.time() - start
        healthy = len(models) > 0

        return EnvironmentTestResult(
            healthy=healthy,
            adapter_type="openai_api",
            diagnostics=diagnostics,
            models_available=models[:50],
            response_time=elapsed,
        )

    async def list_models(self) -> List[str]:
        """Discover available OpenAI models."""
        provider = self._ensure_provider()
        return await provider.list_models()


__all__ = ["OpenAIAdapter"]
