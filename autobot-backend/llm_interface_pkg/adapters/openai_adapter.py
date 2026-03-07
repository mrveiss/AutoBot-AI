# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
OpenAI Adapter - Wraps existing OpenAIProvider for the adapter registry.

Issue #1403: Delegates to OpenAIProvider for execution, adds
test_environment and list_models via the OpenAI API.
"""

import logging
import time
from typing import List, Optional

from ..models import LLMRequest, LLMResponse
from .base import (
    AdapterBase,
    AdapterConfig,
    DiagnosticLevel,
    DiagnosticMessage,
    EnvironmentTestResult,
)

logger = logging.getLogger(__name__)


class OpenAIAdapter(AdapterBase):
    """Adapter wrapping the existing OpenAIProvider (#1403)."""

    def __init__(self, config: Optional[AdapterConfig] = None):
        super().__init__("openai_api", config)
        self._provider = None

    def _ensure_provider(self):
        """Lazily initialize the OpenAIProvider."""
        if self._provider is None:
            from ..providers.openai_provider import OpenAIProvider

            api_key = self.config.settings.get("api_key")
            self._provider = OpenAIProvider(api_key=api_key)
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

        provider = self._ensure_provider()
        if not provider.api_key:
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
            import openai

            client = openai.AsyncOpenAI(api_key=provider.api_key)
            model_list = await client.models.list()
            models = [m.id for m in model_list.data[:50]]
            diagnostics.append(
                DiagnosticMessage(
                    level=DiagnosticLevel.INFO,
                    message=f"Found {len(models)} models",
                )
            )
        except Exception as e:
            diagnostics.append(
                DiagnosticMessage(
                    level=DiagnosticLevel.ERROR,
                    message=f"API call failed: {e}",
                )
            )

        elapsed = time.time() - start
        healthy = len(models) > 0

        return EnvironmentTestResult(
            healthy=healthy,
            adapter_type="openai_api",
            diagnostics=diagnostics,
            models_available=models,
            response_time=elapsed,
        )

    async def list_models(self) -> List[str]:
        """Discover available OpenAI models."""
        result = await self.test_environment()
        return result.models_available


__all__ = ["OpenAIAdapter"]
